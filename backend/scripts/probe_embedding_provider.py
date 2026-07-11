"""探测 OpenAI Embeddings 兼容服务的结构和中文语义排序能力。"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXACT_DUPLICATE_MIN_SIMILARITY = 0.999


@dataclass(frozen=True, slots=True)
class ProbeSample:
    """一条固定的中性化 Embedding 探测文本。"""

    label: str
    text: str


@dataclass(frozen=True, slots=True)
class SemanticCase:
    """一个锚点及其预期排名第一的语义改写。"""

    label: str
    anchor_index: int
    positive_index: int
    excluded_indices: frozenset[int]


SAMPLES = (
    ProbeSample(
        "invoice_anchor",
        "目标用户：小型装修公司财务；核心痛点：报销时需要人工核对发票抬头和金额，"
        "经常出错并反复沟通；场景：每周集中处理员工报销；期望结果：减少核对时间和返工。",
    ),
    ProbeSample(
        "invoice_paraphrase",
        "目标用户：中小装修企业的报销负责人；核心痛点：逐张检查发票名称与金额耗时且容易遗漏；"
        "场景：周期性审核员工提交的票据；期望结果：更快发现填写错误并减少来回确认。",
    ),
    ProbeSample(
        "invoice_hard_negative",
        "目标用户：小型装修公司项目经理；核心痛点：工人分散在多个工地，排班和调度经常冲突；"
        "场景：每天安排施工人员；期望结果：减少空档和临时调班。",
    ),
    ProbeSample(
        "expiry_anchor",
        "目标用户：餐饮门店店长；核心痛点：人工检查食材保质期容易遗漏并造成浪费；"
        "场景：每天盘点冷库和货架；期望结果：及时发现临期食材并减少损耗。",
    ),
    ProbeSample(
        "expiry_paraphrase",
        "目标用户：小型餐厅库存负责人；核心痛点：依赖手写记录追踪原料有效期，常有食材过期；"
        "场景：每日备餐和库存检查；期望结果：提前处理临期库存并降低浪费。",
    ),
    ProbeSample(
        "expiry_hard_negative",
        "目标用户：餐饮门店前台；核心痛点：用餐高峰排队和桌位分配混乱；"
        "场景：晚餐时段接待顾客；期望结果：缩短等位时间并提高翻台效率。",
    ),
    ProbeSample(
        "appointment_anchor",
        "目标用户：小型诊所前台；核心痛点：患者忘记预约导致医生时段空置；"
        "场景：每天安排门诊预约；期望结果：降低爽约率并充分利用医生时间。",
    ),
    ProbeSample(
        "appointment_paraphrase",
        "目标用户：社区门诊预约人员；核心痛点：患者没有按时到诊，预留的接诊时间被浪费；"
        "场景：日常维护医生排期；期望结果：减少未到诊并提升预约利用率。",
    ),
    ProbeSample(
        "appointment_hard_negative",
        "目标用户：小型诊所医护人员；核心痛点：相同病历信息需要重复录入多个系统；"
        "场景：患者就诊后整理记录；期望结果：减少重复录入和信息错误。",
    ),
    ProbeSample(
        "invoice_exact_duplicate",
        "目标用户：小型装修公司财务；核心痛点：报销时需要人工核对发票抬头和金额，"
        "经常出错并反复沟通；场景：每周集中处理员工报销；期望结果：减少核对时间和返工。",
    ),
)

SEMANTIC_CASES = (
    SemanticCase("发票核对", 0, 1, frozenset({0, 9})),
    SemanticCase("食材保质期", 3, 4, frozenset({3})),
    SemanticCase("预约爽约", 6, 7, frozenset({6})),
)


class ProbeSettings(BaseSettings):
    """从环境变量或 backend/.env 读取 Embedding 探测配置。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_prefix="EMBEDDING_",
        extra="ignore",
    )

    base_url: str = Field(min_length=1)
    api_key: SecretStr = Field(min_length=1)
    model_id: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60, gt=0, le=300)
    dimensions: int | None = Field(default=None, gt=0, le=100_000)


