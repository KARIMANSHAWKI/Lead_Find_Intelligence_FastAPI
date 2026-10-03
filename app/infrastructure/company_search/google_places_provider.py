import logging

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from app.core.exceptions import (
    CompanySearchInputError, ProviderAuthenticationError, ProviderConfigurationError,
    ProviderError, ProviderRateLimitError, ProviderResponseError, ProviderTimeoutError,
)
from app.domain.models.company import Company
from app.domain.models.types import NonEmptyString
from app.domain.ports.company_search import CompanySearchPort

logger = logging.getLogger(__name__)
_FIELD_MASK = "places.id,places.displayName,places.websiteUri,places.formattedAddress,places.primaryTypeDisplayName"


class _Text(BaseModel):
    text: NonEmptyString


class _Place(BaseModel):
    id: NonEmptyString
    displayName: _Text
    websiteUri: NonEmptyString | None = None
    formattedAddress: NonEmptyString | None = None
    primaryTypeDisplayName: _Text | None = None


class _Response(BaseModel):
    places: list[_Place] = Field(default_factory=list)


class GooglePlacesCompanySearchProvider(CompanySearchPort):
    def __init__(self, api_key: SecretStr | None, base_url: str = "https://places.googleapis.com",
                 client: httpx.AsyncClient | None = None) -> None:
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Google Places requires GOOGLE_PLACES_API_KEY.")
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/v1/places:searchText"
        self._client = client

    async def search(self, industries: list[str], location: str, min_size: int | None = None,
                     max_size: int | None = None, limit: int = 20) -> list[Company]:
        if min_size is not None or max_size is not None:
            raise CompanySearchInputError("Google Places does not support employee-count filters.")
        if not industries or any(not item.strip() for item in industries) or not location.strip() or not 1 <= limit <= 20:
            raise CompanySearchInputError("Places requires industries, location, and a limit from 1 to 20.")
        logger.info("google_places_search_started", extra={"provider": "google_places"})
        try:
            if self._client is not None:
                companies = await self._search(self._client, industries, location, limit)
            else:
                async with httpx.AsyncClient() as client:
                    companies = await self._search(client, industries, location, limit)
        except httpx.TimeoutException:
            logger.warning("google_places_search_failed", extra={"error_type": "ProviderTimeoutError"})
            raise ProviderTimeoutError("Google Places search timed out.") from None
        except httpx.RequestError:
            logger.warning("google_places_search_failed", extra={"error_type": "ProviderError"})
            raise ProviderError("Google Places connection failed.") from None
        except ProviderError as error:
            logger.warning("google_places_search_failed", extra={"error_type": type(error).__name__})
            raise
        logger.info("google_places_search_completed", extra={"provider": "google_places", "discovered_count": len(companies)})
        return companies

    async def _search(self, client, industries, location, limit):
        companies = []
        seen = set()
        # One unambiguous query per category, sharing a single total result budget.
        for industry in dict.fromkeys(" ".join(item.casefold().split()) for item in industries):
            response = await client.post(self._url, headers={
                "X-Goog-Api-Key": self._api_key.get_secret_value(), "X-Goog-FieldMask": _FIELD_MASK,
            }, json={"textQuery": f"{industry} in {location.strip()}", "pageSize": limit - len(companies),
                     "languageCode": "en"}, timeout=20)
            if response.status_code in {401, 403}:
                raise ProviderAuthenticationError("Google Places authorization failed; check key, API access, and billing.")
            if response.status_code == 429:
                raise ProviderRateLimitError("Google Places quota or rate limit reached.")
            if response.status_code != 200:
                raise ProviderError(f"Google Places search failed (HTTP {response.status_code}).")
            try:
                payload = response.json()
                if not isinstance(payload, dict) or "error" in payload or (payload and "places" not in payload):
                    raise ValueError
                results = _Response.model_validate(payload, strict=True)
            except (ValidationError, ValueError):
                raise ProviderResponseError("Google Places returned an invalid discovery response.") from None
            for place in results.places:
                if place.id in seen:
                    continue
                seen.add(place.id)
                companies.append(Company(name=place.displayName.text, website=place.websiteUri,
                                         industry=place.primaryTypeDisplayName.text if place.primaryTypeDisplayName else None,
                                         location=place.formattedAddress, employee_count=None,
                                         source="google_places", external_id=place.id))
                if len(companies) == limit:
                    return companies
        return companies
