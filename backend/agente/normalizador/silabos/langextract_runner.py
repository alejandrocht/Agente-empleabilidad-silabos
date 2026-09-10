"""Explicit, diagnostic-only runner for CIAR LangExtract syllabus extraction."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from agente.normalizador.silabos.langextract_catalogo import (
    CatalogPreflightError,
    CatalogSelection,
    preflight_catalog,
    resolve_catalog_document,
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
    extractor: ExtraerDocumento,
    catalog_selection: CatalogSelection | None = None,
    *,
    on_document: Callable[[dict[str, object]], None] | None = None,
    results_dir: Path | None = None,
    resume: bool = False,
    profile: str = "strict",
) -> dict[str, object]:
    """Extract explicit DOCX files and expose accepted proposals, pending rows, and failures."""

    if profile not in {"strict", "baseline"}:
        raise ValueError(f"Unknown LangExtract profile: {profile}")
    if profile == "baseline" and catalog_selection is not None:
        raise ValueError("The baseline profile rejects catalog resolution.")

    catalog = None
    if catalog_selection is not None:
        try:
            catalog = preflight_catalog(catalog_selection)
        except CatalogPreflightError as error:
            return {
                "documentos": [],
                "catalogo_preflight": _catalogo_bloqueado(error.code, catalog_selection),
            }

    destination = results_dir.resolve() if results_dir is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=True)
    documentos: list[dict[str, object]] = []
    for caso in build_corpus_cases(docx_paths):
        source = _mapping(caso["source"])
        saved = _load_saved_document(destination, source) if resume else None
        if saved is not None:
            documentos.append(saved)
            if on_document is not None:
                on_document(saved)
            continue
        texto = str(caso["source_text"] if profile == "baseline" else caso["texto_razonado"])
        documento = DocumentoRazonadoCIAR(
            contenido_documental=texto,
            ruta=str(source["path"]),
            hash_fuente=str(source["sha256"]),
        )
        paquetes: tuple[PaqueteRespaldadoCIAR, ...] = ()
        pendientes: tuple[PendienteCIAR, ...] = ()
        errores: list[dict[str, str]] = []
        fragmentos: list[dict[str, object]] = []
        propuestas_generadas = 0
        started = time.perf_counter()
        try:
            bruto = extractor(documento)
            propuestas_generadas = _contar_propuestas(bruto)
            if isinstance(bruto, ResultadoFragmentadoLangExtractCIAR):
                paquetes, pendientes, errores, fragmentos = _adaptar_fragmentos(
                    texto, bruto, profile=profile
                )
            else:
                resultado = adaptar_resultado_langextract(bruto, profile=profile)
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
        if profile == "baseline":
            diagnostico_documento["profile"] = "baseline_unverified"
        if catalog is not None:
            diagnostico_documento.update(
                resolve_catalog_document(
                    catalog,
                    texto,
                    str(caso["source_text"]),
                    paquetes_serializados,
                )
            )
        documentos.append(diagnostico_documento)
        if destination is not None:
            _save_document(destination, diagnostico_documento, caso)
        if on_document is not None:
            on_document(diagnostico_documento)
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
    texto_fuente: str, bruto: ResultadoFragmentadoLangExtractCIAR, *, profile: str
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
                resultado = adaptar_resultado_langextract(fragmento.resultado, profile=profile)
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
        "evidencia_principal": asdict(paquete.evidencia_principal),
        "evidencia_complementaria": (
            asdict(paquete.evidencia_complementaria)
            if paquete.evidencia_complementaria is not None
            else None
        ),
        "contexto_relacion": paquete.contexto_relacion,
    }


def _catalogo_bloqueado(code: str, selection: CatalogSelection) -> dict[str, object]:
    return {
        "estado": "BLOQUEADO",
        "codigo": code,
        "career": selection.career,
        "period": selection.period,
        "version": selection.version,
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
        choices=("baseline", "strict"),
        default=os.getenv("CIAR_LANGEXTRACT_PROFILE", "baseline"),
    )
    parser.add_argument("--model", default=os.getenv("CIAR_LANGEXTRACT_MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--reasoning-effort", default=os.getenv("CIAR_LANGEXTRACT_REASONING_EFFORT")
    )
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--catalog-dir")
    parser.add_argument("--career")
    parser.add_argument("--period")
    parser.add_argument("--catalog-version")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=0)
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
    catalog_values = (args.catalog_dir, args.career, args.period, args.catalog_version)
    if args.profile == "baseline" and (
        any(catalog_values) or args.preflight_only or args.resolve_only
    ):
        parser.error("--profile baseline rejects catalog and canonical resolution options.")
    if any(catalog_values) and not all(catalog_values):
        parser.error(
            "--catalog-dir, --career, --period, and --catalog-version must be supplied together."
        )
    catalog_selection = (
        CatalogSelection(Path(args.catalog_dir), args.career, args.period, args.catalog_version)
        if all(catalog_values)
        else None
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

    on_document = emit_document if args.stream else None
    diagnostico = ejecutar_corpus_langextract(
        args.docx_paths,
        extractor,
        catalog_selection,
        on_document=on_document,
        results_dir=args.results_dir,
        resume=args.resume,
        profile=args.profile,
    )
    if args.stream:
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