class ProbeFailure(RuntimeError):
    """表示配置、HTTP 或向量结构探测失败。"""


class EmbeddingItem(BaseModel):
    """OpenAI 兼容响应中的单条向量。"""

    model_config = ConfigDict(extra="ignore", strict=True)

    index: int = Field(ge=0)
    embedding: list[float]

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding_values(cls, value: Any) -> list[float]:
        if not isinstance(value, list):
            raise ValueError("embedding 必须是数组")
        normalized: list[float] = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError("embedding 只能包含数值")
            number = float(item)
            if not math.isfinite(number):
                raise ValueError("embedding 不能包含 NaN 或 Infinity")
            normalized.append(number)
        return normalized


class EmbeddingResponse(BaseModel):
    """探测脚本需要的 OpenAI 兼容响应字段。"""

    model_config = ConfigDict(extra="ignore", strict=True)

    data: list[EmbeddingItem]
    model: str | None = None
    usage: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ParsedEmbeddings:
    """按输入索引恢复顺序后的已校验向量。"""

    vectors: tuple[tuple[float, ...], ...]
    dimension: int
    norms: tuple[float, ...]
    response_model: str | None
    usage: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class ProbeRunResult:
    """一次成功接口调用的结构化结果。"""

    embeddings: ParsedEmbeddings
    elapsed_seconds: float
    request_id: str | None


@dataclass(frozen=True, slots=True)
class SemanticCaseResult:
    """一个语义锚点的正样例与最佳负样例排名。"""

    label: str
    positive_similarity: float
    best_negative_label: str
    best_negative_similarity: float
    margin: float
    passed: bool
    ranking: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class SemanticAnalysis:
    """固定中文样例的完整行为检查结果。"""

    exact_duplicate_similarity: float
    cases: tuple[SemanticCaseResult, ...]
    failures: tuple[str, ...]


def build_embeddings_url(base_url: str) -> str:
    """把常规 Base URL 转换成 Embeddings 端点。"""

    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProbeFailure("EMBEDDING_BASE_URL 不能为空")
    if normalized.endswith("/embeddings"):
        return normalized
    return f"{normalized}/embeddings"


def classify_http_error(status_code: int) -> str:
    """将常见状态码转换成便于选择服务商的错误分类。"""

    if status_code in {401, 403}:
        return "鉴权失败"
    if status_code == 404:
        return "Base URL、接口路径或 Model ID 不存在"
    if status_code in {400, 422}:
        return "请求参数、批量输入或 float 格式不受支持"
    if status_code == 429:
        return "请求被限流或余额不足"
    if status_code >= 500:
        return "Embedding 服务内部错误"
    return "HTTP 请求失败"


def vector_norm(vector: tuple[float, ...]) -> float:
    """计算向量的欧几里得范数。"""

    return math.sqrt(sum(value * value for value in vector))


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """计算两个同维非零向量的余弦相似度。"""

    if len(left) != len(right):
        raise ValueError("余弦相似度要求向量维度一致")
    left_norm = vector_norm(left)
    right_norm = vector_norm(right)
    if left_norm == 0 or right_norm == 0:
        raise ValueError("余弦相似度不接受零向量")
    raw_similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return max(-1.0, min(1.0, raw_similarity))


