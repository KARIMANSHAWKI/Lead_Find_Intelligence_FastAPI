import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from app.agents.lead_intelligence_agent import LeadIntelligenceAgent
from app.application.dto.request import RunAgentRequest
from app.application.use_cases.run_lead_intelligence import RunLeadIntelligence
from app.core.exceptions import (
    AgentUnavailableError, ProviderAuthenticationError, ProviderError,
    ProviderRateLimitError, ProviderResponseError, ProviderTimeoutError, LLMResponseValidationError,
)
from app.domain.models.client_context import ClientContext
from app.domain.models.buying_signal import BuyingSignal
from app.domain.models.company import Company
from app.domain.models.contact_info import CompanyEmail, ContactInfo, PersonContact
from app.domain.models.prospect_analysis import ProspectAnalysis
from tests.fakes.fake_company_search import FakeCompanySearch
from tests.fakes.fake_llm import FakeLLM
from tests.fakes.fake_web_research import FakeWebResearch
from app.domain.models.company_research import CompanyResearch, ResearchEvidence

EVIDENCE = ResearchEvidence(text="The company currently lists 18 open roles.", source_url="https://example.com/careers")

def researcher():
    return FakeWebResearch(CompanyResearch(company_name="Example", evidence=[EVIDENCE]))


@pytest.fixture
def context():
    return ClientContext(product="Recruitment", target_industries=["Software"],
                         location="Egypt", company_size={"min": 50, "max": 300})


@pytest.fixture
def analysis():
    return ProspectAnalysis(icp_fit="high", product_relevance="high",
                            why_now="Insufficient evidence to establish buying timing.",
                            buying_signals=[BuyingSignal(type="hiring", evidence=EVIDENCE.text, source_url=EVIDENCE.source_url, strength="high")], evidence_quality="high")


def execute(companies, context, analysis, responses=None):
    search = FakeCompanySearch(companies)
    llm = FakeLLM(analysis, responses)
    result = asyncio.run(LeadIntelligenceAgent(search, llm, researcher()).run(context, 7))
    return result, search, llm


def test_ports_receive_icp_and_candidate_data(context, analysis):
    company = Company(name="Example", industry="Software", employee_count=100, location="Egypt")
    result, search, llm = execute([company], context, analysis)
    assert search.calls == [(["Software"], "Egypt", 50, 300, 10)]
    assert llm.calls == [(company, context, [EVIDENCE])]
    assert result[0].company_name == "Example"
    assert result[0].buying_signals[0].source_url == EVIDENCE.source_url
    assert EVIDENCE.text in result[0].why_now
    assert "score" not in result[0].model_dump()


@pytest.mark.parametrize(("fit", "relevance", "included"), [
    ("high", "high", True), ("high", "medium", True), ("high", "low", False),
    ("medium", "high", False), ("low", "high", False),
])
def test_qualification_rule(fit, relevance, included, context, analysis):
    analysis = analysis.model_copy(update={"icp_fit": fit, "product_relevance": relevance})
    result, _, _ = execute([Company(name="Example")], context, analysis)
    assert bool(result) == included


@pytest.mark.parametrize("fields", [
    {"industry": "Retail"}, {"employee_count": 49}, {"employee_count": 301},
    {"location": "Germany"},
    {"location": "DE"}, {"location": "Berlin, Germany"},
])
def test_clear_mismatches_skip_llm(fields, context, analysis):
    result, _, llm = execute([Company(name="Example", **fields)], context, analysis)
    assert result == [] and llm.calls == []


@pytest.mark.parametrize("fields", [
    {}, {"employee_count": 50}, {"employee_count": 300},
    {"industry": "Software Development"}, {"location": "Cairo, Egypt"},
    {"location": "EG"},
    {"location": "Cairo"},
])
def test_unknown_and_compatible_values_are_analyzed(fields, context, analysis):
    result, _, llm = execute([Company(name="Example", **fields)], context, analysis)
    assert len(result) == 1 and len(llm.calls) == 1


def test_city_alone_is_not_treated_as_wrong_country(context, analysis):
    context.location = "Germany"
    result, _, llm = execute([Company(name="Example", location="Berlin")], context, analysis)
    assert len(result) == 1 and len(llm.calls) == 1


