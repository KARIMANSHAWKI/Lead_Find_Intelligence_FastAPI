class ProviderConfigurationError(RuntimeError):
    """A requested external provider is missing required configuration."""


class ProviderError(RuntimeError):
    """An external provider operation failed without exposing vendor payloads."""


class ProviderAuthenticationError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderResponseError(ProviderError):
    pass


class CompanySearchInputError(ValueError):
    """Company discovery parameters cannot be mapped to supported filters."""


class LLMConfigurationError(ProviderConfigurationError):
    pass


class LLMResponseValidationError(ProviderResponseError):
    """LLM JSON failed local schema or evidence validation."""


class LLMMalformedResponseError(ProviderResponseError):
    """The provider returned an unusable completion envelope."""


class AgentUnavailableError(ProviderError):
    """No candidate could be analyzed due to provider availability failures."""
