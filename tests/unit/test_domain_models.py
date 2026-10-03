import pytest
from pydantic import ValidationError

from app.application.dto.response import ProspectResult
from app.domain.models.buying_signal import BuyingSignal
from app.domain.models.client_context import ClientContext
from app.domain.models.company import Company
from app.domain.models.company_research import CompanyResearch, ResearchEvidence
from app.domain.models.prospect import Prospect


def test_company_optional_fields_and_size():
    company = Company(name=" Example Company ")
    assert company.name == "Example Company"
    assert company.website is None
    assert company.employee_count is None
    assert Company(name="Example", employee_count=0).employee_count == 0
    complete = Company(
        name="Example", website="https://example.com", industry="Logistics",
        location="Egypt", employee_count=50, source="hunter", external_id="123",
    )
    assert Company.model_validate(complete.model_dump()) == complete


@pytest.mark.parametrize("fields", [{"name": " "}, {"name": "Example", "employee_count": -1}])
def test_invalid_company(fields):
    with pytest.raises(ValidationError):
        Company(**fields)


def test_prospect_and_signal_validation():
    signal = BuyingSignal(
        type="hiring_growth", evidence="Published job listing",
        source_url=None, strength="high",
    )
    prospect = Prospect(
        company_name="Example", website=None, icp_fit="high",
        product_relevance="medium", why_now="The company is hiring.",
        buying_signals=[signal],
    )
    assert ProspectResult.model_validate(prospect.model_dump()).buying_signals == [signal]
    assert "score" not in prospect.model_dump()
    for field, value in [("icp_fit", "excellent"), ("why_now", " ")]:
        with pytest.raises(ValidationError):
            Prospect.model_validate({**prospect.model_dump(), field: value})
    for field, value in [("type", ""), ("evidence", " "), ("strength", "strong")]:
        with pytest.raises(ValidationError):
            BuyingSignal.model_validate({**signal.model_dump(), field: value})


def test_research_evidence_keeps_source_and_allows_no_findings():
    evidence = ResearchEvidence(text="Hiring announcement", source_url="https://example.com/jobs")
    result = CompanyResearch(company_name="Example", evidence=[evidence])
    assert result.evidence[0].source_url == "https://example.com/jobs"
    assert CompanyResearch(company_name="Example").evidence == []
    assert result.summary is None
    assert ResearchEvidence(text="Public information").source_url is None
    assert ResearchEvidence(text="Public information", source_type="news").source_type == "news"
    for field in ["text", "source_url"]:
        with pytest.raises(ValidationError):
            ResearchEvidence.model_validate({**evidence.model_dump(), field: " "})
    with pytest.raises(ValidationError):
        CompanyResearch(company_name=" ")


def test_domain_client_context_validates_size_range():
    context = {
        "product": "Recruitment", "target_industries": ["Logistics"],
        "location": "Egypt", "company_size": {"min": 10, "max": 50},
    }
    assert ClientContext.model_validate(context).company_size.min == 10
    with pytest.raises(ValidationError, match="must not be greater"):
        ClientContext.model_validate({**context, "company_size": {"min": 51, "max": 50}})
