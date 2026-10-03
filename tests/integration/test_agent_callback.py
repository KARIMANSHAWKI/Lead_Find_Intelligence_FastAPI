from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_run_lead_intelligence
from app.api.v1.agent_routes import get_callback_client
from app.application.dto.response import RunAgentResponse
from app.core.config import Settings
from app.core.exceptions import CompanySearchInputError, ProviderError, ProviderResponseError, ProviderTimeoutError
from app.infrastructure.result_callback import ResultCallbackClient
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def payload():
    return {
        "run_id": 25,
        "client": {"product": "Recruiting software", "target_industries": ["Software"], "location": "Egypt", "company_size": {}},
        "callback": {
            "url": "http://dashboard.test/api/v1/agent/runs/25/result",
            "token": "a" * 64,
        },
    }


def application(use_case, delivery):
    app = create_app(Settings(_env_file=None, laravel_callback_base_url="http://dashboard.test"))
    app.dependency_overrides[get_run_lead_intelligence] = lambda: use_case
    app.dependency_overrides[get_callback_client] = lambda: delivery
    return app


def test_callback_request_acknowledges_and_delivers_result(payload):
    use_case = AsyncMock()
    use_case.execute.return_value = RunAgentResponse(run_id=25, prospects=[])
    delivery = AsyncMock()
    with TestClient(application(use_case, delivery)) as client:
        response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 202, response.text
    assert response.json() == {"run_id": 25, "status": "running"}
    use_case.execute.assert_awaited_once()
    delivery.send.assert_awaited_once_with(
        payload["callback"]["url"], "a" * 64,
        {"run_id": 25, "prospects": [], "status": "completed"},
    )


@pytest.mark.parametrize("error,code", [
    (CompanySearchInputError("private-provider-details"), "invalid_icp"),
    (ProviderError("private-provider-details"), "service_unavailable"),
    (ProviderTimeoutError("private-provider-details"), "timeout"),
    (ProviderResponseError("private-provider-details"), "invalid_response"),
    (RuntimeError("private-provider-details"), "research_failed"),
])
def test_research_failure_delivers_safe_failure(payload, error, code):
    use_case = AsyncMock()
    use_case.execute.side_effect = error
    delivery = AsyncMock()
    with TestClient(application(use_case, delivery)) as client:
        assert client.post("/api/v1/agent/run", json=payload).status_code == 202
    delivery.send.assert_awaited_once_with(payload["callback"]["url"], "a" * 64,
        {"run_id": 25, "status": "failed", "error_code": code})


@pytest.mark.parametrize("url", [
    "http://other.test/api/v1/agent/runs/25/result",
    "http://dashboard.test/api/v1/agent/runs/26/result",
    "http://dashboard.test/api/v1/agent/runs/25/result?token=unsafe",
    "http://username:password@dashboard.test/api/v1/agent/runs/25/result",
    "http://dashboard.test/private",
])
def test_callback_cannot_target_arbitrary_services(payload, url):
    use_case, delivery = AsyncMock(), AsyncMock()
    payload["callback"]["url"] = url
    with TestClient(application(use_case, delivery)) as client:
        assert client.post("/api/v1/agent/run", json=payload).status_code == 422
    use_case.execute.assert_not_awaited()
    delivery.send.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("statuses,attempts,success", [([200], 1, True), ([503, 200], 2, True), ([503, 503, 503], 3, False), ([302], 1, False), ([401], 1, False)])
async def test_delivery_authentication_retries_and_no_redirects(monkeypatch, statuses, attempts, success):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(statuses.pop(0), headers={"Location": "http://untrusted.test"})
    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.infrastructure.result_callback.httpx.AsyncClient",
        lambda **options: real_client(transport=httpx.MockTransport(handler), **options))
    monkeypatch.setattr("app.infrastructure.result_callback.asyncio.sleep", AsyncMock())
    assert await ResultCallbackClient().send("http://dashboard.test/result", "secret-token", {"run_id": 25}) is success
    assert len(requests) == attempts
    assert all(request.headers["Authorization"] == "Bearer secret-token" for request in requests)
    assert all(request.url.host == "dashboard.test" for request in requests)


@pytest.mark.anyio
async def test_connection_failure_has_bounded_retries(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        raise httpx.ConnectError("private-network-details", request=request)
    real_client = httpx.AsyncClient
    monkeypatch.setattr("app.infrastructure.result_callback.httpx.AsyncClient",
        lambda **options: real_client(transport=httpx.MockTransport(handler), **options))
    monkeypatch.setattr("app.infrastructure.result_callback.asyncio.sleep", AsyncMock())
    assert await ResultCallbackClient().send("http://dashboard.test/result", "secret-token", {"run_id": 25}) is False
    assert len(requests) == 3
