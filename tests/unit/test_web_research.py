import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import ProviderError, ProviderResponseError, ProviderTimeoutError
from app.domain.models.company import Company
from app.infrastructure.research.web_search_provider import WebSearchResearchProvider, _public_ip


def run(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    resolver = AsyncMock(return_value="93.184.216.34")
    return asyncio.run(WebSearchResearchProvider(client=client, resolver=resolver, **kwargs).research(
        Company(name="Example", website="https://example.com")))


def test_maps_official_pages_and_bounds_budget():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(200, headers={"content-type":"text/html"}, text='<a href="/careers">Careers</a><a href="https://linkedin.com/company/x">Social</a><script>invented fact</script>')
        return httpx.Response(200, headers={"content-type":"text/html"}, text='<p>The company currently lists 18 open roles across operations and sales.</p>')
    result = run(handler, max_pages=2, max_evidence=1)
    assert len(result.evidence) == 1
    assert result.evidence[0].source_url == "https://example.com/careers"
    assert result.evidence[0].source_type == "careers"
    assert len(calls) == 3
    assert "invented" not in result.evidence[0].text


def test_robots_disallow_no_pages():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="User-agent: *\nDisallow: /", headers={"content-type":"text/plain"})
    assert run(handler).evidence == []
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_robots_failure_not_treated_as_empty(status):
    with pytest.raises(ProviderError):
        run(lambda request: httpx.Response(status))


def test_timeout_translated():
    def handler(request):
        raise httpx.ReadTimeout("secret", request=request)
    with pytest.raises(ProviderTimeoutError, match="timed out"):
        run(handler)


def test_private_dns_rejected(monkeypatch):
    loop = asyncio.new_event_loop()
    async def check():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=[(None,None,None,None,("127.0.0.1",80))]))
        with pytest.raises(ProviderResponseError):
            await _public_ip("example.com", 80)
    loop.run_until_complete(check())
    loop.close()


def test_redirect_to_private_address_is_rejected():
    with pytest.raises(ProviderResponseError):
        run(lambda request: httpx.Response(302, headers={"location":"http://127.0.0.1/"}))


def test_public_redirects_are_followed_with_revalidation():
    calls = []

    def handler(request):
        calls.append(request)
        if request.headers["host"] == "example.com":
            return httpx.Response(
                301,
                headers={"location": f"https://www.example.com{request.url.path}"},
            )
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<p>We are hiring for multiple open positions across our growing team.</p>",
        )

    result = run(handler)

    assert len(result.evidence) == 1
    assert {request.headers["host"] for request in calls} == {
        "example.com",
        "www.example.com",
    }


def test_body_budget():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, headers={"content-type":"text/html"}, content=b'x' * 250001)
    assert run(handler).evidence == []


def test_all_page_failures_report_provider_unavailable():
    def handler(request):
        return httpx.Response(404 if request.url.path == "/robots.txt" else 503)
    with pytest.raises(ProviderError, match="unavailable"):
        run(handler)


def test_careers_evidence_prioritized_over_homepage():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        body = '<p>We provide general services and software for our customers.</p><a href="/careers">Jobs</a>' if request.url.path == "/" else '<p>We currently advertise 18 open roles in our operations team.</p>'
        return httpx.Response(200, headers={"content-type":"text/html"}, text=body)
    result = run(handler, max_evidence=1)
    assert result.evidence[0].source_type == "careers"
