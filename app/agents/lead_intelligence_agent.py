import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.exceptions import (
    AgentUnavailableError,
    LLMResponseValidationError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.domain.models.buying_signal import BuyingSignal
from app.domain.models.client_context import ClientContext
from app.domain.models.company import Company
from app.domain.models.company_research import CompanyResearch, ResearchEvidence
from app.domain.models.contact_info import ContactInfo
from app.domain.models.prospect import Prospect
from app.domain.models.prospect_analysis import ProspectAnalysis
from app.domain.models.types import location_country_code
from app.domain.ports.company_search import CompanySearchPort
from app.domain.ports.contact_enrichment import ContactEnrichmentPort
from app.domain.ports.llm import LLMPort
from app.domain.ports.web_research import WebResearchPort

logger = logging.getLogger(__name__)


@dataclass
class _RunStats:
    completed_research: int = 0
    research_failures: int = 0
    analysis_attempts: int = 0
    successful_analyses: int = 0
    analysis_failures: int = 0
    invalid_analyses: int = 0


class LeadIntelligenceAgent:
    """Find and qualify evidence-supported prospects."""

    def __init__(
        self,
        company_search: CompanySearchPort,
        llm: LLMPort,
        web_research: WebResearchPort,
        max_candidates: int = 10,
        max_research: int = 10,
        max_evidence: int = 8,
        contact_enrichment: ContactEnrichmentPort | None = None,
        contact_people_limit: int = 3,
    ) -> None:
        self._company_search = company_search
        self._llm = llm
        self._web_research = web_research
        self._max_candidates = max_candidates
        self._max_research = max_research
        self._max_evidence = max_evidence
        self._contact_enrichment = contact_enrichment
        self._contact_people_limit = contact_people_limit

    async def run(
        self,
        client_context: ClientContext,
        run_id: int,
    ) -> list[Prospect]:
        """Run the complete lead-intelligence workflow sequentially."""
        context = {"run_id": run_id}
        stats = _RunStats()
        prospects: list[Prospect] = []
        seen: set[tuple[str, str]] = set()
        filtered: list[tuple[Company, dict]] = []

        logger.info("agent_run_started", extra=context)
        companies = await self._search_companies(client_context, context)
        print('###########################')
        print(companies)
        for index, company in enumerate(companies[: self._max_candidates]):
            company_context = {
                **context,
                "candidate_index": index,
                "company_name": company.name,
            }

            if self._should_skip_company(company, client_context, seen, company_context):
                continue
            filtered.append((company, company_context))

        selected_names = await self._select_research_candidates(
            [company for company, _ in filtered],
            client_context,
            context,
        )
        selected = set(selected_names)

        for company, company_context in filtered:
            if company.name not in selected:
                self._log_rejection(company_context, "not_selected_for_research")
                continue
            research = await self._research_company(company, company_context, stats)
            if research is None:
                continue

            evidence = self._extract_valid_evidence(research)
            logger.info(
                "company_research_completed",
                extra={**company_context, "evidence_count": len(evidence)},
            )
            if not evidence:
                self._log_rejection(company_context, "no_evidence")
                continue

            analysis = await self._analyze_company(
                company,
                client_context,
                evidence,
                company_context,
                stats,
            )
            if analysis is None:
                self._log_rejection(company_context, "analysis_failed")
                continue

            prospect = self._build_qualified_prospect(
                company,
                client_context,
                analysis,
                company_context,
            )
            if prospect is not None:
                prospect.contact_info = await self._find_contacts(
                    company,
                    company_context,
                )
                prospects.append(prospect)

        self._validate_run_result(stats)
        logger.info(
            "agent_run_completed",
            extra={
                **context,
                "prospect_count": len(prospects),
                "analysis_count": stats.successful_analyses,
            },
        )
        return prospects

    async def _select_research_candidates(
        self,
        companies: list[Company],
        client: ClientContext,
        context: dict,
    ) -> list[str]:
        if not companies:
            return []
        limit = min(self._max_research, len(companies))
        try:
            selected = await self._llm.select_companies_for_research(
                companies,
                client,
                limit,
            )
        except (
            ProviderConfigurationError,
            ProviderAuthenticationError,
            ProviderRateLimitError,
        ):
            raise
        except ProviderError as error:
            logger.warning(
                "research_selection_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            selected = [company.name for company in companies[:limit]]

        logger.info(
            "research_candidates_selected",
            extra={
                **context,
                "candidate_count": len(companies),
                "selected_count": len(selected),
            },
        )
        return selected

    async def _search_companies(
        self,
        client: ClientContext,
        context: dict,
    ) -> list[Company]:
        logger.info("company_search_started", extra=context)
        try:
            companies = await self._company_search.search(
                industries=client.target_industries,
                location=client.location,
                min_size=client.company_size.min,
                max_size=client.company_size.max,
                limit=self._max_candidates,
            )
        except Exception as error:
            logger.warning(
                "company_search_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            raise

        logger.info(
            "company_search_completed",
            extra={**context, "discovered_count": len(companies)},
        )
        return companies

    def _should_skip_company(
        self,
        company: Company,
        client: ClientContext,
        seen: set[tuple[str, str]],
        context: dict,
    ) -> bool:
        identities = self._identities(company)
        reason = "duplicate" if identities & seen else self._skip_reason(company, client)
        seen.update(identities)

        if reason:
            logger.info("company_skipped", extra={**context, "reason": reason})
            return True
        return False

    @staticmethod
    def _identities(company: Company) -> set[tuple[str, str]]:
        name = " ".join(company.name.casefold().split())
        location = " ".join((company.location or "").casefold().split())
        identities = {("name_location", f"{name}|{location}")}

        if company.website and not location:
            website = (
                company.website
                if "://" in company.website
                else f"https://{company.website}"
            )
            try:
                hostname = urlsplit(website).hostname
            except ValueError:
                hostname = None
            if hostname:
                identities.add(("website", hostname.casefold().removeprefix("www.")))

        if company.source and company.external_id:
            identities.add(("external_id", f"{company.source}:{company.external_id}"))
        return identities

    @staticmethod
    def _skip_reason(company: Company, client: ClientContext) -> str | None:
        count = company.employee_count
        if count is not None:
            if client.company_size.min is not None and count < client.company_size.min:
                return "employee_count_below_minimum"
            if client.company_size.max is not None and count > client.company_size.max:
                return "employee_count_above_maximum"

        if company.industry:
            company_words = LeadIntelligenceAgent._industry_words(company.industry)
            if not any(
                company_words & LeadIntelligenceAgent._industry_words(industry)
                for industry in client.target_industries
            ):
                return "wrong_industry"

        if company.location:
            actual = location_country_code(company.location)
            expected = location_country_code(client.location)
            if actual is not None and expected is not None and actual != expected:
                return "wrong_location"
        return None

    @staticmethod
    def _industry_words(value: str) -> set[str]:
        normalized = value.casefold().replace("dentist", "dental clinic")
        return {word.removesuffix("s") for word in re.findall(r"\w+", normalized)}

    async def _research_company(
        self,
        company: Company,
        context: dict,
        stats: _RunStats,
    ) -> CompanyResearch | None:
        logger.info("company_research_started", extra=context)
        try:
            research = await self._web_research.research(company)
            if research.company_name != company.name:
                raise ProviderResponseError("Research company identity mismatch.")
        except (
            ProviderConfigurationError,
            ProviderAuthenticationError,
            ProviderRateLimitError,
        ):
            raise
        except Exception as error:
            if isinstance(error, ProviderError) and not isinstance(
                error, ProviderResponseError
            ):
                stats.research_failures += 1
            logger.warning(
                "company_research_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            return None

        stats.completed_research += 1
        return research

    def _extract_valid_evidence(
        self,
        research: CompanyResearch,
    ) -> list[ResearchEvidence]:
        valid: list[ResearchEvidence] = []
        seen: set[tuple[str, str]] = set()

        for item in research.evidence:
            if not item.source_url:
                continue
            try:
                parsed = urlsplit(item.source_url)
            except ValueError:
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue

            identity = (item.text, item.source_url)
            if identity in seen:
                continue
            seen.add(identity)
            valid.append(item)
            if len(valid) == self._max_evidence:
                break
        return valid

    async def _analyze_company(
        self,
        company: Company,
        client: ClientContext,
        evidence: list[ResearchEvidence],
        context: dict,
        stats: _RunStats,
    ) -> ProspectAnalysis | None:
        stats.analysis_attempts += 1
        logger.info("company_analysis_started", extra=context)
        try:
            analysis = await self._llm.analyze_company(company, client, evidence)
            analysis.validate_evidence(evidence)
        except (
            ProviderConfigurationError,
            ProviderAuthenticationError,
            ProviderRateLimitError,
        ):
            raise
        except ProviderResponseError as error:
            stats.invalid_analyses += 1
            logger.warning(
                "company_analysis_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            return None
        except ProviderError as error:
            stats.analysis_failures += 1
            logger.warning(
                "company_analysis_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            return None
        except ValueError:
            stats.invalid_analyses += 1
            logger.warning("company_analysis_failed", extra=context)
            return None
        except Exception as error:
            logger.warning(
                "company_analysis_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            return None

        stats.successful_analyses += 1
        logger.info(
            "buying_signals_validated",
            extra={**context, "signal_count": len(analysis.buying_signals)},
        )
        return analysis

    def _build_qualified_prospect(
        self,
        company: Company,
        client: ClientContext,
        analysis: ProspectAnalysis,
        context: dict,
    ) -> Prospect | None:
        if analysis.icp_fit != "high":
            self._log_rejection(context, "weak_icp_fit")
            return None
        if analysis.product_relevance not in {"high", "medium"}:
            self._log_rejection(context, "weak_product_relevance")
            return None
        if analysis.evidence_quality == "low":
            self._log_rejection(context, "low_evidence_quality")
            return None

        signals = [
            signal
            for signal in analysis.buying_signals
            if signal.strength in {"high", "medium"}
        ]
        if not signals:
            self._log_rejection(context, "no_meaningful_verified_signal")
            return None

        prospect = Prospect(
            company_name=company.name,
            website=company.website,
            icp_fit=analysis.icp_fit,
            product_relevance=analysis.product_relevance,
            why_now=self._build_why_now(client, signals),
            buying_signals=signals,
        )
        logger.info(
            "company_qualified",
            extra={**context, "evidence_quality": analysis.evidence_quality},
        )
        return prospect

    async def _find_contacts(
        self,
        company: Company,
        context: dict,
    ) -> ContactInfo:
        if self._contact_enrichment is None:
            return ContactInfo()
        try:
            contacts = await self._contact_enrichment.find_contacts(
                company,
                people_limit=self._contact_people_limit,
            )
        except Exception as error:
            logger.warning(
                "contact_enrichment_failed",
                extra={**context, "error_type": type(error).__name__},
            )
            return ContactInfo()
        logger.info(
            "contact_enrichment_completed",
            extra={
                **context,
                "contact_count": (
                    len(contacts.people) + len(contacts.company_emails)
                ),
            },
        )
        return contacts

    @staticmethod
    def _build_why_now(
        client: ClientContext,
        signals: list[BuyingSignal],
    ) -> str:
        evidence = " ".join(signal.evidence for signal in signals[:3])
        return f"{evidence} These verified signals indicate a timely need for {client.product}."

    @staticmethod
    def _validate_run_result(stats: _RunStats) -> None:
        if (
            stats.analysis_attempts
            and stats.invalid_analyses == stats.analysis_attempts
        ):
            raise LLMResponseValidationError(
                "All company analyses failed evidence validation."
            )
        if stats.research_failures and not stats.completed_research:
            raise AgentUnavailableError("The research provider was unavailable.")
        if stats.analysis_failures and not stats.successful_analyses:
            raise AgentUnavailableError("The LLM provider was unavailable.")

    @staticmethod
    def _log_rejection(context: dict, reason: str) -> None:
        logger.info("company_rejected", extra={**context, "reason": reason})
