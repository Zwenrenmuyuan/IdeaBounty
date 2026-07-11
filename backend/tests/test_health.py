from fastapi.testclient import TestClient

from idea_bounty.main import create_app


def test_health_returns_service_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "idea-bounty-api"}


def test_health_is_documented_in_openapi() -> None:
    with TestClient(create_app()) as client:
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert openapi_response.status_code == 200

    health_operation = openapi_response.json()["paths"]["/api/health"]["get"]
    response_schema = health_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/HealthResponse"}
