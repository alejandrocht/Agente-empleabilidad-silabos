"""Explicit, diagnostic-only runner for CIAR LangExtract syllabus extraction."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from agente.normalizador.silabos.langextract_catalogo import (
    CatalogPreflightError,
    CatalogSelection,
    ReferenceCatalogSelection,
    detect_catalog_tools,
    preflight_catalog,
    preflight_reference_catalog,
    preflight_tool_catalog,
    resolve_catalog_document,
    suggest_reference_catalog_document,
)
from agente.normalizador.silabos.langextract_ciar import (
    PROMPT_EXTRACCION_CIAR,
    CitaLiteralCIAR,
    DocumentoRazonadoCIAR,
    PaqueteRespaldadoCIAR,
    PendienteCIAR,
    adaptar_resultado_langextract,
    construir_ejemplos_langextract,
    construir_payload_langextract,
)
from agente.normalizador.silabos.langextract_corpus import build_corpus_cases
from agente.normalizador.silabos.langextract_provider import OpenAICiarLanguageModel
from agente.observabilidad.langsmith import ejecutar_flujo

# Documents are independent, so wall time is bounded by concurrency, not by their sum.
# The ceiling stays bounded because every slot is one in-flight provider request.
_MAX_IN_FLIGHT_LIMITE = 16

ExtraerDocumento = Callable[[DocumentoRazonadoCIAR], object]


@dataclass(frozen=True, slots=True)
class ConfiguracionLangExtractCIAR:
    chunk_chars: int | None = None

    def __post_init__(self) -> None:
        if self.chunk_chars is not None and self.chunk_chars <= 0:
            raise ValueError("chunk_chars must be positive when explicitly enabled.")


@dataclass(frozen=True, slots=True)
class FragmentoLangExtractCIAR:
    inicio: int
    fin: int
    resultado: object | None = None
    error_tipo: str | None = None
    error_mensaje: str | None = None


@dataclass(frozen=True, slots=True)
class ResultadoFragmentadoLangExtractCIAR:
    fragmentos: tuple[FragmentoLangExtractCIAR, ...]


class ExtractorLangExtractCIAR:
    """Thin adapter over LangExtract. Default execution makes one call per document."""

    def __init__(
        self,
        model: OpenAICiarLanguageModel,
        configuracion: ConfiguracionLangExtractCIAR = ConfiguracionLangExtractCIAR(),
    ) -> None:
        self._model = model
        self._configuracion = configuracion

    def __call__(self, documento: DocumentoRazonadoCIAR) -> object:
        try:
            import langextract as lx
        except ImportError as error:
            raise RuntimeError(
                "LangExtract is not installed. Sync project dependencies first."
            ) from error

        texto = construir_payload_langextract(documento)["text_or_documents"]
        if self._configuracion.chunk_chars is None:
            return self._extraer(lx, texto, max(1, len(texto) + 1))

        fragmentos: list[FragmentoLangExtractCIAR] = []
        for inicio, fin, fragmento in _fragmentos(texto, self._configuracion.chunk_chars):
            try:
                fragmentos.append(
                    FragmentoLangExtractCIAR(
                        inicio=inicio,
                        fin=fin,
                        resultado=self._extraer(lx, fragmento, max(1, len(fragmento) + 1)),
                    )
                )
            except Exception as error:
                fragmentos.append(
                    FragmentoLangExtractCIAR(
                        inicio=inicio,
                        fin=fin,
                        error_tipo=type(error).__name__,
                        error_mensaje=str(error),
                    )
                )
        return ResultadoFragmentadoLangExtractCIAR(tuple(fragmentos))

    def _extraer(self, lx: object, texto: str, max_char_buffer: int) -> object:
        extract = getattr(lx, "extract")
        return extract(
            text_or_documents=texto,
            prompt_description=PROMPT_EXTRACCION_CIAR,
            examples=construir_ejemplos_langextract(),
            model=self._model,
            use_schema_constraints=False,
            fence_output=False,
            max_char_buffer=max_char_buffer,
            batch_length=1,
            extraction_passes=1,
            show_progress=False,
            resolver_params={"suppress_parse_errors": False},
        )


def ejecutar_corpus_langextract(
    docx_paths: Sequence[str | Path],
    extractor: ExtraerDocumento | None,
    catalog_selection: CatalogSelection | None = None,
    *,
    reference_catalog_selection: ReferenceCatalogSelection | None = None,
    on_document: Callable[[dict[str, object]], None] | None = None,
    results_dir: Path | None = None,
    resume: bool = False,
    profile: str = "strict",
    benchmark_model: str | None = None,
    benchmark_reasoning_effort: str | None = None,
    max_in_flight: int = 2,
    tools_only: bool = False,
    tool_catalog_path: Path | None = None,
) -> dict[str, object]:
    """Extract explicit DOCX files and expose accepted proposals, pending rows, and failures."""

    if profile not in {"strict", "baseline", "benchmark"}:
        raise ValueError(f"Unknown LangExtract profile: {profile}")
    if not 1 <= max_in_flight <= _MAX_IN_FLIGHT_LIMITE:
        raise ValueError(f"max_in_flight must be between 1 and {_MAX_IN_FLIGHT_LIMITE}.")
    if tools_only and catalog_selection is None and tool_catalog_path is None:
        raise ValueError("tools_only requires a canonical or standalone tool catalog.")
    if tools_only and reference_catalog_selection is not None:
        raise ValueError("tools_only rejects reference-only catalog suggestions.")
    if not tools_only and extractor is None:
        raise ValueError("extractor is required unless tools_only is enabled.")
    if not tools_only and profile in {"baseline", "benchmark"} and catalog_selection is not None:
        raise ValueError(f"The {profile} profile rejects catalog resolution.")
    if catalog_selection is not None and reference_catalog_selection is not None:
        raise ValueError("Catalog resolution and reference-only suggestions cannot coexist.")
    if catalog_selection is not None and tool_catalog_path is not None:
        raise ValueError("Canonical and standalone tool catalogs cannot coexist.")
    if not tools_only and profile == "benchmark" and not (
        benchmark_model and benchmark_reasoning_effort
    ):
        raise ValueError("The benchmark profile requires model and reasoning effort metadata.")

    catalog = None
    if catalog_selection is not None:
        try:
            catalog = preflight_catalog(catalog_selection)
        except CatalogPreflightError as error:
            return {
                "documentos": [],
                "catalogo_preflight": _catalogo_bloqueado(error.code, catalog_selection),
            }
    reference_catalog = None
    if reference_catalog_selection is not None:
        try:
            reference_catalog = preflight_reference_catalog(reference_catalog_selection)
        except CatalogPreflightError as error:
            return {
                "documentos": [],
                "catalogo_referencia": _catalogo_referencia_bloqueado(
                    error.code, reference_catalog_selection
                ),
            }
    tool_catalog = None
    if tool_catalog_path is not None:
        try:
            tool_catalog = preflight_tool_catalog(tool_catalog_path)
        except CatalogPreflightError as error:
            return {
                "documentos": [],
                "catalogo_herramientas_preflight": {"estado": "BLOQUEADO", "codigo": error.code},
            }

    destination = results_dir.resolve() if results_dir is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=True)
    cases = build_corpus_cases(docx_paths)

    def process_case(caso: dict[str, object]) -> dict[str, object]:
        source = _mapping(caso["source"])
        source_text = str(caso["source_text"])
        texto = str(
            source_text if profile in {"baseline", "benchmark"} else caso["texto_razonado"]
        )
        catalogo_herramientas = tool_catalog or catalog
        herramientas_detectadas = (
            detect_catalog_tools(catalogo_herramientas, source_text)
            if catalogo_herramientas is not None
            else []
        )
        candidatas_catalogo = _candidatas_catalogo_para_llm(herramientas_detectadas, source_text)
        paquetes: tuple[PaqueteRespaldadoCIAR, ...] = ()
        pendientes: tuple[PendienteCIAR, ...] = ()
        errores: list[dict[str, str]] = []
        fragmentos: list[dict[str, object]] = []
        propuestas_generadas = 0
        if not tools_only:
            documento = DocumentoRazonadoCIAR(
                contenido_documental=texto,
                ruta=str(source["path"]),
                hash_fuente=str(source["sha256"]),
                catalog_tool_candidates=candidatas_catalogo,
            )
            started = time.perf_counter()
            nombre_documento = Path(str(source["path"])).name
            try:
                assert extractor is not None
                extraer = extractor
                bruto = ejecutar_flujo(
                    lambda: extraer(documento),
                    run_name=f"langextract.extraccion.{nombre_documento}",
                    inputs={
                        "document": nombre_documento,
                        "source_sha256": str(source["sha256"]),
                    },
                    tags=["langextract", "extraccion", f"perfil:{profile}"],
                    metadata={
                        "document": nombre_documento,
                        "source_sha256": str(source["sha256"]),
                        "model": benchmark_model or "",
                        "reasoning_effort": benchmark_reasoning_effort or "",
                    },
                )
                propuestas_generadas = _contar_propuestas(bruto)
                if isinstance(bruto, ResultadoFragmentadoLangExtractCIAR):
                    paquetes, pendientes, errores, fragmentos = _adaptar_fragmentos(
                        texto,
                        bruto,
                        profile=profile,
                        catalog_tool_candidates=candidatas_catalogo,
                        source_text=source_text,
                    )
                else:
                    resultado = adaptar_resultado_langextract(
                        bruto,
                        profile=profile,
                        catalog_tool_candidates=candidatas_catalogo,
                        source_text=source_text,
                    )
                    paquetes = resultado.paquetes_respaldados
                    pendientes = resultado.pendientes
            except Exception as error:
                mensaje = str(error)
                if _is_timeout(error):
                    errores.append(
                        {
                            "tipo": type(error).__name__,
                            "mensaje": mensaje,
                            "duracion_segundos": f"{time.perf_counter() - started:.6f}",
                        }
                    )
                    pendientes = (_pendiente_fallo("LLM_REQUEST_TIMEOUT"),)
                else:
                    errores.append({"tipo": type(error).__name__, "mensaje": mensaje})
                    pendientes = (_pendiente_fallo(),)
        paquetes_serializados = [_serializar_paquete(paquete) for paquete in paquetes]
        diagnostico_documento = {
            "source": source,
            "structural_metadata": caso["structural_metadata"],
            "paquetes": paquetes_serializados,
            "pendientes": [asdict(pendiente) for pendiente in pendientes],
            "errores": errores,
            "fragmentos": fragmentos,
            "resumen": _resumen(propuestas_generadas, paquetes, pendientes, errores),
        }
        if not tools_only and profile in {"baseline", "benchmark"}:
            diagnostico_documento["profile"] = f"{profile}_unverified"
        if not tools_only and profile == "benchmark":
            diagnostico_documento["benchmark"] = {
                "model": benchmark_model,
                "reasoning_effort": benchmark_reasoning_effort,
            }
        if catalog is not None:
            diagnostico_documento.update(
                resolve_catalog_document(
                    catalog,
                    texto,
                    str(caso["source_text"]),
                    paquetes_serializados,
                )
            )
        elif tool_catalog is not None:
            diagnostico_documento["herramientas_detectadas"] = herramientas_detectadas
            diagnostico_documento["herramientas_sin_vinculo"] = _herramientas_sin_vinculo(
                herramientas_detectadas, paquetes_serializados
            )
        if reference_catalog is not None:
            diagnostico_documento.update(
                suggest_reference_catalog_document(reference_catalog, paquetes_serializados)
            )
        return diagnostico_documento

    documentos: list[dict[str, object]] = []
    ready: dict[int, tuple[dict[str, object], bool]] = {}
    in_flight: dict[Future[dict[str, object]], int] = {}
    next_input = 0
    next_output = 0
    with ThreadPoolExecutor(max_workers=max_in_flight) as executor:
        while next_output < len(cases):
            while next_input < len(cases) and len(in_flight) < max_in_flight:
                caso = cases[next_input]
                source = _mapping(caso["source"])
                saved = _load_saved_document(destination, source) if resume else None
                index = next_input
                next_input += 1
                if saved is not None:
                    ready[index] = (saved, False)
                    continue
                in_flight[executor.submit(process_case, caso)] = index

            while next_output in ready:
                diagnostico_documento, generated = ready.pop(next_output)
                documentos.append(diagnostico_documento)
                if generated and destination is not None:
                    _save_document(destination, diagnostico_documento, cases[next_output])
                if on_document is not None:
                    on_document(diagnostico_documento)
                next_output += 1

            if next_output == len(cases):
                break
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                ready[in_flight.pop(future)] = (future.result(), True)
    return {"documentos": documentos}


def _contar_propuestas(resultado: object) -> int:
    if isinstance(resultado, ResultadoFragmentadoLangExtractCIAR):
        return sum(_contar_propuestas(fragmento.resultado) for fragmento in resultado.fragmentos)
    extracciones = (
        resultado.get("extractions", ())
        if isinstance(resultado, dict)
        else getattr(resultado, "extractions", ())
    )
    return sum(
        1
        for extraccion in extracciones or ()
        if str(
            extraccion.get("extraction_class", "")
            if isinstance(extraccion, dict)
            else getattr(extraccion, "extraction_class", "")
        ).casefold()
        in {"paquete_respaldado", "paquete"}
    )


def _resumen(
    propuestas_generadas: int,
    paquetes: Sequence[PaqueteRespaldadoCIAR],
    pendientes: Sequence[PendienteCIAR],
    errores: Sequence[dict[str, str]],
) -> dict[str, object]:
    pendientes_por_motivo: dict[str, int] = {}
    for pendiente in pendientes:
        pendientes_por_motivo[pendiente.codigo] = pendientes_por_motivo.get(pendiente.codigo, 0) + 1
    return {
        "propuestas_generadas": propuestas_generadas,
        "paquetes_aceptados": len(paquetes),
        "pendientes_por_motivo": pendientes_por_motivo,
        "errores": len(errores),
    }


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Corpus case source is invalid.")
    return value


def _fragmentos(texto: str, longitud: int) -> tuple[tuple[int, int, str], ...]:
    if not texto:
        return ((0, 0, ""),)

    fragmentos: list[tuple[int, int, str]] = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + longitud, len(texto))
        if fin < len(texto):
            corte = texto.rfind(" ", inicio + 1, fin)
            if corte > inicio:
                fin = corte
        fragmentos.append((inicio, fin, texto[inicio:fin]))
        inicio = fin
        while inicio < len(texto) and texto[inicio].isspace():
            inicio += 1
    return tuple(fragmentos)


def _adaptar_fragmentos(
    texto_fuente: str,
    bruto: ResultadoFragmentadoLangExtractCIAR,
    *,
    profile: str,
    catalog_tool_candidates: tuple[dict[str, object], ...] = (),
    source_text: str | None = None,
) -> tuple[
    tuple[PaqueteRespaldadoCIAR, ...],
    tuple[PendienteCIAR, ...],
    list[dict[str, str]],
    list[dict[str, object]],
]:
    paquetes: list[PaqueteRespaldadoCIAR] = []
    pendientes: list[PendienteCIAR] = []
    errores: list[dict[str, str]] = []
    diagnosticos: list[dict[str, object]] = []
    for fragmento in bruto.fragmentos:
        paquetes_fragmento: tuple[PaqueteRespaldadoCIAR, ...] = ()
        pendientes_fragmento: tuple[PendienteCIAR, ...] = ()
        errores_fragmento: list[dict[str, str]] = []
        if fragmento.error_tipo is not None:
            error = {
                "tipo": fragmento.error_tipo,
                "mensaje": fragmento.error_mensaje or "Error LangExtract sin detalle.",
            }
            errores.append(error)
            errores_fragmento.append(error)
            pendientes_fragmento = (_pendiente_fallo(),)
        else:
            try:
                resultado = adaptar_resultado_langextract(
                    fragmento.resultado,
                    profile=profile,
                    catalog_tool_candidates=catalog_tool_candidates,
                    source_text=source_text,
                )
                paquetes_rebasados: list[PaqueteRespaldadoCIAR] = []
                pendientes_rebase: list[PendienteCIAR] = []
                for paquete in resultado.paquetes_respaldados:
                    rebasado, pendiente = _rebasar_paquete(paquete, texto_fuente, fragmento.inicio)
                    if rebasado is not None:
                        paquetes_rebasados.append(rebasado)
                    if pendiente is not None:
                        pendientes_rebase.append(pendiente)
                paquetes_fragmento = tuple(paquetes_rebasados)
                pendientes_fragmento = resultado.pendientes + tuple(pendientes_rebase)
            except Exception as error:
                detalle = {"tipo": type(error).__name__, "mensaje": str(error)}
                errores.append(detalle)
                errores_fragmento.append(detalle)
                pendientes_fragmento = (_pendiente_fallo(),)
        paquetes.extend(paquetes_fragmento)
        pendientes.extend(pendientes_fragmento)
        diagnosticos.append(
            {
                "inicio": fragmento.inicio,
                "fin": fragmento.fin,
                "paquetes": [_serializar_paquete(paquete) for paquete in paquetes_fragmento],
                "pendientes": [asdict(pendiente) for pendiente in pendientes_fragmento],
                "errores": errores_fragmento,
            }
        )
    return tuple(paquetes), tuple(pendientes), errores, diagnosticos


def _rebasar_paquete(
    paquete: PaqueteRespaldadoCIAR, texto_fuente: str, desplazamiento: int
) -> tuple[PaqueteRespaldadoCIAR | None, PendienteCIAR | None]:
    principal = _rebasar_cita(paquete.evidencia_principal, texto_fuente, desplazamiento)
    if principal is None:
        return None, PendienteCIAR(
            codigo="CITA_PRINCIPAL_NO_LITERAL",
            motivo="La cita del fragmento no coincide con el documento completo.",
        )
    complementaria = paquete.evidencia_complementaria
    if complementaria is not None:
        complementaria = _rebasar_cita(complementaria, texto_fuente, desplazamiento)
        if complementaria is None:
            return None, PendienteCIAR(
                codigo="CITA_COMPLEMENTARIA_NO_LITERAL",
                motivo="La cita complementaria no coincide con el documento completo.",
            )
    return replace(
        paquete,
        evidencia_principal=principal,
        evidencia_complementaria=complementaria,
    ), None


def _rebasar_cita(
    cita: CitaLiteralCIAR, texto_fuente: str, desplazamiento: int
) -> CitaLiteralCIAR | None:
    inicio = cita.start_pos + desplazamiento
    fin = cita.end_pos + desplazamiento
    if inicio < 0 or fin > len(texto_fuente) or texto_fuente[inicio:fin] != cita.texto:
        return None
    return CitaLiteralCIAR(texto=cita.texto, start_pos=inicio, end_pos=fin)


def _pendiente_fallo(codigo: str = "EXTRACCION_LANGEXTRACT_FALLIDA") -> PendienteCIAR:
    return PendienteCIAR(
        codigo=codigo,
        motivo=(
            "La solicitud al LLM excedió el tiempo límite."
            if codigo == "LLM_REQUEST_TIMEOUT"
            else "La extracción LangExtract no produjo un resultado verificable."
        ),
    )


def _serializar_paquete(paquete: PaqueteRespaldadoCIAR) -> dict[str, object]:
    return {
        "habilidad_propuesta": paquete.habilidad_propuesta,
        "competencia_propuesta": paquete.competencia_propuesta,
        "herramientas": list(paquete.herramientas),
        "herramientas_catalogo": list(paquete.herramientas_catalogo),
        "herramientas_propuestas": list(paquete.herramientas_propuestas),
        "evidencia_principal": asdict(paquete.evidencia_principal),
        "evidencia_complementaria": (
            asdict(paquete.evidencia_complementaria)
            if paquete.evidencia_complementaria is not None
            else None
        ),
        "contexto_relacion": paquete.contexto_relacion,
    }


def _candidatas_catalogo_para_llm(
    herramientas_detectadas: Sequence[dict[str, object]], source_text: str
) -> tuple[dict[str, object], ...]:
    candidatas: list[dict[str, object]] = []
    for herramienta in herramientas_detectadas:
        inicio = herramienta.get("start_pos")
        fin = herramienta.get("end_pos")
        if (
            herramienta.get("estado") != "RESUELTO"
            or not isinstance(inicio, int)
            or not isinstance(fin, int)
            or not isinstance(herramienta.get("id"), str)
        ):
            continue
        linea_inicio = source_text.rfind("\n", 0, inicio) + 1
        linea_fin = source_text.find("\n", fin)
        contexto_fin = len(source_text) if linea_fin < 0 else linea_fin
        candidatas.append(
            {
                "id": herramienta["id"],
                "nombre": herramienta["nombre"],
                "evidencia_literal": herramienta["evidencia_literal"],
                "seccion_fuente": "silabo_completo",
                "contexto_fuente": source_text[linea_inicio:contexto_fin],
                "start_pos": inicio,
                "end_pos": fin,
            }
        )
    return tuple(candidatas)


def _herramientas_sin_vinculo(
    herramientas_detectadas: Sequence[dict[str, object]], paquetes: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    vinculadas: set[tuple[object, object, object]] = set()
    for paquete in paquetes:
        herramientas = paquete.get("herramientas_catalogo")
        if not isinstance(herramientas, list):
            continue
        for herramienta in herramientas:
            if isinstance(herramienta, dict):
                vinculadas.add(
                    (
                        herramienta.get("id"),
                        herramienta.get("start_pos"),
                        herramienta.get("end_pos"),
                    )
                )
    return [
        {
            **herramienta,
            "motivo_sin_vinculo": (
                "SIN_ASIGNACION_RESPALDADA_A_HABILIDAD"
                if herramienta.get("estado") == "RESUELTO"
                else herramienta.get("codigo")
            ),
        }
        for herramienta in herramientas_detectadas
        if (
            herramienta.get("id"),
            herramienta.get("start_pos"),
            herramienta.get("end_pos"),
        )
        not in vinculadas
    ]


def _catalogo_bloqueado(code: str, selection: CatalogSelection) -> dict[str, object]:
    return {
        "estado": "BLOQUEADO",
        "codigo": code,
        "career": selection.career,
        "period": selection.period,
        "version": selection.version,
    }


def _catalogo_referencia_bloqueado(
    code: str, selection: ReferenceCatalogSelection
) -> dict[str, object]:
    return {
        "modo": "reference_only",
        "estado": "BLOQUEADO",
        "codigo": code,
        "alcance": str(selection.directory),
    }


def _is_timeout(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or type(error).__name__ == "APITimeoutError"


def _result_path(directory: Path, source: dict[str, object]) -> Path:
    return directory / f"{source['sha256']}.json"


def _save_document(directory: Path, document: dict[str, object], case: dict[str, object]) -> None:
    source = _mapping(document["source"])
    payload = {
        "documento": document,
        "catalogo_entrada": {
            "texto_razonado": case["texto_razonado"],
            "texto_silabo": case["source_text"],
            "paquetes_crudos": document.get("paquetes_crudos", document["paquetes"]),
        },
    }
    _result_path(directory, source).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_saved_document(
    directory: Path | None, source: dict[str, object]
) -> dict[str, object] | None:
    if directory is None:
        return None
    try:
        payload = json.loads(_result_path(directory, source).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    document = payload.get("documento") if isinstance(payload, dict) else None
    if not isinstance(document, dict) or document.get("errores"):
        return None
    return document


def resolver_resultados_guardados(
    results_dir: Path, selection: CatalogSelection
) -> dict[str, object]:
    """Apply a valid selected catalog to persisted raw results without calling an LLM."""
    try:
        catalog = preflight_catalog(selection)
    except CatalogPreflightError as error:
        return {"documentos": [], "catalogo_preflight": _catalogo_bloqueado(error.code, selection)}

    documents: list[dict[str, object]] = []
    for path in sorted(results_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        document = payload.get("documento")
        catalog_input = payload.get("catalogo_entrada")
        if not isinstance(document, dict) or not isinstance(catalog_input, dict):
            continue
        raw = catalog_input.get("paquetes_crudos")
        reasoned = catalog_input.get("texto_razonado")
        syllabus = catalog_input.get("texto_silabo")
        if (
            not isinstance(raw, list)
            or not isinstance(reasoned, str)
            or not isinstance(syllabus, str)
        ):
            continue
        document.update(resolve_catalog_document(catalog, reasoned, syllabus, raw))
        _save_replayed_document(path, payload, document)
        documents.append(document)
    return {"documentos": documents}


def _save_replayed_document(
    path: Path, payload: dict[str, object], document: dict[str, object]
) -> None:
    payload["documento"] = document
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _stream_document(document: dict[str, object]) -> dict[str, object]:
    safe = dict(document)
    source = _mapping(safe["source"])
    safe["source"] = {**source, "path": Path(str(source["path"])).name}
    return safe


def _stream_summary(result: dict[str, object], duration: float) -> dict[str, object]:
    documents = result.get("documentos", [])
    return {
        "tipo": "resumen",
        "documentos": len(documents) if isinstance(documents, list) else 0,
        "duracion_total_segundos": duration,
        "catalogo_preflight": result.get("catalogo_preflight"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx_paths", nargs="*", metavar="DOCX")
    parser.add_argument(
        "--profile",
        choices=("baseline", "benchmark", "strict"),
        default=os.getenv("CIAR_LANGEXTRACT_PROFILE", "baseline"),
    )
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--catalog-dir")
    parser.add_argument(
        "--tool-catalog",
        type=Path,
        help="Standalone catalogo_herramientas.csv used for local, canonical tool detection.",
    )
    parser.add_argument("--reference-catalog-dir")
    parser.add_argument("--career")
    parser.add_argument("--period")
    parser.add_argument("--catalog-version")
    parser.add_argument("--preflight-only", action="store_true")
    stream = parser.add_mutually_exclusive_group()
    stream.add_argument("--stream", dest="stream", action="store_true")
    stream.add_argument("--no-stream", dest="stream", action="store_false")
    parser.set_defaults(stream=None)
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Persist per-document results externally and stream document records by default.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse successful records from --results-dir; failed records are retried once.",
    )
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument(
        "--tools-only",
        action="store_true",
        help="Detect canonical catalog tools locally without creating a provider or LLM request.",
    )
    parser.add_argument(
        "--max-in-flight",
        type=int,
        default=8,
        help=(
            "Maximum concurrent document requests, 1 to "
            f"{_MAX_IN_FLIGHT_LIMITE} (default: 8)."
        ),
    )
    # Reasoning-heavy models spend minutes on a single syllabus; a short ceiling
    # discards finished work instead of saving time.
    parser.add_argument("--request-timeout-seconds", type=float, default=600.0)
    # Concurrency makes provider rate limits reachable, so let the SDK back off.
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--chunk-chars",
        type=int,
        help=(
            "Explicitly permit LangExtract chunks of this many characters; "
            "default is one call per DOCX."
        ),
    )
    args = parser.parse_args(argv)
    if args.results_dir is not None and args.results_dir.resolve().is_relative_to(
        _repository_root()
    ):
        parser.error("--results-dir must be outside the repository.")
    if args.resume and args.results_dir is None:
        parser.error("--resume requires --results-dir.")
    if args.tools_only and (args.preflight_only or args.resolve_only):
        parser.error("--tools-only cannot coexist with --preflight-only or --resolve-only.")
    catalog_values = (args.catalog_dir, args.career, args.period, args.catalog_version)
    if args.reference_catalog_dir and (any(catalog_values) or args.tool_catalog):
        parser.error("--reference-catalog-dir cannot coexist with canonical catalog options.")
    if args.tool_catalog and any(catalog_values):
        parser.error("--tool-catalog cannot coexist with canonical catalog options.")
    if not args.tools_only and args.profile in {"baseline", "benchmark"} and (
        any(catalog_values) or args.preflight_only or args.resolve_only
    ):
        parser.error(f"--profile {args.profile} rejects catalog and canonical resolution options.")
    if not args.tools_only and args.profile == "benchmark" and not (
        args.model and args.reasoning_effort
    ):
        parser.error("--profile benchmark requires explicit --model and --reasoning-effort.")
    if args.profile == "strict":
        args.model = args.model or os.getenv("CIAR_LANGEXTRACT_MODEL", "gpt-4o-mini")
        args.reasoning_effort = args.reasoning_effort or os.getenv(
            "CIAR_LANGEXTRACT_REASONING_EFFORT"
        )
    if any(catalog_values) and not all(catalog_values):
        parser.error(
            "--catalog-dir, --career, --period, and --catalog-version must be supplied together."
        )
    catalog_selection = (
        CatalogSelection(Path(args.catalog_dir), args.career, args.period, args.catalog_version)
        if all(catalog_values)
        else None
    )
    reference_catalog_selection = (
        ReferenceCatalogSelection(Path(args.reference_catalog_dir))
        if args.reference_catalog_dir
        else None
    )
    if args.tools_only and catalog_selection is None and args.tool_catalog is None:
        parser.error(
            "--tools-only requires --tool-catalog or a complete canonical catalog selection."
        )
    if args.preflight_only:
        if catalog_selection is None:
            parser.error("--preflight-only requires a complete catalog selection.")
        try:
            preflight_catalog(catalog_selection)
        except CatalogPreflightError as error:
            print(
                json.dumps(
                    {"catalogo_preflight": _catalogo_bloqueado(error.code, catalog_selection)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2
        print(
            json.dumps({"catalogo_preflight": {"estado": "VALIDO"}}, ensure_ascii=False, indent=2)
        )
        return 0
    if args.resolve_only:
        if catalog_selection is None or args.results_dir is None:
            parser.error("--resolve-only requires --results-dir and a complete catalog selection.")
        diagnostico = resolver_resultados_guardados(args.results_dir, catalog_selection)
        print(json.dumps(diagnostico, ensure_ascii=False, indent=2))
        return 0
    if not args.docx_paths:
        parser.error(
            "At least one DOCX path is required unless --preflight-only or --resolve-only is used."
        )
    extractor: ExtraerDocumento | None = None
    if not args.tools_only:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            parser.error(f"Environment variable {args.api_key_env} is required.")
        if args.profile == "baseline":
            provider = OpenAICiarLanguageModel(
                model_id="ciar-openai/gpt-4o-mini",
                api_key=api_key,
                temperature=0,
                request_timeout_seconds=args.request_timeout_seconds,
                max_retries=args.max_retries,
            )
        elif args.reasoning_effort:
            provider = OpenAICiarLanguageModel(
                model_id=f"ciar-openai/{args.model}",
                api_key=api_key,
                reasoning_effort=args.reasoning_effort,
                request_timeout_seconds=args.request_timeout_seconds,
                max_retries=args.max_retries,
            )
        else:
            provider = OpenAICiarLanguageModel(
                model_id=f"ciar-openai/{args.model}",
                api_key=api_key,
                request_timeout_seconds=args.request_timeout_seconds,
                max_retries=args.max_retries,
            )
        extractor = ExtractorLangExtractCIAR(
            provider, ConfiguracionLangExtractCIAR(chunk_chars=args.chunk_chars)
        )
    started = time.perf_counter()

    def emit_document(document: dict[str, object]) -> None:
        print(
            json.dumps(
                {"tipo": "documento", "documento": _stream_document(document)},
                ensure_ascii=False,
            ),
            flush=True,
        )

    use_stream = args.stream if args.stream is not None else args.results_dir is not None
    on_document = emit_document if use_stream else None
    diagnostico = ejecutar_corpus_langextract(
        args.docx_paths,
        extractor,
        catalog_selection=catalog_selection,
        reference_catalog_selection=reference_catalog_selection,
        on_document=on_document,
        results_dir=args.results_dir,
        resume=args.resume,
        profile=args.profile,
        benchmark_model=args.model if args.profile == "benchmark" else None,
        benchmark_reasoning_effort=args.reasoning_effort if args.profile == "benchmark" else None,
        max_in_flight=args.max_in_flight,
        tools_only=args.tools_only,
        tool_catalog_path=args.tool_catalog,
    )
    if use_stream:
        print(
            json.dumps(
                _stream_summary(diagnostico, time.perf_counter() - started), ensure_ascii=False
            ),
            flush=True,
        )
    else:
        print(json.dumps(diagnostico, ensure_ascii=False, indent=2))
    return 0


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


if __name__ == "__main__":
    raise SystemExit(main())
