from abc import ABC, abstractmethod

from app.domain.models.company import Company
from app.domain.models.contact_info import ContactInfo


class ContactEnrichmentPort(ABC):
    """Retrieve public business contact data for a qualified company."""

    @abstractmethod
    async def find_contacts(
        self,
        company: Company,
        people_limit: int = 3,
    ) -> ContactInfo:
        raise NotImplementedError
