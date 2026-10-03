from pydantic import BaseModel, Field

from app.domain.models.types import NonEmptyString


class CompanyEmail(BaseModel):
    email: NonEmptyString
    confidence: int | None = Field(default=None, ge=0, le=100)
    verification_status: str | None = None


class PersonContact(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: NonEmptyString
    position: str | None = None
    seniority: str | None = None
    department: str | None = None
    linkedin_url: str | None = None
    phone_number: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    verification_status: str | None = None


class ContactInfo(BaseModel):
    company_emails: list[CompanyEmail] = Field(default_factory=list)
    company_phone_numbers: list[str] = Field(default_factory=list)
    people: list[PersonContact] = Field(default_factory=list)