def parse_embedding_response(
    response_body: str,
    *,
    expected_count: int,
    expected_dimensions: int | None,
) -> ParsedEmbeddings:
    """解析响应并严格校验索引、维度和向量数值。"""

    try:
        parsed = EmbeddingResponse.model_validate_json(response_body)
    except ValidationError as exc:
        raise ProbeFailure(f"Embedding 响应结构无效：{exc.error_count()} 个校验错误") from exc

    if len(parsed.data) != expected_count:
        raise ProbeFailure(f"向量数量不符：期望 {expected_count}，实际 {len(parsed.data)}")

    indexed: dict[int, tuple[float, ...]] = {}
    for item in parsed.data:
        if item.index in indexed:
            raise ProbeFailure(f"响应包含重复 index：{item.index}")
        if item.index >= expected_count:
            raise ProbeFailure(f"响应 index 越界：{item.index}")
        indexed[item.index] = tuple(item.embedding)

    expected_indices = set(range(expected_count))
    if set(indexed) != expected_indices:
        missing = ", ".join(str(index) for index in sorted(expected_indices - set(indexed)))
        raise ProbeFailure(f"响应缺少 index：{missing}")

    vectors = tuple(indexed[index] for index in range(expected_count))
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise ProbeFailure("响应中的向量维度不一致")
    dimension = dimensions.pop()
    if dimension == 0:
        raise ProbeFailure("Embedding 向量不能为空")
    if expected_dimensions is not None and dimension != expected_dimensions:
        raise ProbeFailure(f"Embedding 维度不匹配：配置 {expected_dimensions}，实际 {dimension}")

    norms = tuple(vector_norm(vector) for vector in vectors)
    if any(norm == 0 for norm in norms):
        raise ProbeFailure("Embedding 响应包含零向量")

    return ParsedEmbeddings(
        vectors=vectors,
        dimension=dimension,
        norms=norms,
        response_model=parsed.model,
        usage=parsed.usage,
    )


