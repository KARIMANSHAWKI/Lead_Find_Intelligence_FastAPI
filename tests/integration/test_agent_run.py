from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import (
    get_company_search_provider,
    get_contact_enrichment_provider,
    get_llm,
    get_web_research_provider,
)
from app.application.dto.response import RunAgentResponse
from app.domain.models.company import Company
from app.domain.models.contact_info import ContactInfo
from app.domain.models.prospect_analysis import ProspectAnalysis
from tests.fakes.fake_company_search import FakeCompanySearch
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_web_research import FakeWebResearch
from app.domain.models.company_research import CompanyResearch, ResearchEvidence
from app.domain.models.buying_signal import BuyingSignal
from app.core.config import Settings
from app.core.exceptions import CompanySearchInputError, ProviderAuthenticationError, ProviderError, ProviderRateLimitError
from app.main import create_app


@pytest.fixture
def client():
    application = create_app(Settings(_env_file=None))
    search = FakeCompanySearch([Company(name="Test Software", website="https://test.example")])
    evidence = ResearchEvidence(text="The company currently lists 18 open roles.", source_url="https://test.example/careers")
    application.dependency_overrides[get_web_research_provider] = lambda: FakeWebResearch(CompanyResearch(company_name="Test Software", evidence=[evidence]))
    llm = FakeLLM(ProspectAnalysis(
        icp_fit="high", product_relevance="high", why_now="Insufficient timing evidence.",
        buying_signals=[BuyingSignal(type="hiring", evidence=evidence.text, source_url=evidence.source_url, strength="high")], evidence_quality="high",
    ))
    application.dependency_overrides[get_company_search_provider] = lambda: search
    contact_enrichment = AsyncMock()
    contact_enrichment.find_contacts.return_value = ContactInfo()
    application.dependency_overrides[get_contact_enrichment_provider] = (
        lambda: contact_enrichment
    )
    application.dependency_overrides[get_llm] = lambda: llm
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def payload():
    return {
        "run_id": 42,
        "client": {
            "product": "Recruitment Management Software",
            "target_industries": ["Software", "Logistics"],
            "location": "Egypt",
            "company_size": {"min": 50, "max": 300},
            "ideal_customer_description": "Companies actively growing their teams",
        },
    }


def test_successful_agent_run(client, payload):
    response = client.post("/api/v1/agent/run", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == 42
    assert len(data["prospects"]) == 1
    prospect = data["prospects"][0]
    assert prospect["company_name"] == "Test Software"
    assert prospect["website"] == "https://test.example"
    assert prospect["icp_fit"] == "high"
    assert prospect["buying_signals"][0]["source_url"] == "https://test.example/careers"
    assert "18 open roles" in prospect["why_now"]
    assert "score" not in prospect
    assert client.post("/api/v1/agent/run", json=payload).json() == response.json()


def test_response_schema(client, payload):
    data = client.post("/api/v1/agent/run", json=payload).json()
    result = RunAgentResponse.model_validate(data)
    assert result.run_id == payload["run_id"]
    assert result.prospects[0].buying_signals

    invalid = deepcopy(data)
    invalid["prospects"][0]["icp_fit"] = "excellent"
    with pytest.raises(ValidationError):
        RunAgentResponse.model_validate(invalid)

    data["prospects"][0]["website"] = None
    RunAgentResponse.model_validate(data)

    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/agent/run"]["post"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RunAgentResponse"
    }


def test_missing_product(client, payload):
    del payload["client"]["product"]
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "client", "product"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_industries", []),
        ("target_industries", [" "]),
        ("product", ""),
        ("product", "   "),
        ("location", ""),
        ("location", "   "),
        ("company_size", {"min": -1, "max": 300}),
        ("company_size", {"min": 50, "max": -1}),
        ("company_size", {"min": 301, "max": 300}),
    ],
)
def test_invalid_client_context(client, payload, field, value):
    payload["client"][field] = value
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:3] == ["body", "client", field]


@pytest.mark.parametrize("run_id", [0, -1, 1.5, "invalid", None])
def test_invalid_run_id(client, payload, run_id):
    payload["run_id"] = run_id
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "run_id"]


@pytest.mark.parametrize(
    "company_size",
    [{}, {"min": None, "max": None}, {"min": 0}, {"max": 300}, {"min": 50, "max": 50}],
)
def test_optional_fields_and_valid_size_boundaries(client, payload, company_size):
    payload["client"]["company_size"] = company_size
    del payload["client"]["ideal_customer_description"]
    assert client.post("/api/v1/agent/run", json=payload).status_code == 200


def test_empty_search_returns_empty_prospects(client, payload):
    client.app.dependency_overrides[get_company_search_provider] = lambda: FakeCompanySearch([])
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 200
    assert response.json() == {"run_id": 42, "prospects": []}


