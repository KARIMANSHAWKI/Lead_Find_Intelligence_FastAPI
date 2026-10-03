import logging

from app.core.config import Settings
from app.domain.models.client_context import ClientContext
from app.domain.ports.company_search import CompanySearchPort
from app.infrastructure.company_search.google_places_provider import GooglePlacesCompanySearchProvider
from app.infrastructure.company_search.hunter_provider import HunterCompanySearchProvider

logger = logging.getLogger(__name__)
LOCAL_BUSINESS_CATEGORIES = frozenset({
    "restaurant", "restaurants", "cafe", "cafes", "gym", "gyms", "clinic", "clinics",
    "dental clinic", "dental clinics", "dentist", "dentists", "salon", "salons",
    "beauty salon", "beauty salons", "beauty center", "beauty centers", "hotel", "hotels",
    "pharmacy", "pharmacies", "retail", "retail store", "retail stores", "store", "stores",
    "training center", "training centers", "local service businesses",
})


class CompanySearchProviderResolver:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self, client_context: ClientContext) -> CompanySearchPort:
        size = client_context.company_size
        reason = "default_b2b"
        if size.min is not None or size.max is not None:
            reason = "company_size_filter"
        elif all(" ".join(category.casefold().split()) in LOCAL_BUSINESS_CATEGORIES
                 for category in client_context.target_industries):
            logger.info("company_search_provider_selected", extra={"provider": "google_places", "reason": "local_business_category"})
            return GooglePlacesCompanySearchProvider(self._settings.google_places_api_key,
                                                     str(self._settings.google_places_base_url))
        logger.info("company_search_provider_selected", extra={"provider": "hunter", "reason": reason})
        return HunterCompanySearchProvider(self._settings.hunter_api_key, str(self._settings.hunter_base_url))
