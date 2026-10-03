from app.domain.models.company import Company
from app.domain.models.company_research import CompanyResearch
from app.domain.ports.web_research import WebResearchPort


class FakeWebResearch(WebResearchPort):
    def __init__(self, result: CompanyResearch, responses: dict | None = None) -> None:
        self.result = result
        self.responses = responses or {}
        self.calls: list[Company] = []

    async def research(
        self, company: Company
    ) -> CompanyResearch:
        self.calls.append(company)
        result = self.responses.get(company.name, self.result)
        if isinstance(result, Exception):
            raise result
        return result.model_copy(deep=True, update={"company_name": company.name})
