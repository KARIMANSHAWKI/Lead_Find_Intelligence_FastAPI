from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.domain.models.types import NonEmptyString


class CompanySize(BaseModel):
    min: int | None = Field(default=None, ge=0)
    max: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("company_size.min must not be greater than max")
        return self


class ClientContext(BaseModel):
    product: NonEmptyString
    target_industries: list[NonEmptyString] = Field(min_length=1)
    location: NonEmptyString
    company_size: CompanySize
    ideal_customer_description: str | None = None
