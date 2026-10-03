import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import (
    CompanySearchInputError, ProviderAuthenticationError, ProviderError,
    ProviderRateLimitError, ProviderResponseError, ProviderTimeoutError,
)
from app.domain.models.company import Company
from app.domain.ports.company_search import CompanySearchPort
from app.infrastructure.company_search.hunter_provider import HunterCompanySearchProvider


def run_search(handler, **parameters):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider: CompanySearchPort = HunterCompanySearchProvider(
                SecretStr("test-secret"), base_url="https://hunter.test/", client=client,
            )
            return await provider.search(**{
                "industries": ["Software"], "location": "Egypt", **parameters,
            })
    return asyncio.run(execute())


def response(request):
    return httpx.Response(200, json={"data": [{
        "organization": "Example", "domain": "example.com",
        "emails_count": {"total": 18},
    }]})


def test_documented_filters_and_mapping():
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://hunter.test/v2/discover"
        assert request.headers["X-API-KEY"] == "test-secret"
        assert request.extensions["timeout"]["read"] == 20
        assert json.loads(request.content) == {
            "industry": {"include": [
                "Software Development", "Transportation, Logistics, Supply Chain and Storage",
            ]},
            "headquarters_location": {"include": [{"country": "EG"}]},
            "headcount": ["11-50", "51-200", "201-500"],
        }
        return response(request)

    companies = run_search(handler, industries=["Software", "Logistics"], min_size=50, max_size=300)
    assert companies == [Company(
        name="Example", website="https://example.com", source="hunter", external_id="example.com",
    )]
    assert companies[0].employee_count is None  # Email counts are not employees.
    assert companies[0].industry is None
    assert companies[0].location is None


@pytest.mark.parametrize(("location", "expected"), [
    ("Egypt", {"country": "EG"}), ("eg", {"country": "EG"}),
    ("United States", {"country": "US"}),
    ("Cairo, Egypt", {"city": "Cairo", "country": "EG"}),
])
def test_location_mapping(location, expected):
    def handler(request):
        assert json.loads(request.content)["headquarters_location"] == {"include": [expected]}
        return response(request)
    run_search(handler, location=location)


def test_industry_labels_pass_through_and_aliases_are_deduplicated():
    def handler(request):
        assert json.loads(request.content)["industry"] == {
            "include": ["Software Development", "Financial Services"],
        }
        return response(request)
    run_search(handler, industries=[" Software ", "Software Development", "Financial Services"])


@pytest.mark.parametrize(("minimum", "maximum", "bands"), [
    (None, None, None), (0, 10, ["1-10"]), (11, 50, ["11-50"]),
    (50, 50, ["11-50"]), (51, 200, ["51-200"]),
    (None, 50, ["1-10", "11-50"]), (10001, None, ["10001+"]),
    (5001, None, ["5001-10000", "10001+"]),
])
def test_size_band_mapping(minimum, maximum, bands):
    def handler(request):
        body = json.loads(request.content)
        assert body.get("headcount") == bands
        assert "limit" not in body and "offset" not in body
        return response(request)
    run_search(handler, min_size=minimum, max_size=maximum)


def test_zero_employee_search_returns_empty_without_http():
    def handler(request):
        pytest.fail("Zero employees cannot match any Hunter band")
    assert run_search(handler, min_size=0, max_size=0) == []


@pytest.mark.parametrize("parameters", [
    {"industries": []}, {"industries": [" "]}, {"location": ""},
    {"location": "Cairo"}, {"location": "Cairo,"},
    {"min_size": -1}, {"max_size": -1}, {"min_size": 301, "max_size": 300},
    {"min_size": True}, {"max_size": 1.5}, {"limit": 0}, {"limit": 101},
])
def test_invalid_inputs_fail_before_http(parameters):
    def handler(request):
        pytest.fail("Invalid inputs must not call Hunter")
    with pytest.raises(CompanySearchInputError):
        run_search(handler, **parameters)


def test_empty_discover_response_is_a_normal_no_matches_result():
    assert run_search(lambda request: httpx.Response(200, json={"data": []})) == []


def test_limit_is_enforced_locally():
    def handler(request):
        return httpx.Response(200, json={"data": [
            {"organization": f"Example {i}", "domain": f"example{i}.com"} for i in range(5)
        ]})
    assert len(run_search(handler, limit=2)) == 2


@pytest.mark.parametrize("payload", [
    {}, {"data": None}, {"data": {}}, {"data": [{}]},
    {"data": [{"organization": " ", "domain": "example.com"}]},
    {"data": [{"organization": 12, "domain": "example.com"}]},
    {"data": [{"organization": "Example", "domain": "https://example.com"}]},
    {"data": [{"organization": "Example", "domain": "example.com/path"}]},
    {"data": [{"organization": "Example", "domain": None}]},
    {"data": [], "errors": [{"details": "secret vendor error"}]},
])
def test_invalid_payload_is_a_safe_provider_error(payload):
    with pytest.raises(ProviderResponseError, match="invalid Discover response") as error:
        run_search(lambda request: httpx.Response(200, json=payload))
    assert "secret" not in str(error.value)


def test_non_json_response():
    with pytest.raises(ProviderResponseError):
        run_search(lambda request: httpx.Response(200, text="not JSON"))


def test_provider_closes_its_owned_http_client(monkeypatch):
    client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)
    provider = HunterCompanySearchProvider(SecretStr("test-secret"))
    assert asyncio.run(provider.search(["Software"], "Egypt"))[0].name == "Example"
    assert client.is_closed


@pytest.mark.parametrize(("status", "payload", "expected"), [
    (401, {}, ProviderAuthenticationError),
    (403, {"errors": [{"id": "rate_limit"}]}, ProviderRateLimitError),
    (403, {"errors": [{"id": "no_discover_access"}]}, ProviderError),
    (429, {}, ProviderRateLimitError), (400, {}, CompanySearchInputError), (500, {}, ProviderError),
])
def test_http_errors_are_translated(status, payload, expected):
    with pytest.raises(expected) as error:
        run_search(lambda request: httpx.Response(status, json=payload))
    assert "test-secret" not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.parametrize(("exception", "expected"), [
    (httpx.ReadTimeout, ProviderTimeoutError),
    (httpx.ConnectTimeout, ProviderTimeoutError),
    (httpx.ConnectError, ProviderError),
])
def test_network_errors_and_timeouts_are_translated(exception, expected):
    def handler(request):
        raise exception("secret vendor details", request=request)
    with pytest.raises(expected) as error:
        run_search(handler)
    assert "secret" not in str(error.value)
    assert error.value.__cause__ is None


def test_marketing_industry_aliases_use_supported_labels():
    def handler(request):
        assert json.loads(request.content) == {
            "industry": {"include": ["Advertising Services", "Marketing Services"]},
            "headquarters_location": {"include": [{"country": "EG"}]},
            "headcount": ["1-10", "11-50", "51-200"],
        }
        return response(request)
    run_search(handler, industries=["Advertising Services", "Marketing SErvice", " marketing services "],
        min_size=1, max_size=200)


def test_rejected_filters_do_not_expose_vendor_error_details():
    with pytest.raises(CompanySearchInputError, match="rejected the ICP filters") as error:
        run_search(lambda request: httpx.Response(400, json={"errors": [
            {"id": "invalid_industry", "details": "private-provider-secret"},
        ]}))
    assert "private-provider-secret" not in str(error.value)
