from abc import ABC, abstractmethod

from app.domain.models.company import Company


class CompanySearchPort(ABC):
    """Contract implemented by an infrastructure company-search adapter."""

    @abstractmethod
    async def search(
        self,
        industries: list[str],
        location: str,
        min_size: int | None = None,
        max_size: int | None = None,
        limit: int = 20,
    ) -> list[Company]:
        """Discover candidates; [] means no matches. Size filters may be approximate."""
        raise NotImplementedError
