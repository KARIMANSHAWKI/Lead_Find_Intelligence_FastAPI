import re

import httpx
import pycountry
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from app.core.exceptions import (
    CompanySearchInputError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.domain.models.company import Company
from app.domain.models.types import NonEmptyString
from app.domain.ports.company_search import CompanySearchPort


class _DiscoverCompany(BaseModel):
    model_config = ConfigDict(strict=True)

    organization: NonEmptyString
    domain: NonEmptyString


class _DiscoverResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    data: list[_DiscoverCompany]


_HEADCOUNT_BANDS = (
    ("1-10", 1, 10), ("11-50", 11, 50), ("51-200", 51, 200),
    ("201-500", 201, 500), ("501-1000", 501, 1000),
    ("1001-5000", 1001, 5000), ("5001-10000", 5001, 10000),
    ("10001+", 10001, float("inf")),
)
_INDUSTRY_ALIASES = {
    "software": "Software Development",
    "logistics": "Transportation, Logistics, Supply Chain and Storage",
}


class HunterCompanySearchProvider(CompanySearchPort):
    """Discover one page (up to 100) using documented Hunter filters.

    Size bands overlap the requested interval, so size matching is approximate.
    Locations must be a country name/code or 'City, Country'. Industry labels
    are passed through except the explicit Software/Logistics aliases above.
    No enrichment is performed: Discover does not return firmographic fields.
    """

    def __init__(
        self,
        api_key: SecretStr | None,
        base_url: str = "https://api.hunter.io",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Hunter requires HUNTER_API_KEY.")
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/v2/discover"
        self._client = client

    async def search(
        self,
        industries: list[str],
        location: str,
        min_size: int | None = None,
        max_size: int | None = None,
        limit: int = 20,
    ) -> list[Company]:
        body = self._filters(industries, location, min_size, max_size, limit)
        if body is None:  # Hunter has no band for zero employees.
            return []
        try:
            if self._client is not None:
                response = await self._post(self._client, body)
            else:
                async with httpx.AsyncClient() as client:
                    response = await self._post(client, body)
        except httpx.TimeoutException:
            raise ProviderTimeoutError("Hunter company search timed out.") from None
        except httpx.RequestError:
            raise ProviderError("Hunter company search network request failed.") from None

        self._check_status(response)
        try:
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("errors"):
                raise ValueError
            result = _DiscoverResponse.model_validate(payload)
            companies = []
            for item in result.data:
                domain = item.domain.encode("idna").decode("ascii").lower()
                if len(domain) > 253 or not re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", domain
                ):
                    raise ValueError
                companies.append(Company(
                    name=item.organization, website=f"https://{domain}",
                    source="hunter", external_id=domain,
                ))
            return companies[:limit]
        except (ValueError, ValidationError, UnicodeError):
            raise ProviderResponseError("Hunter returned an invalid Discover response.") from None

    async def _post(self, client: httpx.AsyncClient, body: dict) -> httpx.Response:
        return await client.post(
            self._url,
            headers={"X-API-KEY": self._api_key.get_secret_value()},
            json=body,
            timeout=20.0,
        )

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise ProviderAuthenticationError("Hunter authentication failed; check HUNTER_API_KEY.")
        if response.status_code == 403:
            # Hunter also uses 403 for plan/access failures, not just rate limits.
            try:
                errors = response.json().get("errors", [])
                access_denied = any(error.get("id") == "no_discover_access" for error in errors)
            except (ValueError, AttributeError, TypeError):
                access_denied = True
            if access_denied:
                raise ProviderError("Hunter Discover access denied; check account permissions and plan.")
            raise ProviderRateLimitError("Hunter company search rate limit reached.")
        if response.status_code == 429:
            raise ProviderRateLimitError("Hunter company search rate or usage limit reached.")
        if response.status_code != 200:
            raise ProviderError(f"Hunter company search failed (HTTP {response.status_code}).")

    @staticmethod
    def _filters(
        industries: list[str], location: str,
        min_size: int | None, max_size: int | None, limit: int,
    ) -> dict | None:
        if not industries or any(not isinstance(value, str) or not value.strip() for value in industries):
            raise CompanySearchInputError("At least one non-empty industry is required.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise CompanySearchInputError("Company search limit must be between 1 and 100.")
        for value in (min_size, max_size):
            if value is not None and (type(value) is not int or value < 0):
                raise CompanySearchInputError("Company sizes must be non-negative integers.")
        if min_size is not None and max_size is not None and min_size > max_size:
            raise CompanySearchInputError("min_size must not be greater than max_size.")
        if not isinstance(location, str) or not location.strip():
            raise CompanySearchInputError("A country or 'City, Country' location is required.")
        parts = [part.strip() for part in location.rsplit(",", 1)]
        if any(not part for part in parts):
            raise CompanySearchInputError("Use a country or 'City, Country' location.")
        try:
            country = pycountry.countries.lookup(parts[-1])
        except LookupError:
            raise CompanySearchInputError(
                "Location country is unknown; use a country name/code or 'City, Country'."
            ) from None
        headquarters = {"country": country.alpha_2}
        if len(parts) == 2:
            headquarters["city"] = parts[0]
        labels = list(dict.fromkeys(
            _INDUSTRY_ALIASES.get(value.strip().casefold(), value.strip()) for value in industries
        ))
        body = {
            "industry": {"include": labels},
            "headquarters_location": {"include": [headquarters]},
        }
        if min_size is not None or max_size is not None:
            bands = [
                label for label, lower, upper in _HEADCOUNT_BANDS
                if upper >= (min_size if min_size is not None else 0)
                and lower <= (max_size if max_size is not None else float("inf"))
            ]
            if not bands:
                return None
            body["headcount"] = bands
        # Omit limit/offset: Hunter restricts changing pagination to Premium.
        return body
