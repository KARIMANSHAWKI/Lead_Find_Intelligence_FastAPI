from app.domain.models.company import Company
from app.domain.ports.company_search import CompanySearchPort


class FakeCompanySearch(CompanySearchPort):
    def __init__(self, companies: list[Company], error: Exception | None = None) -> None:
        self.companies = companies
        self.error = error
        self.calls: list[tuple[list[str], str, int | None, int | None, int]] = []

    async def search(
        self,
        industries: list[str],
        location: str,
        min_size: int | None = None,
        max_size: int | None = None,
        limit: int = 20,
    ) -> list[Company]:
        self.calls.append((list(industries), location, min_size, max_size, limit))
        if self.error is not None:
            raise self.error
        return list(self.companies[:limit])
