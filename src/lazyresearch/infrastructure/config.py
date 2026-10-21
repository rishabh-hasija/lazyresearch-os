"""Explicit configuration; no credentials or providers are hard-coded."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from lazyresearch.application.analysis_models import AnalysisConfig
from lazyresearch.application.intake_models import IntakeLimits


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = field(repr=False)
    limits: IntakeLimits = IntakeLimits()
    ai: AnalysisConfig = AnalysisConfig()
    ai_endpoint: str = "http://127.0.0.1:11434"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        url = values.get("DATABASE_URL", "")
        if not url:
            raise ValueError("DATABASE_URL is required")
        defaults = IntakeLimits()
        kwargs: dict[str, int | float] = {}
        for name in defaults.__dataclass_fields__:
            key = name.upper()
            if key in values:
                kwargs[name] = float(values[key]) if "timeout" in name else int(values[key])
        # Each field is numeric; individual fields are validated by IntakeLimits.
        limits = IntakeLimits(**kwargs)  # type: ignore[arg-type]
        ai = AnalysisConfig(
            provider=values.get("AI_PROVIDER", "ollama"),
            model=values.get("AI_MODEL", "gemma4:e4b"),
            timeout_seconds=float(values.get("AI_TIMEOUT_SECONDS", "120")),
            max_input_chars=int(values.get("AI_MAX_INPUT_CHARS", "4000")),
            max_chunks=int(values.get("AI_MAX_CHUNKS", "64")),
            max_output_tokens=int(values.get("AI_MAX_OUTPUT_TOKENS", "2400")),
        )
        return cls(url, limits, ai, values.get("AI_ENDPOINT", "http://127.0.0.1:11434"))
