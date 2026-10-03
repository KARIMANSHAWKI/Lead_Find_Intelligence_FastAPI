from fastapi import FastAPI

from app.api.exception_handlers import configuration_error, provider_error, search_input_error
from app.api.health_routes import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings, get_settings
from app.core.exceptions import CompanySearchInputError, ProviderConfigurationError, ProviderError
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings if settings is not None else get_settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.add_exception_handler(ProviderConfigurationError, configuration_error)
    application.add_exception_handler(ProviderError, provider_error)
    application.add_exception_handler(CompanySearchInputError, search_input_error)
    application.include_router(health_router)
    application.include_router(v1_router, prefix="/api/v1")
    return application


app = create_app()
