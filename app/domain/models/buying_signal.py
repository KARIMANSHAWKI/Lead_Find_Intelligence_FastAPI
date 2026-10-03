from pydantic import BaseModel, ConfigDict

from app.domain.models.types import NonEmptyString, QualificationLevel


class BuyingSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: NonEmptyString
    evidence: NonEmptyString
    source_url: str | None
    strength: QualificationLevel
