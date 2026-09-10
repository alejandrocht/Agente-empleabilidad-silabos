"""LangExtract OpenAI provider that preserves CIAR system/user message roles."""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

from agente.normalizador.silabos.langextract_ciar import PROMPT_EXTRACCION_CIAR
from agente.observabilidad.langsmith import envolver_cliente_openai

_langextract_base_model: Any | None
_langextract_types: Any | None
_langextract_router: Any | None
try:
    _langextract_base_model = import_module("langextract.core.base_model")
    _langextract_types = import_module("langextract.core.types")
    _langextract_router = import_module("langextract.providers.router")
except ImportError:

    class _FallbackBaseLanguageModel:
        def __init__(self, **_: object) -> None:
            pass

    @dataclass(frozen=True)
    class _ScoredOutput:
        score: float | None = None
        output: str | None = None

    _langextract_base_model = None
    _langextract_types = None
    _langextract_router = None

if TYPE_CHECKING:
    from langextract.core.base_model import BaseLanguageModel as _ProviderBase
elif _langextract_base_model is None:

    class _ProviderBase(_FallbackBaseLanguageModel):
        pass

else:
    _ProviderBase = _langextract_base_model.BaseLanguageModel


def _registrar_proveedor(*patterns: str, priority: int) -> Any:
    if _langextract_router is None:
        return lambda provider: provider
    return _langextract_router.register(*patterns, priority=priority)


@_registrar_proveedor(r"^ciar-openai/", priority=100)
class OpenAICiarLanguageModel(_ProviderBase):
    """OpenAI adapter for CIAR that keeps rules in system and source text in user."""

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        client: Any | None = None,
        temperature: float | None = 0,
        request_timeout_seconds: float = 120.0,
        max_retries: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.temperature = temperature
        self.request_timeout_seconds = request_timeout_seconds
        self.max_retries = max_retries
        self._extra_kwargs = dict(kwargs)
        self._client = client or self._crear_cliente()

    @property
    def requires_fence_output(self) -> bool:
        return False

    def infer(self, batch_prompts: Sequence[str], **kwargs: object) -> Iterator[Sequence[Any]]:
        for prompt in batch_prompts:
            system = (
                f"{PROMPT_EXTRACCION_CIAR}\n\n"
                "Respond with a valid JSON object compatible with the extraction schema."
            )
            model = _modelo_openai(self.model_id)
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                **_parametros_openai(model, self.temperature, self._extra_kwargs | kwargs),
            )
            yield [_scored_output(_contenido_respuesta(response))]

    def _crear_cliente(self) -> Any:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required when no OpenAI client is injected.")
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "OpenAI SDK is required for the CIAR LangExtract provider."
            ) from error
        cliente = OpenAI(
            api_key=self.api_key,
            timeout=self.request_timeout_seconds,
            max_retries=self.max_retries,
        )
        return envolver_cliente_openai(
            cliente,
            metadata={
                "langextract_model_id": self.model_id,
                "langextract_reasoning_effort": self._extra_kwargs.get("reasoning_effort"),
            },
            tags=["langextract", "extraccion"],
        )


def _modelo_openai(model_id: str) -> str:
    prefix = "ciar-openai/"
    if not model_id.startswith(prefix) or not model_id.removeprefix(prefix):
        raise ValueError("CIAR LangExtract model IDs must use ciar-openai/<OpenAI model>.")
    return model_id.removeprefix(prefix)


def _parametros_openai(
    model: str, temperature: float | None, kwargs: dict[str, object]
) -> dict[str, object]:
    parametros: dict[str, object] = {}
    if model != "gpt-5.6-luna" and temperature is not None:
        parametros["temperature"] = temperature
    nombres: tuple[str, ...] = ("reasoning_effort", "max_output_tokens")
    if model != "gpt-5.6-luna":
        nombres += ("top_p", "seed")
    for nombre in nombres:
        if nombre in kwargs and kwargs[nombre] is not None:
            parametros[nombre] = kwargs[nombre]
    if "max_output_tokens" in parametros:
        parametros["max_tokens"] = parametros.pop("max_output_tokens")
    return parametros


def _contenido_respuesta(response: object) -> str:
    choices = _campo(response, "choices", ())
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        raise RuntimeError("OpenAI response did not contain choices.")
    content = _campo(_campo(choices[0], "message", {}), "content")
    if not isinstance(content, str) or not content:
        raise RuntimeError("OpenAI response did not contain message content.")
    return content


def _scored_output(content: str) -> Any:
    if _langextract_types is None:
        return _ScoredOutput(score=1.0, output=content)
    return _langextract_types.ScoredOutput(score=1.0, output=content)


def _campo(value: object, field: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)
