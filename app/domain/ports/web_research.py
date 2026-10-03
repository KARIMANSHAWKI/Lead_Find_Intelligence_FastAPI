from abc import ABC, abstractmethod

from app.domain.models.company import Company
from app.domain.models.company_research import CompanyResearch


class WebResearchPort(ABC):
    """Contract implemented by an infrastructure research adapter."""

    @abstractmethod
    async def research(self, company: Company) -> CompanyResearch:
        """Retrieve structured public evidence for one company."""
        raise NotImplementedError
