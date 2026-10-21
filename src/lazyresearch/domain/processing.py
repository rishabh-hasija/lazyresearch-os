"""Identity of a generated artifact; no model calls or ProcessingRun engine."""

from dataclasses import dataclass

from lazyresearch.domain._validation import require_sha256, require_text


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessingIdentity:
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    schema_version: str
    pipeline_version: str
    input_hash: str
    model_revision: str | None = None
    provider_revision: str | None = None

    def __post_init__(self) -> None:
        for name in ("provider", "model", "prompt_version", "schema_version", "pipeline_version"):
            require_text(getattr(self, name), name)
        for name in ("prompt_hash", "input_hash"):
            require_sha256(getattr(self, name), name)
        for name in ("model_revision", "provider_revision"):
            value = getattr(self, name)
            if value is not None:
                require_text(value, name)
