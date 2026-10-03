from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr

from app.domain.models.client_context import ClientContext


class ResultCallback(BaseModel):
    url: AnyHttpUrl
    token: SecretStr = Field(min_length=32, max_length=256)


class RunAgentRequest(BaseModel):
    run_id: int = Field(gt=0)
    client: ClientContext
    callback: ResultCallback | None = None
