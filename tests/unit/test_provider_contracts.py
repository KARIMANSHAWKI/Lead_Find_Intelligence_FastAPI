import asyncio
import inspect

import pytest

from app.domain.models.company import Company
from app.domain.models.company_research import CompanyResearch, ResearchEvidence
from app.domain.ports.company_search import CompanySearchPort
from app.domain.ports.web_research import WebResearchPort
from app.infrastructure.company_search.hunter_provider import HunterCompanySearchProvider
from app.infrastructure.research.web_search_provider import WebSearchResearchProvider
from tests.fakes.fake_company_search import FakeCompanySearch
from tests.fakes.fake_web_research import FakeWebResearch


@pytest.mark.parametrize(
    ("implementation", "port", "method"),
    [
        (HunterCompanySearchProvider, CompanySearchPort, "search"),
        (FakeCompanySearch, CompanySearchPort, "search"),
        (WebSearchResearchProvider, WebResearchPort, "research"),
        (FakeWebResearch, WebResearchPort, "research"),
    ],
)
def test_implementations_match_async_port_signature(implementation, port, method):
    assert issubclass(implementation, port)
    assert not inspect.isabstract(implementation)
    assert inspect.iscoroutinefunction(getattr(implementation, method))
    assert inspect.signature(getattr(implementation, method)) == inspect.signature(getattr(port, method))


@pytest.mark.parametrize("port", [CompanySearchPort, WebResearchPort])
def test_ports_cannot_be_instantiated(port):
    with pytest.raises(TypeError):
        port()


def test_company_search_fake_returns_typed_results_and_records_arguments():
    company = Company(name="Example")
    provider: CompanySearchPort = FakeCompanySearch([company])
    assert asyncio.run(provider.search(["Logistics"], "Egypt", 50, 300)) == [company]
    assert provider.calls == [(["Logistics"], "Egypt", 50, 300, 20)]
    assert asyncio.run(FakeCompanySearch([]).search(["Software"], "Egypt")) == []


def test_research_fake_returns_structured_evidence():
    company = Company(name="Example")
    result = CompanyResearch(
        company_name=company.name,
        evidence=[ResearchEvidence(text="Job listing", source_url="https://example.com/jobs")],
    )
    provider: WebResearchPort = FakeWebResearch(result)
    assert asyncio.run(provider.research(company)) == result
    assert provider.calls == [company]


def test_company_without_website_has_no_research_evidence():
    result = asyncio.run(WebSearchResearchProvider().research(Company(name="Example")))
    assert result.evidence == []
