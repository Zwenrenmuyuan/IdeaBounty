"""探测 OpenAI 兼容模型的查重结构和固定中文判定表现。"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import httpx
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from idea_bounty.ai.duplicate_prompts import build_duplicate_payload
from idea_bounty.models import (
    DuplicateVerdict,
    InformationSource,
    PainRelation,
    SolutionRelation,
)
from idea_bounty.schemas.ai import NormalizedField
from idea_bounty.schemas.duplicate import (
    ComparableIdea,
    DuplicateCandidateInput,
    DuplicateComparisonInput,
    DuplicateJudgmentOutput,
    validate_duplicate_judgment_json,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class ProbeSettings(BaseSettings):
    """从 backend/.env 读取现有生成模型配置。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_prefix="AI_",
        extra="ignore",
    )

    base_url: str = Field(min_length=1)
    api_key: SecretStr = Field(min_length=1)
    model_id: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60, gt=0, le=300)
    temperature: float = Field(default=0.2, ge=0, le=2)


class ProbeFailure(RuntimeError):
    """表示配置、HTTP 或模型结构化输出探测失败。"""


@dataclass(frozen=True, slots=True)
class ProbeCase:
    """一个固定中文查重案例及其预期结论。"""

    case_id: str
    label: str
    comparison: DuplicateComparisonInput
    expected_pain_relation: PainRelation
    expected_solution_relation: SolutionRelation
    expected_verdict: DuplicateVerdict
    expected_matched_internal_id: int | None


@dataclass(frozen=True, slots=True)
class ProbeCaseResult:
    """一次成功模型调用的结构化结果和安全元数据。"""

    output: DuplicateJudgmentOutput
    elapsed_seconds: float
    request_id: str | None
    total_tokens: int | None


def _unknown() -> NormalizedField:
    return NormalizedField(value=None, source=InformationSource.UNKNOWN)


def _known(value: str, *, inferred: bool = False) -> NormalizedField:
    source = InformationSource.INFERRED if inferred else InformationSource.EXPLICIT
    return NormalizedField(value=value, source=source)


def _idea(
    *,
    audience: str,
    pain: str,
    context: str,
    desired: str,
    frequency: str | None = None,
    alternative: str | None = None,
    solution: str | None = None,
    mechanism: str | None = None,
    value_proposition: str | None = None,
) -> ComparableIdea:
    has_solution = solution is not None
    return ComparableIdea(
        target_audience=_known(audience),
        pain_point=_known(pain),
        context=_known(context),
        frequency_or_severity=_known(frequency) if frequency else _unknown(),
        current_alternative=_known(alternative) if alternative else _unknown(),
        desired_outcome=_known(desired),
        solution_present=has_solution,
        proposed_solution=_known(solution) if solution else _unknown(),
        solution_mechanism=(
            _known(mechanism, inferred=True) if mechanism is not None else _unknown()
        ),
        value_proposition=(
            _known(value_proposition, inferred=True)
            if value_proposition is not None
            else _unknown()
        ),
    )


def _comparison(
    current: ComparableIdea,
    *candidates: tuple[int, ComparableIdea],
) -> DuplicateComparisonInput:
    return DuplicateComparisonInput(
        current=current,
        candidates=[
            DuplicateCandidateInput(internal_id=internal_id, content=content)
            for internal_id, content in candidates
        ],
    )


