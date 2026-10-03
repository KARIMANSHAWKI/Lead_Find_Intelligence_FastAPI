from pydantic import BaseModel, Field

from app.domain.models.types import NonEmptyString


class ResearchEvidence(BaseModel):
    """Retrieved text paired with its source; not yet a buying signal."""

    text: NonEmptyString
    source_url: NonEmptyString | None = None
    source_type: NonEmptyString | None = None


class CompanyResearch(BaseModel):
    company_name: NonEmptyString
    website: str | None = None
    summary: str | None = None
    evidence: list[ResearchEvidence] = Field(default_factory=list)
