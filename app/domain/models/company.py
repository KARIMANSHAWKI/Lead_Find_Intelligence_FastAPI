from pydantic import BaseModel, Field

from app.domain.models.types import NonEmptyString


class Company(BaseModel):
    name: NonEmptyString
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    employee_count: int | None = Field(default=None, ge=0)
    source: str | None = None
    external_id: str | None = None