@pytest.mark.parametrize("second", [
    Company(name=" example "),
    Company(name="Another", website="http://www.example.com/about"),
    Company(name="Another", source="test", external_id="123"),
])
def test_duplicates_are_analyzed_once(second, context, analysis):
    first = Company(name="Example", website="https://example.com", source="test", external_id="123")
    result, _, llm = execute([first, second], context, analysis)
    assert len(result) == 1 and len(llm.calls) == 1


@pytest.mark.parametrize("error", [ProviderResponseError("invalid"), ProviderTimeoutError("timeout"), RuntimeError("bad")])
def test_one_company_failure_continues(error, context, analysis, caplog):
    caplog.set_level(logging.INFO)
    result, _, llm = execute([Company(name="Bad"), Company(name="Good")], context, analysis, {"Bad": error})
    assert [item.company_name for item in result] == ["Good"]
    assert len(llm.calls) == 2
    assert any(record.message == "company_analysis_failed" for record in caplog.records)


@pytest.mark.parametrize("error", [ProviderAuthenticationError("secret"), ProviderRateLimitError("secret")])
def test_global_failures_abort(error, context, analysis):
    with pytest.raises(type(error)):
        execute([Company(name="Example")], context, analysis, {"Example": error})


def test_all_operational_failures_are_unavailable(context, analysis):
    with pytest.raises(AgentUnavailableError):
        execute([Company(name="Example")], context, analysis, {"Example": ProviderTimeoutError("secret")})


def test_search_failure_aborts(context, analysis):
    search = FakeCompanySearch([], error=ProviderError("search failed"))
    with pytest.raises(ProviderError):
        asyncio.run(LeadIntelligenceAgent(search, FakeLLM(analysis), researcher()).run(context, 7))


def test_empty_search_does_not_call_llm(context, analysis):
    result, _, llm = execute([], context, analysis)
    assert result == [] and llm.calls == []


def test_candidate_limit_and_order(context, analysis):
    result, _, llm = execute([Company(name=f"Example {i}") for i in range(30)], context, analysis)
    assert len(llm.calls) == 10
    assert [item.company_name for item in result] == [f"Example {i}" for i in range(10)]


def test_fabricated_signal_is_rejected(context, analysis):
    analysis.buying_signals = [BuyingSignal(type="hiring_growth", evidence="Invented jobs",
                                          source_url=None, strength="high")]
    with pytest.raises(LLMResponseValidationError):
        execute([Company(name="Example")], context, analysis)


def test_fabricated_high_evidence_quality_is_rejected(context, analysis):
    analysis.evidence_quality = "low"
    result, _, _ = execute([Company(name="Example")], context, analysis)
    assert result == []


def test_run_use_case_calls_agent(context):
    agent = AsyncMock(spec=LeadIntelligenceAgent)
    agent.run.return_value = []
    request = RunAgentRequest(run_id=9, client=context)
    response = asyncio.run(RunLeadIntelligence(agent).execute(request))
    agent.run.assert_awaited_once_with(context, 9)
    assert response.model_dump() == {"run_id": 9, "prospects": []}


def test_logs_are_structured_without_error_secrets(context, analysis, caplog):
    caplog.set_level(logging.INFO)
    execute([Company(name="Bad"), Company(name="Good")], context, analysis,
            {"Bad": ProviderResponseError("sensitive-key")})
    assert "sensitive-key" not in caplog.text
    records = [record for record in caplog.records if record.name.endswith("lead_intelligence_agent")]
    assert all(record.run_id == 7 for record in records)
    assert records[-1].prospect_count == 1


def test_research_calls_and_evidence_budget(context, analysis):
    research = researcher()
    llm = FakeLLM(analysis)
    companies = [Company(name="Wrong", industry="Retail"), Company(name="Good"), Company(name="Good")]
    result = asyncio.run(LeadIntelligenceAgent(FakeCompanySearch(companies), llm, research).run(context, 1))
    assert [item.name for item in research.calls] == ["Good"]
    assert llm.calls[0][2] == [EVIDENCE]
    assert result[0].buying_signals[0].source_url == research.result.evidence[0].source_url


