from pydantic import BaseModel, Field

from app.domain.models.prospect import Prospect


class ProspectResult(Prospect):
    """HTTP result schema sharing the domain prospect's fields and validation."""


class RunAgentResponse(BaseModel):
    run_id: int = Field(gt=0)
    prospects: list[ProspectResult]
