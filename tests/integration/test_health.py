from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health() -> None:
    settings = Settings(_env_file=None, service_name="health-test-service")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "health-test-service"}


def test_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Configured Agent API")
    settings = Settings(_env_file=None)

    assert create_app(settings).title == "Configured Agent API"
