from typing import Annotated, Literal

from pydantic import StringConstraints
import pycountry

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
QualificationLevel = Literal["high", "medium", "low"]


def location_country_code(location: str) -> str | None:
    """Normalize a country or 'City, Country' using the local ISO dataset."""
    try:
        return pycountry.countries.lookup(location.rsplit(",", 1)[-1].strip()).alpha_2
    except LookupError:
        return None