PROBE_CASES = (
    ProbeCase(
        "duplicate_paraphrase",
        "同一痛点的明显改写",
        _comparison(
            _idea(
                audience="社区独居老人",
                pain="行动不便时购买日常食材困难",
                context="日常居家生活",
                desired="更方便地获得新鲜食材",
            ),
            (
                101,
                _idea(
                    audience="独居且行动不便的老年人",
                    pain="平时难以外出买菜",
                    context="独自在家生活",
                    desired="不出门也能获得日常食材",
                ),
            ),
            (
                102,
                _idea(
                    audience="社区独居老人",
                    pain="容易忘记按时服药",
                    context="日常居家生活",
                    desired="减少漏服药物",
                ),
            ),
        ),
        PainRelation.SAME,
        SolutionRelation.NOT_APPLICABLE,
        DuplicateVerdict.DUPLICATE,
        101,
    ),
    ProbeCase(
        "duplicate_same_solution",
        "相同痛点和相同方案",
        _comparison(
            _idea(
                audience="中小企业财务人员",
                pain="人工核对报销发票抬头和金额非常耗时",
                context="每周集中处理员工报销",
                desired="减少发票核对和返工时间",
                solution="上传发票照片后自动识别并检查字段",
                mechanism="OCR 提取字段后与公司信息比对",
            ),
            (
                201,
                _idea(
                    audience="小公司报销负责人",
                    pain="手工检查发票信息容易出错并反复沟通",
                    context="员工提交报销材料时",
                    desired="自动发现发票字段错误",
                    solution="上传发票图片自动识别并校验抬头金额",
                    mechanism="OCR 识别加规则比对",
                ),
            ),
            (
                202,
                _idea(
                    audience="中小企业财务人员",
                    pain="报销审批流经常找不到负责人",
                    context="跨部门审批报销时",
                    desired="自动分配审批人",
                ),
            ),
        ),
        PainRelation.SAME,
        SolutionRelation.SAME,
        DuplicateVerdict.DUPLICATE,
        201,
    ),
    ProbeCase(
        "duplicate_audience_wording",
        "用户称呼不同但实际场景相同",
        _comparison(
            _idea(
                audience="小型餐厅店长",
                pain="食材临近过期时难以及时发现",
                context="每天检查后厨库存",
                desired="减少过期浪费",
            ),
            (
                301,
                _idea(
                    audience="中小餐饮门店负责人",
                    pain="库存食材保质期依靠人工检查容易遗漏",
                    context="门店每日盘点后厨库存",
                    desired="及时处理临期食材并减少浪费",
                ),
            ),
            (
                302,
                _idea(
                    audience="餐厅顾客",
                    pain="排队时不知道还要等待多久",
                    context="到店就餐高峰期",
                    desired="提前知道等位时间",
                ),
            ),
        ),
        PainRelation.SAME,
        SolutionRelation.NOT_APPLICABLE,
        DuplicateVerdict.DUPLICATE,
        301,
    ),
    ProbeCase(
        "related_different_solution",
        "相同痛点但不同方案",
        _comparison(
            _idea(
                audience="小型诊所前台",
                pain="患者预约后频繁爽约造成号源浪费",
                context="日常门诊预约管理",
                desired="降低预约爽约率",
                solution="预约时收取可退还的小额保证金",
                mechanism="按到诊状态自动退还保证金",
            ),
            (
                401,
                _idea(
                    audience="诊所预约管理员",
                    pain="患者预约后不来导致医生时间空置",
                    context="门诊预约安排",
                    desired="减少患者爽约",
                    solution="就诊前通过短信和电话多次提醒",
                    mechanism="按预约时间触发分阶段提醒",
                ),
            ),
            (
                402,
                _idea(
                    audience="小型诊所前台",
                    pain="现场排队患者不知道预计等待时间",
                    context="门诊候诊区",
                    desired="让患者了解排队进度",
                ),
            ),
        ),
        PainRelation.SAME,
        SolutionRelation.DIFFERENT,
        DuplicateVerdict.RELATED,
        401,
    ),
    ProbeCase(
        "related_new_solution",
        "历史只有痛点而新投稿增加方案",
        _comparison(
            _idea(
                audience="装修公司报销负责人",
                pain="人工核对发票抬头经常返工",
                context="每周处理员工报销",
                desired="缩短发票检查时间",
                solution="上传发票后自动检查公司抬头",
                mechanism="OCR 识别后与预设抬头比对",
            ),
            (
                501,
                _idea(
                    audience="装修公司财务人员",
                    pain="人工核对员工发票抬头经常出错并返工",
                    context="每周集中处理员工报销",
                    desired="缩短发票检查和返工时间",
                ),
            ),
            (
                502,
                _idea(
                    audience="装修公司项目经理",
                    pain="施工材料送达时间经常无法确定",
                    context="安排现场施工计划",
                    desired="及时了解材料物流",
                ),
            ),
        ),
        PainRelation.SAME,
        SolutionRelation.DIFFERENT,
        DuplicateVerdict.RELATED,
        501,
    ),
    ProbeCase(
        "related_pain",
        "同一业务场景中的相关痛点",
        _comparison(
            _idea(
                audience="小型餐饮门店店长",
                pain="食材采购量难以预测，经常买多造成积压",
                context="每周制定食材采购计划",
                desired="让采购量更接近实际消耗",
            ),
            (
                601,
                _idea(
                    audience="小型餐饮门店店长",
                    pain="食材采购量难以预测，经常买少导致菜品缺货",
                    context="每周制定食材采购计划",
                    desired="减少因采购不足造成的缺货",
                ),
            ),
            (
                602,
                _idea(
                    audience="餐厅顾客",
                    pain="高峰期到店后等待座位时间太长",
                    context="周末到店就餐",
                    desired="减少现场等位时间",
                ),
            ),
        ),
        PainRelation.RELATED,
        SolutionRelation.NOT_APPLICABLE,
        DuplicateVerdict.RELATED,
        601,
    ),
    ProbeCase(
        "novel_same_industry",
        "同行业但核心痛点不同",
        _comparison(
            _idea(
                audience="餐饮门店店长",
                pain="员工临时请假后很难快速重新排班",
                context="每日安排门店班次",
                desired="快速找到可替班员工",
            ),
            (
                701,
                _idea(
                    audience="餐饮门店店长",
                    pain="食材临近过期时容易遗漏",
                    context="检查后厨库存",
                    desired="减少食材浪费",
                ),
            ),
            (
                702,
                _idea(
                    audience="餐饮门店店长",
                    pain="顾客差评分散在多个平台难以汇总",
                    context="复盘门店服务质量",
                    desired="集中查看顾客反馈",
                ),
            ),
        ),
        PainRelation.DIFFERENT,
        SolutionRelation.NOT_APPLICABLE,
        DuplicateVerdict.NOVEL,
        None,
    ),
    ProbeCase(
        "novel_different_payer",
        "付费方和使用约束发生变化",
        _comparison(
            _idea(
                audience="个人自由职业者",
                pain="个人消费票据太多，报税时难以整理",
                context="年度个人税务申报",
                desired="整理个人可抵扣票据",
            ),
            (
                801,
                _idea(
                    audience="企业财务部门",
                    pain="员工报销发票信息填写错误导致审核返工",
                    context="公司内部费用报销",
                    desired="减少企业报销审核时间",
                ),
            ),
            (
                802,
                _idea(
                    audience="小企业老板",
                    pain="无法快速查看每月经营现金流",
                    context="月末经营复盘",
                    desired="了解企业收支变化",
                ),
            ),
        ),
        PainRelation.DIFFERENT,
        SolutionRelation.NOT_APPLICABLE,
        DuplicateVerdict.NOVEL,
        None,
    ),
    ProbeCase(
        "novel_surface_keywords",
        "只有表面关键词相同",
        _comparison(
            _idea(
                audience="视力较弱的患者",
                pain="诊所预约页面字体太小，难以独立完成预约",
                context="使用手机预约门诊",
                desired="更容易看清并操作预约页面",
            ),
            (
                901,
                _idea(
                    audience="诊所预约管理员",
                    pain="患者预约后经常爽约",
                    context="安排每日门诊号源",
                    desired="降低预约爽约率",
                ),
            ),
            (
                902,
                _idea(
                    audience="医院患者",
                    pain="到院后不知道当前排队进度",
                    context="门诊候诊区等待",
                    desired="查看实时叫号位置",
                ),
            ),
        ),
        PainRelation.DIFFERENT,
        SolutionRelation.NOT_APPLICABLE,
        DuplicateVerdict.NOVEL,
        None,
    ),
)