def send_probe(
    settings: ProbeSettings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProbeRunResult:
    """发送一次无重试的批量 Embedding 探测请求。"""

    endpoint = build_embeddings_url(settings.base_url)
    payload = {
        "model": settings.model_id,
        "input": [sample.text for sample in SAMPLES],
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }

    started_at = perf_counter()
    try:
        with httpx.Client(timeout=settings.timeout_seconds, transport=transport) as client:
            response = client.post(endpoint, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        elapsed = perf_counter() - started_at
        raise ProbeFailure(f"请求超时，耗时 {elapsed:.2f}s") from exc
    except httpx.RequestError as exc:
        elapsed = perf_counter() - started_at
        raise ProbeFailure(f"网络连接失败，耗时 {elapsed:.2f}s") from exc

    elapsed = perf_counter() - started_at
    if response.status_code >= 400:
        category = classify_http_error(response.status_code)
        safe_body = response.text[:1500].replace(settings.api_key.get_secret_value(), "***")
        raise ProbeFailure(
            f"{category}：HTTP {response.status_code}，耗时 {elapsed:.2f}s\n服务端响应：{safe_body}"
        )

    embeddings = parse_embedding_response(
        response.text,
        expected_count=len(SAMPLES),
        expected_dimensions=settings.dimensions,
    )
    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    return ProbeRunResult(
        embeddings=embeddings,
        elapsed_seconds=elapsed,
        request_id=request_id,
    )


def analyze_semantics(vectors: tuple[tuple[float, ...], ...]) -> SemanticAnalysis:
    """检查完全重复一致性和三个中文主题的 Top-1 排名。"""

    if len(vectors) != len(SAMPLES):
        raise ValueError("语义分析向量数量必须与固定样例一致")

    failures: list[str] = []
    exact_similarity = cosine_similarity(vectors[0], vectors[9])
    if exact_similarity < EXACT_DUPLICATE_MIN_SIMILARITY:
        failures.append(
            f"完全相同文本的相似度低于 {EXACT_DUPLICATE_MIN_SIMILARITY:.4f}：{exact_similarity:.6f}"
        )

    case_results: list[SemanticCaseResult] = []
    for case in SEMANTIC_CASES:
        anchor = vectors[case.anchor_index]
        ranked = sorted(
            (
                (index, cosine_similarity(anchor, vector))
                for index, vector in enumerate(vectors)
                if index not in case.excluded_indices
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        best_index, _ = ranked[0]
        positive_similarity = next(
            similarity for index, similarity in ranked if index == case.positive_index
        )
        negative_candidates = [item for item in ranked if item[0] != case.positive_index]
        best_negative_index, best_negative_similarity = negative_candidates[0]
        passed = best_index == case.positive_index
        if not passed:
            failures.append(
                f"{case.label}的语义改写不是 Top-1，最高结果为 {SAMPLES[best_index].label}"
            )
        case_results.append(
            SemanticCaseResult(
                label=case.label,
                positive_similarity=positive_similarity,
                best_negative_label=SAMPLES[best_negative_index].label,
                best_negative_similarity=best_negative_similarity,
                margin=positive_similarity - best_negative_similarity,
                passed=passed,
                ranking=tuple((SAMPLES[index].label, similarity) for index, similarity in ranked),
            )
        )

    return SemanticAnalysis(
        exact_duplicate_similarity=exact_similarity,
        cases=tuple(case_results),
        failures=tuple(failures),
    )


def print_usage(usage: dict[str, Any] | None) -> None:
    """打印 Embedding 服务返回的 Token 用量。"""

    if usage is None:
        print("Token 用量：服务端未返回")
        return
    prompt_tokens = usage.get("prompt_tokens", "未知")
    total_tokens = usage.get("total_tokens", "未知")
    print(f"Token 用量：输入 {prompt_tokens}，合计 {total_tokens}")


def print_run_result(run_number: int, result: ProbeRunResult, analysis: SemanticAnalysis) -> None:
    """输出一次探测的安全摘要，不打印完整向量。"""

    embeddings = result.embeddings
    print(f"\n第 {run_number} 次探测：")
    print(
        f"[PASS] 返回 {len(embeddings.vectors)} 条合法向量，维度 {embeddings.dimension}，"
        f"耗时 {result.elapsed_seconds:.2f}s"
    )
    print(f"响应模型：{embeddings.response_model or '服务端未返回'}")
    print(f"请求 ID：{result.request_id or '服务端未返回'}")
    print(f"向量范数：最小 {min(embeddings.norms):.6f}，最大 {max(embeddings.norms):.6f}")
    print(f"完全相同文本相似度：{analysis.exact_duplicate_similarity:.6f}")
    for case in analysis.cases:
        status = "PASS" if case.passed else "FAIL"
        print(
            f"[{status}] {case.label}：改写 {case.positive_similarity:.6f}，"
            f"最佳负样例 {case.best_negative_label}={case.best_negative_similarity:.6f}，"
            f"差值 {case.margin:+.6f}"
        )
        ranking = " > ".join(f"{label}={similarity:.6f}" for label, similarity in case.ranking)
        print(f"  排名：{ranking}")
    print_usage(embeddings.usage)


def run_probe(
    settings: ProbeSettings,
    *,
    runs: int,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """执行指定次数的探测并返回稳定的进程退出码。"""

    semantic_failures: list[str] = []
    for run_number in range(1, runs + 1):
        try:
            result = send_probe(settings, transport=transport)
        except ProbeFailure as exc:
            print(f"\n[FAIL] 第 {run_number} 次探测失败：{exc}")
            return 1
        analysis = analyze_semantics(result.embeddings.vectors)
        print_run_result(run_number, result, analysis)
        semantic_failures.extend(f"第 {run_number} 次：{failure}" for failure in analysis.failures)

    if semantic_failures:
        print("\n[FAIL] 固定中文语义样例未达到最低要求：")
        for failure in semantic_failures:
            print(f"  - {failure}")
        return 2

    print(f"\n[PASS] {runs} 次探测的接口、向量结构和中文语义排序全部通过")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="探测 OpenAI 兼容 Embedding 服务的结构和中文语义排序能力",
    )
    parser.add_argument(
        "--runs",
        type=int,
        choices=range(1, 4),
        default=1,
        metavar="1..3",
        help="真实请求次数，默认 1，最多 3 次且不会自动重试",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = ProbeSettings()
    except ValidationError as exc:
        print(
            "配置错误：请在 backend/.env 中设置 EMBEDDING_BASE_URL、"
            "EMBEDDING_API_KEY 和 EMBEDDING_MODEL_ID。"
        )
        print(exc)
        return 1

    print(f"模型：{settings.model_id}")
    print(f"端点：{build_embeddings_url(settings.base_url)}")
    print(f"固定中文样例：{len(SAMPLES)} 条；真实请求：{args.runs} 次；不自动重试")
    return run_probe(settings, runs=args.runs)


if __name__ == "__main__":
    sys.exit(main())
