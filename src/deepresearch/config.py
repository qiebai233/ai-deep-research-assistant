"""Configuration: environment loading, provider presets and validation.

Design goals
------------
* **Zero-config demo** — ``Settings()`` alone runs the fully offline mock stack,
  so a fresh clone produces a report without any API key.
* **Env-first** — every field can be set with ``DEEPRESEARCH_<FIELD>``; the usual
  vendor variables (``DEEPSEEK_API_KEY``, ``OPENAI_API_KEY``, ``TAVILY_API_KEY``,
  ``SEARXNG_URL``) are picked up automatically.
* **No dependency** — ``.env`` parsing, type coercion and validation are ~50 lines
  of :mod:`os` / :mod:`dataclasses`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .errors import ConfigError
from .models import Depth, profile_for

__all__ = [
    "MODEL_PRICING",
    "PRESETS",
    "Settings",
    "load_dotenv",
]

ENV_PREFIX = "DEEPRESEARCH_"

#: ``provider -> defaults``. ``key_env`` documents which variable carries the key.
PRESETS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
        "docs": "https://platform.deepseek.com",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
        "docs": "https://platform.openai.com",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
        "key_env": "OPENROUTER_API_KEY",
        "docs": "https://openrouter.ai",
    },
    "ollama": {
        "label": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:7b",
        "key_env": "",
        "docs": "https://ollama.com",
    },
    "custom": {
        "label": "Custom (OpenAI-compatible)",
        "base_url": "",
        "model": "",
        "key_env": "LLM_API_KEY",
        "docs": "",
    },
    "mock": {
        "label": "Offline mock (no network, no key)",
        "base_url": "",
        "model": "mock-researcher",
        "key_env": "",
        "docs": "",
    },
}

#: Approximate USD cost per 1M tokens as ``(prompt, completion)``.
#: Prices change; treat these numbers as an estimate, not billing truth.
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-3-5-haiku": (0.80, 4.00),
    "mock-researcher": (0.0, 0.0),
}

#: ``field -> env aliases`` (checked after ``DEEPRESEARCH_<FIELD>``).
_ENV_ALIASES: Dict[str, Tuple[str, ...]] = {
    "llm_api_key": ("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"),
    "llm_base_url": ("LLM_BASE_URL", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL"),
    "llm_model": ("LLM_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL"),
    "tavily_api_key": ("TAVILY_API_KEY",),
    "searxng_url": ("SEARXNG_URL",),
    "language": ("DEEPRESEARCH_LANG",),
}

_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}
_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _parse_bool(value: str) -> bool:
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ConfigError(f"expected a boolean, got {value!r}")


def load_dotenv(path: str | os.PathLike[str]) -> Dict[str, str]:
    """Parse a ``.env`` file (``KEY=VALUE``, ``#`` comments, ``export`` prefix).

    Variable references like ``${HOME}/x`` are expanded from the environment.
    """
    file = Path(path)
    if not file.is_file():
        return {}
    values: Dict[str, str] = {}
    for raw_line in file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            quote = value[0]
            value = value[1:-1]
            if quote == '"':
                value = value.encode("utf-8").decode("unicode_escape")
        else:
            value = value.split(" #", 1)[0].strip()
        value = _VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
        values[key] = value
    return values


@dataclass
class Settings:
    """All tunables in one place. See ``docs/configuration.md`` for the matrix."""

    # -- LLM --------------------------------------------------------------- #
    llm_provider: str = "mock"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_temperature: float = 0.3
    llm_max_tokens: int = 0  # 0 -> provider default
    llm_timeout: float = 120.0
    llm_max_retries: int = 2

    # -- Web search -------------------------------------------------------- #
    search_provider: str = "mock"  # tavily | searxng | none | mock
    tavily_api_key: str = ""
    tavily_search_depth: str = "basic"  # basic | advanced
    searxng_url: str = ""
    search_max_results: int = 6
    search_recency_days: int = 0
    search_timeout: float = 20.0
    search_max_retries: int = 1

    # -- Fetching / extraction --------------------------------------------- #
    fetch_timeout: float = 20.0
    fetch_max_chars: int = 12000
    fetch_concurrency: int = 4
    fetch_min_chars: int = 300
    user_agent: str = ""
    cache_dir: str = ".deepresearch/cache"
    cache_ttl_hours: float = 24.0
    use_cache: bool = True

    # -- Research behaviour ------------------------------------------------ #
    language: str = "zh"  # zh | en
    depth: str = "standard"  # quick | standard | deep
    out_dir: str = "reports"
    max_sources: int = 0  # 0 -> derived from depth
    max_llm_calls: int = 0  # 0 -> unlimited
    max_cost_usd: float = 0.0  # 0 -> unlimited
    max_seconds: float = 0.0  # 0 -> unlimited
    report_json: bool = True
    report_trace: bool = True

    # -- Misc -------------------------------------------------------------- #
    log_level: str = "info"  # debug | info | warn | error | quiet

    # ------------------------------------------------------------------ #
    # Constructors
    # ------------------------------------------------------------------ #
    @classmethod
    def from_env(
        cls,
        env_file: str | os.PathLike[str] | None = ".env",
        *,
        environ: Optional[Mapping[str, str]] = None,
        **overrides: Any,
    ) -> "Settings":
        """Build settings from ``.env`` + process environment + explicit overrides.

        Precedence: ``overrides`` > real environment > ``.env`` file > defaults.
        """
        env: Dict[str, str] = {}
        if environ is None:
            if env_file:
                env.update(load_dotenv(env_file))
            env.update(os.environ)
        else:
            env = dict(environ)

        settings = cls()
        known = {f.name: f for f in fields(cls)}

        # 1) explicit generic env vars, 2) documented aliases
        for name, meta in known.items():
            raw = env.get(ENV_PREFIX + name.upper())
            if raw is None:
                for alias in _ENV_ALIASES.get(name, ()):
                    if env.get(alias):
                        raw = env[alias]
                        break
            if raw is not None and str(raw).strip() != "":
                setattr(settings, name, _coerce(name, str(raw), meta.type))

        # 3) provider auto-detection (only when not explicitly configured)
        if not env.get(ENV_PREFIX + "LLM_PROVIDER"):
            if env.get("DEEPSEEK_API_KEY"):
                settings.llm_provider = "deepseek"
            elif env.get("OPENAI_API_KEY"):
                settings.llm_provider = "openai"
            elif env.get("OPENROUTER_API_KEY"):
                settings.llm_provider = "openrouter"
        if not env.get(ENV_PREFIX + "SEARCH_PROVIDER"):
            if env.get("TAVILY_API_KEY"):
                settings.search_provider = "tavily"
            elif env.get("SEARXNG_URL"):
                settings.search_provider = "searxng"
            elif settings.llm_provider == "mock":
                settings.search_provider = "mock"
            else:
                settings.search_provider = "none"

        # 4) explicit overrides (None means "keep default")
        for key, value in overrides.items():
            if value is None:
                continue
            if key not in known:
                raise ConfigError(f"unknown setting: {key!r}")
            setattr(settings, key, value)

        settings._apply_preset_defaults()
        return settings

    def with_overrides(self, **overrides: Any) -> "Settings":
        """Return a copy with ``overrides`` applied, then re-normalised."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        clone = replace(self, **clean)
        clone._apply_preset_defaults()
        return clone

    # ------------------------------------------------------------------ #
    # Normalisation / validation
    # ------------------------------------------------------------------ #
    def _apply_preset_defaults(self) -> None:
        provider = self.llm_provider.strip().lower() or "mock"
        if provider not in PRESETS:
            raise ConfigError(
                f"unknown llm provider {provider!r}; choose from {', '.join(PRESETS)}"
            )
        self.llm_provider = provider
        preset = PRESETS[provider]
        if not self.llm_base_url:
            self.llm_base_url = preset["base_url"]
        if not self.llm_model:
            self.llm_model = preset["model"] or ""
        if not self.llm_model and provider != "custom":
            self.llm_model = "mock-researcher"
        self.llm_base_url = self.llm_base_url.rstrip("/")
        self.llm_model = self.llm_model.strip()
        self.search_provider = (self.search_provider or "none").strip().lower()
        try:
            self.depth = Depth.parse(self.depth).value
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        self.language = "en" if str(self.language).lower().startswith("en") else "zh"
        self.log_level = str(self.log_level or "info").lower()
        self.search_max_results = max(1, min(int(self.search_max_results), 20))
        self.fetch_concurrency = max(1, min(int(self.fetch_concurrency), 16))
        self.max_sources = max(0, int(self.max_sources))
        if self.searxng_url:
            self.searxng_url = self.searxng_url.rstrip("/")

    def validate(self) -> List[str]:
        """Check the configuration; raises :class:`ConfigError` when unusable.

        Returns a list of human-readable warnings for non-fatal problems.
        """
        warnings: List[str] = []
        provider = self.llm_provider
        if provider not in ("mock", "ollama") and not self.llm_api_key:
            raise ConfigError(
                f"LLM provider {provider!r} needs an API key. Set "
                f"{PRESETS[provider]['key_env'] or 'DEEPRESEARCH_LLM_API_KEY'} "
                "in your environment or .env file (see .env.example)."
            )
        if provider == "custom" and not self.llm_base_url:
            raise ConfigError("llm provider 'custom' requires DEEPRESEARCH_LLM_BASE_URL")
        if provider == "custom" and not self.llm_model:
            raise ConfigError("llm provider 'custom' requires DEEPRESEARCH_LLM_MODEL")
        if self.llm_base_url and not self.llm_base_url.startswith(("http://", "https://")):
            raise ConfigError(f"llm_base_url must start with http(s)://, got {self.llm_base_url!r}")

        if self.search_provider == "tavily" and not self.tavily_api_key:
            raise ConfigError(
                "search provider 'tavily' needs TAVILY_API_KEY (get one at "
                "https://tavily.com). Use --search none for a knowledge-only run."
            )
        if self.search_provider == "searxng" and not self.searxng_url:
            raise ConfigError("search provider 'searxng' needs SEARXNG_URL")
        if self.search_provider == "none":
            warnings.append(
                "no web search configured: the report will rely on model knowledge only "
                "(no external citations)."
            )
        if provider == "mock" and self.search_provider != "mock":
            warnings.append(
                "mock LLM is active — the report is a deterministic demo, not real research."
            )
        if not (self.cache_dir and self.use_cache):
            warnings.append("cache disabled: every run will re-fetch pages.")
        return warnings

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def profile(self):
        """Depth profile with ``max_sources`` overridden when set."""
        profile = profile_for(self.depth)
        if self.max_sources:
            return replace(profile, max_sources=self.max_sources)
        return profile

    def has_llm_key(self) -> bool:
        return bool(self.llm_api_key) or self.llm_provider == "mock"

    def pricing(self) -> Tuple[float, float]:
        """Approximate ``(prompt, completion)`` USD per 1M tokens."""
        return MODEL_PRICING.get(self.llm_model, (0.0, 0.0))

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        prompt_price, completion_price = self.pricing()
        return (prompt_tokens * prompt_price + completion_tokens * completion_price) / 1_000_000

    def public_dict(self) -> Dict[str, Any]:
        """Config summary safe to show in the UI / logs (secrets masked)."""

        def mask(value: str) -> str:
            if not value:
                return ""
            return value[:4] + "…" + value[-4:] if len(value) > 8 else "***"

        data = {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "llm_api_key": mask(self.llm_api_key),
            "search_provider": self.search_provider,
            "tavily_api_key": mask(self.tavily_api_key),
            "searxng_url": self.searxng_url,
            "language": self.language,
            "depth": self.depth,
            "out_dir": self.out_dir,
            "cache_dir": self.cache_dir,
            "max_sources": self.max_sources,
            "max_cost_usd": self.max_cost_usd,
            "max_llm_calls": self.max_llm_calls,
            "max_seconds": self.max_seconds,
            "offline": self.llm_provider == "mock" and self.search_provider == "mock",
        }
        return data

    def describe(self) -> List[Tuple[str, str]]:
        """Ordered ``(label, value)`` pairs for the ``providers`` CLI command."""
        rows = [
            ("LLM provider", self.llm_provider),
            ("LLM model", self.llm_model),
            ("LLM endpoint", self.llm_base_url or "(mock, no network)"),
            ("API key", "set" if self.llm_api_key else "missing"),
            ("Search provider", self.search_provider),
            ("Search results/query", str(self.search_max_results)),
            ("Language", self.language),
            ("Depth", self.depth),
            ("Report directory", self.out_dir),
            ("Cache", "on" if self.use_cache else "off"),
        ]
        return rows


def _coerce(name: str, raw: str, annotation: Any) -> Any:
    """Coerce an env string to the declared field type."""
    text = raw.strip()
    target = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
    if target is bool or target == "bool":
        return _parse_bool(text)
    if target is int or target == "int":
        try:
            return int(float(text))
        except ValueError as exc:
            raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if target is float or target == "float":
        try:
            return float(text)
        except ValueError as exc:
            raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    return text