def build_chat_completions_url(base_url: str) -> str:
    """把常规 Base URL 转换为 Chat Completions 端点。"""

    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ProbeFailure("AI_BASE_URL 不能为空")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def classify_http_error(status_code: int) -> str:
    """将常见 HTTP 状态转换成安全错误分类。"""

    if status_code in {401, 403}:
        return "鉴权失败"
    if status_code == 404:
        return "Base URL、接口路径或 Model ID 不存在"
    if status_code in {400, 422}:
        return "请求参数或 json_object 模式不受支持"
    if status_code == 429:
        return "请求被限流或余额不足"
    if status_code >= 500:
        return "模型服务内部错误"
    return "HTTP 请求失败"


def _parse_response(
    response: httpx.Response,
    case: ProbeCase,
    elapsed_seconds: float,
) -> ProbeCaseResult:
    try:
        body = response.json()
    except ValueError as exc:
        raise ProbeFailure("服务端没有返回合法 JSON 响应") from exc
    if not isinstance(body, dict):
        raise ProbeFailure("服务端响应顶层必须是对象")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProbeFailure("服务端响应缺少 choices[0]")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise ProbeFailure("模型输出因长度限制被截断")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ProbeFailure("服务端响应缺少 message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProbeFailure("模型没有返回可校验的 JSON 内容")
    try:
        output = validate_duplicate_judgment_json(content, case.comparison)
    except ValidationError as exc:
        raise ProbeFailure(f"模型输出未通过查重 Schema：{exc.error_count()} 个错误") from exc

    usage = body.get("usage")
    total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
    request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
    return ProbeCaseResult(
        output=output,
        elapsed_seconds=elapsed_seconds,
        request_id=request_id,
        total_tokens=total_tokens if isinstance(total_tokens, int) else None,
    )


def send_case(
    settings: ProbeSettings,
    case: ProbeCase,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ProbeCaseResult:
    """发送一次无重试的查重探测请求。"""

    endpoint = build_chat_completions_url(settings.base_url)
    headers = {
        "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    payload = build_duplicate_payload(
        settings.model_id,
        case.comparison,
        temperature=settings.temperature,
    )
    started_at = perf_counter()
    try:
        with httpx.Client(timeout=settings.timeout_seconds, transport=transport) as client:
            response = client.post(endpoint, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise ProbeFailure("请求超时") from exc
    except httpx.RequestError as exc:
        raise ProbeFailure("网络连接失败") from exc
    elapsed_seconds = perf_counter() - started_at

    if response.status_code >= 400:
        category = classify_http_error(response.status_code)
        safe_body = response.text[:1500].replace(settings.api_key.get_secret_value(), "***")
        raise ProbeFailure(f"{category}：HTTP {response.status_code}；响应：{safe_body}")
    return _parse_response(response, case, elapsed_seconds)


def check_behavior(case: ProbeCase, output: DuplicateJudgmentOutput) -> list[str]:
    """比较结构合法结果和固定案例预期。"""

    failures: list[str] = []
    if output.pain_relation is not case.expected_pain_relation:
        failures.append(
            f"pain_relation 期望 {case.expected_pain_relation.value}，"
            f"实际 {output.pain_relation.value}"
        )
    if output.solution_relation is not case.expected_solution_relation:
        failures.append(
            f"solution_relation 期望 {case.expected_solution_relation.value}，"
            f"实际 {output.solution_relation.value}"
        )
    if output.verdict is not case.expected_verdict:
        failures.append(f"verdict 期望 {case.expected_verdict.value}，实际 {output.verdict.value}")
    if output.matched_internal_id != case.expected_matched_internal_id:
        failures.append(
            f"matched_internal_id 期望 {case.expected_matched_internal_id}，"
            f"实际 {output.matched_internal_id}"
        )
    return failures


def run_probe(
    settings: ProbeSettings,
    *,
    show_output: bool,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """依次运行九个固定案例并返回稳定退出码。"""

    behavior_failures: list[str] = []
    total_elapsed = 0.0
    total_tokens = 0
    has_token_usage = True
    request_ids: list[str] = []

    for index, case in enumerate(PROBE_CASES, start=1):
        try:
            result = send_case(settings, case, transport=transport)
        except ProbeFailure as exc:
            print(f"[FAIL] {index}/9 {case.label}：{exc}")
            return 1

        total_elapsed += result.elapsed_seconds
        if result.total_tokens is None:
            has_token_usage = False
        else:
            total_tokens += result.total_tokens
        if result.request_id is not None:
            request_ids.append(result.request_id)

        failures = check_behavior(case, result.output)
        status = "PASS" if not failures else "FAIL"
        print(f"[{status}] {index}/9 {case.label}，耗时 {result.elapsed_seconds:.2f}s")
        for failure in failures:
            behavior_failures.append(f"{case.case_id}：{failure}")
            print(f"  - {failure}")
        if show_output:
            print(result.output.model_dump_json(indent=2))

    print(f"总耗时：{total_elapsed:.2f}s")
    print(f"Token 用量：{total_tokens if has_token_usage else '服务端未完整返回'}")
    print(f"请求 ID：{', '.join(request_ids) if request_ids else '服务端未返回'}")
    if behavior_failures:
        failed_case_ids = {item.split("：")[0] for item in behavior_failures}
        print(f"[FAIL] {len(PROBE_CASES) - len(failed_case_ids)}/9 个案例通过")
        return 2
    print("[PASS] 9/9 个固定中文查重案例全部通过")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="探测生成模型的固定中文查重判定能力")
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="打印已经通过 Schema 校验的结构化输出",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = ProbeSettings()
    except ValidationError as exc:
        print("配置错误：请在 backend/.env 中设置 AI_BASE_URL、AI_API_KEY 和 AI_MODEL_ID。")
        print(exc)
        return 1

    print(f"模型：{settings.model_id}")
    print(f"端点：{build_chat_completions_url(settings.base_url)}")
    print("固定中文案例：9 个；每个案例单独请求；不自动重试")
    return run_probe(settings, show_output=args.show_output)


if __name__ == "__main__":
    sys.exit(main())
