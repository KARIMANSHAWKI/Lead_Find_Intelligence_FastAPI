from app.domain.models.client_context import ClientContext
from app.domain.models.company import Company
from app.domain.models.company_research import ResearchEvidence
from app.domain.models.prospect_analysis import ProspectAnalysis
from app.domain.ports.llm import LLMPort


class FakeLLM(LLMPort):
    def __init__(
        self, result: ProspectAnalysis, responses: dict[str, ProspectAnalysis | Exception] | None = None
    ) -> None:
        self.result = result
        self.responses = responses or {}
        self.calls: list[tuple[Company, ClientContext, list[ResearchEvidence]]] = []

    async def select_companies_for_research(
        self,
        companies: list[Company],
        client_context: ClientContext,
        limit: int,
    ) -> list[str]:
        return [company.name for company in companies[:limit]]

    async def analyze_company(
        self, company: Company, client_context: ClientContext,
        evidence: list[ResearchEvidence],
    ) -> ProspectAnalysis:
        self.calls.append((company, client_context, evidence))
        result = self.responses.get(company.name, self.result)
        if isinstance(result, Exception):
            raise result
        return result.model_copy(deep=True)
