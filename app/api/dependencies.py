from typing import Annotated

from fastapi import Depends, Request
from openai import AsyncOpenAI

from app.agents.lead_intelligence_agent import LeadIntelligenceAgent
from app.application.use_cases.run_lead_intelligence import RunLeadIntelligence
from app.core.config import Settings
from app.core.exceptions import LLMConfigurationError
from app.domain.ports.company_search import CompanySearchPort
from app.domain.ports.contact_enrichment import ContactEnrichmentPort
from app.domain.ports.llm import LLMPort
from app.domain.ports.web_research import WebResearchPort
from app.infrastructure.company_search.provider_resolver import CompanySearchProviderResolver
from app.infrastructure.company_search.hunter_contact_provider import HunterContactProvider
from app.application.dto.request import RunAgentRequest
from app.infrastructure.research.web_search_provider import WebSearchResearchProvider
from app.infrastructure.llm.openai_llm import OpenAILLM


def get_request_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_company_search_provider(
    settings: Annotated[Settings, Depends(get_request_settings)],
    request: RunAgentRequest,
) -> CompanySearchPort:
    return CompanySearchProviderResolver(settings).resolve(request.client)


def get_web_research_provider(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> WebResearchPort:
    return WebSearchResearchProvider(
        max_pages=settings.research_max_pages,
        max_evidence=settings.research_max_evidence,
    )


def get_contact_enrichment_provider(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> ContactEnrichmentPort:
    return HunterContactProvider(
        api_key=settings.hunter_api_key,
        base_url=str(settings.hunter_base_url),
    )


def get_openai_client(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> AsyncOpenAI:
    """Create OpenAI client from settings."""
    if settings.openai_api_key is None:
        raise LLMConfigurationError("OPENAI_API_KEY is required.")

    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
    )


def get_llm(
    client: Annotated[AsyncOpenAI, Depends(get_openai_client)],
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> LLMPort:
    return OpenAILLM(client=client, model=settings.openai_model)


def get_lead_intelligence_agent(
    company_search: Annotated[CompanySearchPort, Depends(get_company_search_provider)],
    contact_enrichment: Annotated[
        ContactEnrichmentPort,
        Depends(get_contact_enrichment_provider),
    ],
    llm: Annotated[LLMPort, Depends(get_llm)],
    web_research: Annotated[WebResearchPort, Depends(get_web_research_provider)],
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> LeadIntelligenceAgent:
    return LeadIntelligenceAgent(
        company_search=company_search,
        llm=llm,
        web_research=web_research,
        max_candidates=settings.agent_max_candidates,
        max_research=settings.agent_max_research,
        max_evidence=settings.research_max_evidence,
        contact_enrichment=contact_enrichment,
        contact_people_limit=settings.contact_max_people,
    )


def get_run_lead_intelligence(
    agent: Annotated[LeadIntelligenceAgent, Depends(get_lead_intelligence_agent)],
) -> RunLeadIntelligence:
    return RunLeadIntelligence(agent)