@pytest.mark.parametrize(("error", "status"), [
    (ProviderError("sensitive-provider-details"), 502),
    (CompanySearchInputError("sensitive-provider-details"), 422),
])
def test_search_errors_are_safe_http_responses(client, payload, error, status):
    client.app.dependency_overrides[get_company_search_provider] = lambda: FakeCompanySearch([], error=error)
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == status
    assert "sensitive-provider-details" not in response.text


def test_global_llm_failure_is_safe_http_error(client, payload):
    result = ProspectAnalysis(icp_fit="high", product_relevance="high", why_now="Unknown timing",
                              buying_signals=[], evidence_quality="low")
    client.app.dependency_overrides[get_llm] = lambda: FakeLLM(
        result, {"Test Software": ProviderAuthenticationError("sensitive-key")},
    )
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 502
    assert "sensitive-key" not in response.text


@pytest.mark.parametrize("provider", ["search", "llm"])
def test_provider_rate_limit_has_actionable_safe_response(client, payload, provider):
    error = ProviderRateLimitError("sensitive-provider-details")
    if provider == "search":
        client.app.dependency_overrides[get_company_search_provider] = lambda: FakeCompanySearch([], error=error)
    else:
        result = ProspectAnalysis(icp_fit="high", product_relevance="high", why_now="Unknown timing",
                                  buying_signals=[], evidence_quality="low")
        client.app.dependency_overrides[get_llm] = lambda: FakeLLM(result, {"Test Software": error})
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 503
    assert "rate limit" in response.json()["detail"]
    assert "sensitive-provider-details" not in response.text


@pytest.mark.parametrize("missing", ["hunter", "openai"])
def test_missing_configuration_fails_clearly_and_health_still_works(missing, payload):
    settings = Settings(_env_file=None,
                        hunter_api_key=None if missing == "hunter" else "test-key",
                        openai_api_key=None if missing == "openai" else "test-key")
    with TestClient(create_app(settings)) as test_client:
        response = test_client.post("/api/v1/agent/run", json=payload)
        assert response.status_code == 503
        assert "configuration" in response.json()["detail"]
        assert test_client.get("/health").status_code == 200


@pytest.mark.parametrize("industry,size,provider", [
    ("Software", {"min":50,"max":300}, "hunter"),
    ("Restaurants", {}, "places"),
    ("Dental Clinics", {}, "places"),
])
def test_actual_resolver_drives_researched_api_flow(client, payload, monkeypatch, industry, size, provider):
    from unittest.mock import AsyncMock
    from app.infrastructure.company_search.hunter_provider import HunterCompanySearchProvider
    from app.infrastructure.company_search.google_places_provider import GooglePlacesCompanySearchProvider
    from app.core.config import Settings
    client.app.state.settings = Settings(_env_file=None, hunter_api_key="test", google_places_api_key="test")
    del client.app.dependency_overrides[get_company_search_provider]
    category = {"Restaurants":"Restaurant", "Dental Clinics":"Dentist"}.get(industry, industry)
    candidate = Company(name="Test Software", website="https://test.example", industry=category,
                        location="Cairo, Egypt", external_id="place-id", source=provider)
    hunter_search = AsyncMock(return_value=[candidate])
    places_search = AsyncMock(return_value=[candidate])
    monkeypatch.setattr(HunterCompanySearchProvider, "search", hunter_search)
    monkeypatch.setattr(GooglePlacesCompanySearchProvider, "search", places_search)
    payload["client"].update(target_industries=[industry], company_size=size)
    response = client.post("/api/v1/agent/run", json=payload)
    assert response.status_code == 200
    assert response.json()["prospects"][0]["buying_signals"][0]["source_url"] == "https://test.example/careers"
    assert (hunter_search.await_count, places_search.await_count) == ((1,0) if provider=="hunter" else (0,1))
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/api/v1/agent/run"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref":"#/components/schemas/RunAgentRequest"}


def test_missing_places_key_does_not_fall_back_to_hunter(client, payload):
    client.app.state.settings = Settings(_env_file=None, hunter_api_key="test", google_places_api_key=None)
    del client.app.dependency_overrides[get_company_search_provider]
    payload["client"].update(target_industries=["Restaurants"], company_size={})
    assert client.post("/api/v1/agent/run", json=payload).status_code == 503


def test_all_invalid_llm_analyses_return_specific_safe_error(client, payload):
    from app.core.exceptions import LLMResponseValidationError
    result = ProspectAnalysis(icp_fit="high",product_relevance="high",why_now="Unknown",buying_signals=[],evidence_quality="low")
    client.app.dependency_overrides[get_llm] = lambda: FakeLLM(result, {"Test Software":LLMResponseValidationError("sensitive-details")})
    response=client.post("/api/v1/agent/run",json=payload)
    assert response.status_code==502
    assert "invalid or unsupported evidence" in response.json()["detail"]
    assert "sensitive-details" not in response.text
