import asyncio
import inspect
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.exceptions import (
    CompanySearchInputError, ProviderAuthenticationError, ProviderConfigurationError,
    ProviderError, ProviderRateLimitError, ProviderResponseError, ProviderTimeoutError,
)
from app.domain.models.client_context import ClientContext
from app.domain.ports.company_search import CompanySearchPort
from app.infrastructure.company_search.google_places_provider import GooglePlacesCompanySearchProvider
from app.infrastructure.company_search.hunter_provider import HunterCompanySearchProvider
from app.infrastructure.company_search.provider_resolver import CompanySearchProviderResolver


@pytest.mark.parametrize("industry,size,expected", [
    ("Software", {"min":50,"max":300}, HunterCompanySearchProvider),
    ("Logistics", {"min":1}, HunterCompanySearchProvider),
    ("Restaurants", {}, GooglePlacesCompanySearchProvider),
    ("Dental Clinics", {}, GooglePlacesCompanySearchProvider),
    ("Gyms", {}, GooglePlacesCompanySearchProvider),
    ("Unknown", {}, HunterCompanySearchProvider),
    ("Restaurants", {"max":300}, HunterCompanySearchProvider),
    ("  DENTAL   Clinics  ", {}, GooglePlacesCompanySearchProvider),
    ("Restaurants", {"min":0}, HunterCompanySearchProvider),
])
def test_resolver(industry, size, expected):
    context = ClientContext(product="Software", target_industries=[industry], location="Cairo", company_size=size)
    settings = Settings(_env_file=None, hunter_api_key="test", google_places_api_key="test")
    assert isinstance(CompanySearchProviderResolver(settings).resolve(context), expected)


def test_mixed_icp_defaults_to_hunter():
    context = ClientContext(product="Software",target_industries=["Restaurants","Software"],location="Cairo",company_size={})
    assert isinstance(CompanySearchProviderResolver(Settings(_env_file=None,hunter_api_key="test")).resolve(context), HunterCompanySearchProvider)


def test_selected_provider_only_requires_its_key():
    context = ClientContext(product="POS",target_industries=["Restaurants"],location="Cairo",company_size={})
    assert isinstance(CompanySearchProviderResolver(Settings(_env_file=None,google_places_api_key="test",hunter_api_key=None)).resolve(context), GooglePlacesCompanySearchProvider)
    with pytest.raises(ProviderConfigurationError, match="GOOGLE_PLACES_API_KEY"):
        CompanySearchProviderResolver(Settings(_env_file=None,google_places_api_key=None,hunter_api_key="test")).resolve(context)


def search(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GooglePlacesCompanySearchProvider(SecretStr("secret-test-key"), client=client)
    return asyncio.run(provider.search(**{"industries":["Dental Clinics"], "location":"Cairo, Egypt", **kwargs}))


def test_query_and_mapping():
    def handler(request):
        assert request.url == "https://places.googleapis.com/v1/places:searchText"
        assert request.headers["X-Goog-Api-Key"] == "secret-test-key"
        assert "websiteUri" in request.headers["X-Goog-FieldMask"]
        assert "rating" not in request.headers["X-Goog-FieldMask"]
        assert json.loads(request.content) == {"textQuery":"dental clinics in Cairo, Egypt","pageSize":2,"languageCode":"en"}
        return httpx.Response(200,json={"places":[{"id":"place-1","displayName":{"text":"Dental Clinic"},"websiteUri":"https://example.com","formattedAddress":"Cairo, Egypt","primaryTypeDisplayName":{"text":"Dentist"}}]})
    result = search(handler, limit=2)[0]
    assert result.name == "Dental Clinic"
    assert result.external_id == "place-1"
    assert result.employee_count is None
    assert result.source == "google_places"
    assert result.industry == "Dentist"
    assert result.website == "https://example.com"
    assert result.location == "Cairo, Egypt"


def test_missing_optional_fields():
    result = search(lambda request:httpx.Response(200,json={"places":[{"id":"x","displayName":{"text":"Example"}}]}))[0]
    assert result.website is None and result.industry is None and result.employee_count is None


@pytest.mark.parametrize("payload", [{}, {"places":[]}])
def test_empty_results(payload):
    assert search(lambda request:httpx.Response(200,json=payload)) == []


@pytest.mark.parametrize("payload", [[], None, {"error":{}}, {"unexpected":True}, {"places":None}, {"places":[{}]}, {"places":[{"id":"x","displayName":{"text":""}}]}])
def test_invalid_response(payload):
    with pytest.raises(ProviderResponseError):
        search(lambda request:httpx.Response(200,json=payload))


def test_non_json_response():
    with pytest.raises(ProviderResponseError):
        search(lambda request:httpx.Response(200,text="not JSON"))


@pytest.mark.parametrize("key", [None, "", " "])
def test_missing_key(key):
    with pytest.raises(ProviderConfigurationError, match="GOOGLE_PLACES_API_KEY"):
        GooglePlacesCompanySearchProvider(SecretStr(key) if key is not None else None)


@pytest.mark.parametrize("status,error", [(401,ProviderAuthenticationError),(403,ProviderAuthenticationError),(429,ProviderRateLimitError),(500,ProviderError)])
def test_http_errors(status,error):
    with pytest.raises(error) as caught:
        search(lambda request:httpx.Response(status,json={"error":{"message":"secret-test-key"}}))
    assert "secret-test-key" not in str(caught.value)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("secret",request=request)
    with pytest.raises(ProviderTimeoutError):
        search(handler)


@pytest.mark.parametrize("kwargs", [{"min_size":0},{"max_size":10},{"industries":[]},{"location":" "},{"limit":21},{"limit":0}])
def test_unsupported_filters(kwargs):
    def handler(request):
        pytest.fail("Invalid filters must not send HTTP requests")
    with pytest.raises(CompanySearchInputError):
        search(handler, **kwargs)


def test_multiple_categories_shared_budget_and_dedup():
    queries=[]
    def handler(request):
        payload=json.loads(request.content)
        queries.append(payload)
        places=[{"id":"a","displayName":{"text":"A"}}]
        if len(queries)>1:
            places.append({"id":"b","displayName":{"text":"B"}})
        return httpx.Response(200,json={"places":places})
    result=search(handler, industries=["Restaurants","Cafes"],limit=2)
    assert [item.external_id for item in result] == ["a","b"]
    assert [item["pageSize"] for item in queries] == [2,1]


def test_port_contract():
    assert issubclass(GooglePlacesCompanySearchProvider,CompanySearchPort)
    assert inspect.signature(GooglePlacesCompanySearchProvider.search)==inspect.signature(CompanySearchPort.search)


def test_settings_separate_places_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY","unrelated-key")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY","places-key")
    settings=Settings(_env_file=None)
    assert settings.google_places_api_key.get_secret_value()=="places-key"
    assert "places-key" not in repr(settings)
