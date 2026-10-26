"""Exception hierarchy for DeepResearch.

Keeping every public error in one module means callers can catch
``DeepResearchError`` without importing individual providers, and providers can
raise specific errors without creating import cycles.
"""

from __future__ import annotations


class DeepResearchError(Exception):
    """Base class for all errors raised by DeepResearch."""


class ConfigError(DeepResearchError):
    """Invalid or incomplete configuration (missing key, bad URL, ...)."""


class ProviderError(DeepResearchError):
    """A provider (LLM / search / fetch) failed."""


class LLMError(ProviderError):
    """The language model returned an error or unusable output."""


class SearchError(ProviderError):
    """The search backend returned an error."""


class FetchError(ProviderError):
    """A page could not be downloaded or parsed."""


class BudgetExceeded(DeepResearchError):
    """The run hit one of its limits (cost, LLM calls, wall time, sources)."""


class ReportError(DeepResearchError):
    """The report could not be rendered or validated."""
