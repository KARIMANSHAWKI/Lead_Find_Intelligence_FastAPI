import asyncio

import httpx
import pytest
from pydantic import SecretStr

from app.core.exceptions import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.domain.models.company import Company
from app.infrastructure.company_search.hunter_contact_provider import (
    HunterContactProvider,
)


def run(handler, website="https://example.com", people_limit=3):
    async def execute():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = HunterContactProvider(
                SecretStr("test-secret"),
                base_url="https://hunter.test",
                client=client,
            )
            return await provider.find_contacts(
                Company(name="Example", website=website),
                people_limit=people_limit,
            )

    return asyncio.run(execute())


def test_maps_generic_and_ranked_person_contacts():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/v2/domain-search"
        assert request.url.params["domain"] == "example.com"
        assert request.url.params["limit"] == "10"
        assert request.headers["X-API-KEY"] == "test-secret"
        return httpx.Response(
            200,
            json={
                "data": {
                    "emails": [
                        {
                            "value": "info@example.com",
                            "type": "generic",
                            "confidence": 80,
                            "phone_number": "+1 555 0100",
                            "verification": {"status": "valid"},
                        },
                        {
                            "value": "employee@example.com",
                            "type": "personal",
                            "confidence": 99,
                            "first_name": "Regular",
                            "last_name": "Employee",
                            "decision_maker": False,
                        },
                        {
                            "value": "leader@example.com",
                            "type": "personal",
                            "confidence": 90,
                            "first_name": "Lead",
                            "last_name": "Buyer",
                            "position": "Chief People Officer",
                            "seniority": "executive",
                            "department": "hr",
                            "decision_maker": True,
                            "linkedin": "https://linkedin.com/in/lead-buyer",
                            "verification": {"status": "valid"},
                        },
                    ]
                }
            },
        )

    result = run(handler, people_limit=1)

    assert result.company_emails[0].email == "info@example.com"
    assert result.company_phone_numbers == ["+1 555 0100"]
    assert len(result.people) == 1
    assert result.people[0].email == "leader@example.com"
    assert result.people[0].position == "Chief People Officer"


def test_missing_website_returns_empty_without_request():
    def handler(request):
        pytest.fail("Hunter must not be called without a company website")

    assert run(handler, website=None).model_dump() == {
        "company_emails": [],
        "company_phone_numbers": [],
        "people": [],
    }


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderRateLimitError),
        (429, ProviderRateLimitError),
        (500, ProviderError),
    ],
)
def test_http_errors_are_translated(status, expected):
    with pytest.raises(expected):
        run(lambda request: httpx.Response(status))


def test_invalid_response_is_rejected():
    with pytest.raises(ProviderResponseError):
        run(lambda request: httpx.Response(200, json={"data": None}))


def test_timeout_is_translated():
    def handler(request):
        raise httpx.ReadTimeout("private details", request=request)

    with pytest.raises(ProviderTimeoutError):
        run(handler)
