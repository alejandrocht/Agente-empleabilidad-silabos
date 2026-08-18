"""Instrumentación LangSmith opcional y segura para el normalizador curricular.

La integración usa la configuración nativa de LangChain para las llamadas LLM y
``traceable`` solo para crear el span raíz de una ejecución curricular. Cuando el
tracing está apagado, o el paquete de LangSmith no está disponible, las funciones
son no-op y no cambian la interfaz de los dobles usados por las pruebas.

Solo se registran datos de auditoría del dominio: rol, modelo implícito del LLM,
ejecución, carrera, periodo, lote y entradas/salidas del modelo. Nunca se pide ni
se intenta capturar chain-of-thought privado.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from agente.config.settings import booleano
from agente.normalizador.excepciones import CancelacionSolicitada

T = TypeVar("T")

_ESQUEMA = "normalizador-curricular/langsmith-v1"


def tracing_activo() -> bool:
    """Indica si la aplicación solicitó explícitamente trazas LangSmith."""

    return booleano("LANGSMITH_TRACING", False)


def contexto_ejecucion(
    id_ejecucion: str,
    carrera: str,
    periodo: str,
) -> tuple[list[str], dict[str, Any]]:
    """Construye tags y metadata estables sin incluir secretos ni contenido fuente."""

    ejecucion = str(id_ejecucion or "").strip()[:120]
    carrera_normalizada = str(carrera or "").strip()[:120]
    periodo_normalizado = str(periodo or "").strip()[:40]
    tags = ["normalizador", "curricular"]
    if carrera_normalizada:
        tags.append(f"carrera:{carrera_normalizada}")
    if periodo_normalizado:
        tags.append(f"periodo:{periodo_normalizado}")
    metadata = {
        "observability_schema": _ESQUEMA,
        "execution_id": ejecucion,
        "career": carrera_normalizada,
        "period": periodo_normalizado,
    }
    return tags, metadata


def configuracion_llm(
    rol: str,
    *,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    chunk: int | None = None,
    reintento: bool = False,
) -> dict[str, Any] | None:
    """Devuelve un ``RunnableConfig`` compatible solo cuando tracing está activo."""

    if not tracing_activo():
        return None
    tags, metadata = contexto_ejecucion(id_ejecucion, carrera, periodo)
    tags.append(f"rol:{rol}")
    metadata.update({"llm_role": rol, "retry": reintento})
    if chunk is not None:
        metadata["chunk"] = str(chunk)
    return {
        "run_name": f"normalizador.curricular.{rol}",
        "tags": tags,
        "metadata": metadata,
    }


def _acepta_configuracion(invoke: Callable[..., Any]) -> bool:
    try:
        parametros = inspect.signature(invoke).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parametro.name == "config" or parametro.kind == inspect.Parameter.VAR_KEYWORD
        for parametro in parametros
    )


def invocar_llm(
    runnable: Any,
    prompt: str,
    *,
    rol: str,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    chunk: int | None = None,
    reintento: bool = False,
) -> Any:
    """Invoca un runnable pasando contexto LangChain sin romper dobles simples."""

    config = configuracion_llm(
        rol,
        id_ejecucion=id_ejecucion,
        carrera=carrera,
        periodo=periodo,
        chunk=chunk,
        reintento=reintento,
    )
    objetivo = runnable
    if config is not None:
        with_config = getattr(runnable, "with_config", None)
        if callable(with_config):
            try:
                objetivo = with_config(config)
            except (AttributeError, TypeError):
                objetivo = runnable
        invoke = getattr(objetivo, "invoke")
        if objetivo is runnable and _acepta_configuracion(invoke):
            return invoke(prompt, config=config)
    return getattr(objetivo, "invoke")(prompt)


def _resumen_salida(valor: Any) -> dict[str, Any]:
    """Limita el span raíz a un resumen; las salidas LLM quedan en sus runs nativos."""

    resumen: dict[str, Any] = {"type": type(valor).__name__}
    if isinstance(valor, Mapping):
        for atributo in ("status", "estado", "mensaje"):
            dato = valor.get(atributo)
            if isinstance(dato, (bool, int, float, str)):
                resumen[atributo] = dato
    for atributo in ("publicable", "relaciones", "competencias", "habilidades", "herramientas"):
        dato = getattr(valor, atributo, None)
        if isinstance(dato, (bool, int, float, str)):
            resumen[atributo] = dato
    for atributo in ("hallazgos", "outputs", "decisiones", "reportes"):
        dato = getattr(valor, atributo, None)
        if isinstance(dato, (list, tuple, dict)):
            resumen[f"{atributo}_count"] = len(dato)
    return resumen


def ejecutar_flujo(
    funcion: Callable[[], T],
    *,
    run_name: str,
    inputs: Mapping[str, Any],
    tags: Sequence[str],
    metadata: Mapping[str, Any],
) -> T:
    """Ejecuta una función bajo un span raíz sin convertir telemetría en requisito."""

    if not tracing_activo():
        return funcion()
    cancelacion: CancelacionSolicitada | None = None

    def ejecutar_trazado(_entrada: Any) -> T | dict[str, str]:
        nonlocal cancelacion
        try:
            return funcion()
        except CancelacionSolicitada as exc:
            # El span raíz termina correctamente con un estado explícito. La
            # excepción se relanza después para que el worker marque el manifest.
            cancelacion = exc
            return {
                "status": "cancelled",
                "estado": "cancelado",
                "mensaje": str(exc),
            }

    try:
        from langsmith import traceable

        def procesar_entradas(_valor: Any) -> dict[str, Any]:
            return dict(inputs)

        procesar_salidas = _resumen_salida
        decorador = traceable(
            name=run_name,
            run_type="chain",
            tags=list(tags),
            metadata=dict(metadata),
            process_inputs=procesar_entradas,
            process_outputs=procesar_salidas,
            enabled=True,
        )
        trazada = decorador(ejecutar_trazado)
    except Exception:
        # Una instalación incompleta o una configuración inválida no debe impedir
        # el procesamiento curricular. La llamada de negocio se ejecuta una sola vez.
        return funcion()
    resultado = trazada({"run": run_name})
    if cancelacion is not None:
        raise cancelacion
    return resultado  # type: ignore[return-value]
