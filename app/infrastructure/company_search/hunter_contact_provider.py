from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.core.exceptions import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.domain.models.company import Company
from app.domain.models.contact_info import CompanyEmail, ContactInfo, PersonContact
from app.domain.ports.contact_enrichment import ContactEnrichmentPort


class _Verification(BaseModel):
    status: str | None = None


class _HunterEmail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str
    type: str
    confidence: int | None = Field(default=None, ge=0, le=100)
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None
    seniority: str | None = None
    department: str | None = None
    decision_maker: bool | None = None
    linkedin: str | None = None
    phone_number: str | None = None
    verification: _Verification | None = None


class _DomainData(BaseModel):
    emails: list[_HunterEmail] = Field(default_factory=list)


class _DomainResponse(BaseModel):
    data: _DomainData


class HunterContactProvider(ContactEnrichmentPort):
    """Use one Hunter Domain Search call per qualified prospect."""

    def __init__(
        self,
        api_key: SecretStr | None,
        base_url: str = "https://api.hunter.io",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Hunter requires HUNTER_API_KEY.")
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/v2/domain-search"
        self._client = client

    async def find_contacts(
        self,
        company: Company,
        people_limit: int = 3,
    ) -> ContactInfo:
        if people_limit < 1:
            return ContactInfo()
        domain = self._domain(company.website)
        if domain is None:
            return ContactInfo()

        try:
            if self._client is not None:
                response = await self._get(self._client, domain)
            else:
                async with httpx.AsyncClient() as client:
                    response = await self._get(client, domain)
        except httpx.TimeoutException:
            raise ProviderTimeoutError("Hunter contact search timed out.") from None
        except httpx.RequestError:
            raise ProviderError("Hunter contact search network request failed.") from None

        self._check_status(response)
        try:
            payload = _DomainResponse.model_validate(response.json())
        except (ValueError, ValidationError):
            raise ProviderResponseError(
                "Hunter returned an invalid Domain Search response."
            ) from None

        return self._map_contacts(payload.data.emails, people_limit)

    async def _get(self, client: httpx.AsyncClient, domain: str) -> httpx.Response:
        return await client.get(
            self._url,
            headers={"X-API-KEY": self._api_key.get_secret_value()},
            params={"domain": domain, "limit": 10},
            timeout=20.0,
        )

    @staticmethod
    def _domain(website: str | None) -> str | None:
        if not website:
            return None
        parsed = urlsplit(website if "://" in website else f"https://{website}")
        if not parsed.hostname:
            return None
        return parsed.hostname.casefold().removeprefix("www.")

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise ProviderAuthenticationError(
                "Hunter authentication failed; check HUNTER_API_KEY."
            )
        if response.status_code in {403, 429}:
            raise ProviderRateLimitError("Hunter contact search limit reached.")
        if response.status_code != 200:
            raise ProviderError(
                f"Hunter contact search failed (HTTP {response.status_code})."
            )

    @staticmethod
    def _map_contacts(
        emails: list[_HunterEmail],
        people_limit: int,
    ) -> ContactInfo:
        generic: list[CompanyEmail] = []
        people: list[PersonContact] = []
        phone_numbers: list[str] = []
        seen_emails: set[str] = set()

        ranked = sorted(
            emails,
            key=lambda item: (
                item.type != "personal",
                item.decision_maker is not True,
                item.seniority not in {"executive", "senior"},
                -(item.confidence or 0),
            ),
        )
        for item in ranked:
            email = item.value.strip().casefold()
            if (
                not email
                or email in seen_emails
                or "@" not in email
                or any(character.isspace() for character in email)
            ):
                continue
            seen_emails.add(email)
            verification = (
                item.verification.status if item.verification is not None else None
            )
            if item.type == "generic":
                if len(generic) < 3:
                    generic.append(
                        CompanyEmail(
                            email=email,
                            confidence=item.confidence,
                            verification_status=verification,
                        )
                    )
                if item.phone_number and item.phone_number not in phone_numbers:
                    phone_numbers.append(item.phone_number)
                continue
            if item.type != "personal" or len(people) >= people_limit:
                continue
            people.append(
                PersonContact(
                    first_name=item.first_name,
                    last_name=item.last_name,
                    email=email,
                    position=item.position,
                    seniority=item.seniority,
                    department=item.department,
                    linkedin_url=item.linkedin,
                    phone_number=item.phone_number,
                    confidence=item.confidence,
                    verification_status=verification,
                )
            )

        return ContactInfo(
            company_emails=generic,
            company_phone_numbers=phone_numbers[:3],
            people=people,
        )