def test_no_evidence_skips_llm(context, analysis):
    research = FakeWebResearch(CompanyResearch(company_name="Example"))
    llm = FakeLLM(analysis)
    assert asyncio.run(LeadIntelligenceAgent(FakeCompanySearch([Company(name="Example")]), llm, research).run(context, 1)) == []
    assert llm.calls == []


def test_research_failure_isolated(context, analysis):
    research = FakeWebResearch(CompanyResearch(company_name="Example", evidence=[EVIDENCE]),
                               {"Bad": ProviderTimeoutError("secret")})
    result = asyncio.run(LeadIntelligenceAgent(FakeCompanySearch([Company(name="Bad"), Company(name="Good")]),
                                               FakeLLM(analysis), research).run(context, 1))
    assert [item.company_name for item in result] == ["Good"]


def test_all_research_timeouts_fail_clearly(context, analysis):
    research = FakeWebResearch(CompanyResearch(company_name="Example"), {"Bad": ProviderTimeoutError("secret")})
    with pytest.raises(AgentUnavailableError):
        asyncio.run(LeadIntelligenceAgent(FakeCompanySearch([Company(name="Bad")]), FakeLLM(analysis), research).run(context, 1))


def test_generated_unsupported_why_now_is_not_published(context, analysis):
    analysis.why_now = "Invented funding yesterday"
    result, _, _ = execute([Company(name="Example")], context, analysis)
    assert "funding" not in result[0].why_now
    assert EVIDENCE.text in result[0].why_now


def test_use_case_returns_researched_opportunity(context, analysis):
    agent = LeadIntelligenceAgent(FakeCompanySearch([Company(name="Example")]), FakeLLM(analysis), researcher())
    result = asyncio.run(RunLeadIntelligence(agent).execute(RunAgentRequest(run_id=8, client=context)))
    assert result.run_id == 8
    assert result.prospects[0].buying_signals[0].evidence == EVIDENCE.text
    assert "score" not in result.prospects[0].model_dump()


def test_qualified_prospect_is_enriched_with_contacts(context, analysis):
    contact_provider = AsyncMock()
    contact_provider.find_contacts.return_value = ContactInfo(
        company_emails=[CompanyEmail(email="info@example.com")],
        company_phone_numbers=["+20 100 000 0000"],
        people=[
            PersonContact(
                first_name="Mona",
                last_name="Ali",
                email="mona@example.com",
                position="HR Director",
            )
        ],
    )
    company = Company(name="Example", website="https://example.com")
    agent = LeadIntelligenceAgent(
        FakeCompanySearch([company]),
        FakeLLM(analysis),
        researcher(),
        contact_enrichment=contact_provider,
        contact_people_limit=3,
    )

    result = asyncio.run(agent.run(context, 10))

    contact_provider.find_contacts.assert_awaited_once_with(
        company,
        people_limit=3,
    )
    assert result[0].contact_info.company_emails[0].email == "info@example.com"
    assert result[0].contact_info.people[0].position == "HR Director"


def test_evidence_without_source_is_not_analyzed(context, analysis):
    research = FakeWebResearch(CompanyResearch(company_name="Example", evidence=[ResearchEvidence(text="A fact with no URL")]))
    llm = FakeLLM(analysis)
    assert asyncio.run(LeadIntelligenceAgent(FakeCompanySearch([Company(name="Example")]), llm, research).run(context, 1)) == []
    assert not llm.calls


def test_distinct_branches_are_not_collapsed(context, analysis):
    context.target_industries = ["Restaurants"]
    context.company_size.min = None
    context.company_size.max = None
    companies = [Company(name="Same Restaurant", industry="Restaurant", website="https://chain.example",
                         location=f"Branch {i}, Cairo, Egypt", source="google_places", external_id=f"place-{i}")
                 for i in range(2)]
    result, _, llm = execute(companies, context, analysis)
    assert len(result) == 2 and len(llm.calls) == 2


def test_one_website_failure_does_not_make_no_evidence_a_global_outage(context, analysis):
    research = FakeWebResearch(CompanyResearch(company_name="Example"), {"Bad":ProviderError("website down")})
    result = asyncio.run(LeadIntelligenceAgent(FakeCompanySearch([Company(name="Bad"),Company(name="Empty")]),
                                              FakeLLM(analysis),research).run(context,1))
    assert result == []
