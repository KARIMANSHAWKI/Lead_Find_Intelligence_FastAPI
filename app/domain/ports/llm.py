from abc import ABC, abstractmethod

from app.domain.models.client_context import ClientContext
from app.domain.models.company import Company
from app.domain.models.company_research import ResearchEvidence
from app.domain.models.prospect_analysis import ProspectAnalysis


class LLMPort(ABC):
    """Contract implemented by an infrastructure LLM adapter."""

    @abstractmethod
    async def select_companies_for_research(
        self,
        companies: list[Company],
        client_context: ClientContext,
        limit: int,
    ) -> list[str]:
        """Use tool calling to choose which filtered candidates merit research."""
        raise NotImplementedError

    @abstractmethod
    async def analyze_company(
        self, company: Company, client_context: ClientContext,
        evidence: list[ResearchEvidence],
    ) -> ProspectAnalysis:
        """Interpret supplied company data and evidence without retrieving facts."""
        raise NotImplementedError
