from pydantic import BaseModel, Field

from app.domain.models.buying_signal import BuyingSignal
from app.domain.models.contact_info import ContactInfo
from app.domain.models.types import NonEmptyString, QualificationLevel


class Prospect(BaseModel):
    company_name: NonEmptyString
    website: str | None
    icp_fit: QualificationLevel
    product_relevance: QualificationLevel
    why_now: NonEmptyString
    buying_signals: list[BuyingSignal]
    contact_info: ContactInfo = Field(default_factory=ContactInfo)
