import pytest
from fastapi import Request
from pydantic import SecretStr

from app.api.dependencies import (
    get_company_search_provider,
    get_request_settings,
    get_web_research_provider,
)
from app.core.config import Settings
from app.core.exceptions import ProviderConfigurationError
from app.domain.ports.company_search import CompanySearchPort
from app.domain.ports.web_research import WebResearchPort
from app.infrastructure.company_search.hunter_provider import HunterCompanySearchProvider
from app.infrastructure.research.web_search_provider import WebSearchResearchProvider
from app.main import create_app
from app.application.dto.request import RunAgentRequest

def b2b_request():
    return RunAgentRequest(run_id=1, client={"product":"Recruitment", "target_industries":["Software"], "location":"Egypt", "company_size":{"min":50,"max":300}})


def test_factories_return_expected_port_implementations():
    settings = Settings(_env_file=None, hunter_api_key="test-key")
    company_search = get_company_search_provider(settings, b2b_request())
    assert isinstance(company_search, CompanySearchPort)
    assert isinstance(company_search, HunterCompanySearchProvider)
    research = get_web_research_provider(settings)
    assert isinstance(research, WebResearchPort)
    assert isinstance(research, WebSearchResearchProvider)


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_missing_hunter_configuration_is_explicit(api_key):
    settings = Settings(_env_file=None, hunter_api_key=api_key)
    with pytest.raises(ProviderConfigurationError, match="HUNTER_API_KEY"):
        get_company_search_provider(settings, b2b_request())
    secret = SecretStr(api_key) if api_key is not None else None
    with pytest.raises(ProviderConfigurationError, match="HUNTER_API_KEY"):
        HunterCompanySearchProvider(secret)


def test_settings_load_hunter_key_without_exposing_it(monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "test-secret-key")
    monkeypatch.setenv("HUNTER_BASE_URL", "https://hunter.test")
    settings = Settings(_env_file=None)
    assert settings.hunter_api_key.get_secret_value() == "test-secret-key"
    assert "test-secret-key" not in repr(settings)
    assert str(settings.hunter_base_url) == "https://hunter.test/"


def test_dependency_uses_application_settings():
    settings = Settings(_env_file=None, hunter_api_key="test-key")
    application = create_app(settings)
    request = Request({"type": "http", "app": application})
    assert get_request_settings(request) is settings
    assert isinstance(get_company_search_provider(get_request_settings(request), b2b_request()), HunterCompanySearchProvider)
