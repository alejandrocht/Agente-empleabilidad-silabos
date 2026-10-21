"""Validated, explicitly opted-in import of session-authored technical judgments."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agente.normalizador.silabos import analista_tecnico


class SessionAnalystInputError(ValueError):
    """The session-authored answer file cannot be safely bound to this run."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SessionAnalystInputError(f"JSONL contiene la clave duplicada {key!r}")
        result[key] = value
    return result


def sha256_registro_canonico(registro: Mapping[str, object]) -> str:
    """Hash the complete extracted record using stable canonical JSON bytes."""

    try:
        canonico = json.dumps(
            registro,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SessionAnalystInputError(f"Registro extraído no serializable: {exc}") from exc
    return hashlib.sha256(canonico).hexdigest()


def ruta_respuestas_sesion_activa(usar_llm: bool, ruta: str | None) -> str | None:
    """Do not let the final-run opt-in affect deterministic preprocessing."""

    return ruta if usar_llm and ruta else None


def _leer_respuestas(
    ruta: Path,
) -> tuple[dict[str, tuple[analista_tecnico.RespuestaCompetenciasTecnicas, str, str]], str]:
    try:
        contenido = ruta.read_bytes()
        lineas = contenido.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise SessionAnalystInputError(f"No se pudo leer el JSONL de respuestas: {exc}") from exc
    if not lineas:
        raise SessionAnalystInputError("JSONL de respuestas vacío")

    respuestas: dict[str, tuple[analista_tecnico.RespuestaCompetenciasTecnicas, str, str]] = {}
    for numero, linea in enumerate(lineas, start=1):
        if not linea.strip():
            raise SessionAnalystInputError(f"JSONL contiene una línea vacía: {numero}")
        try:
            fila = json.loads(linea, object_pairs_hook=_strict_object)
        except (json.JSONDecodeError, SessionAnalystInputError) as exc:
            raise SessionAnalystInputError(f"JSONL inválido en línea {numero}: {exc}") from exc
        if not isinstance(fila, Mapping):
            raise SessionAnalystInputError(f"JSONL línea {numero} debe ser un objeto")
        if set(fila) != {
            "id_silabo",
            "registro_sha256",
            "catalogo_sha256",
            "competencias",
        }:
            raise SessionAnalystInputError(
                f"JSONL línea {numero}: campos esperados id_silabo, registro_sha256, "
                "catalogo_sha256 y competencias"
            )
        id_silabo = fila.get("id_silabo")
        if not isinstance(id_silabo, str) or not id_silabo.strip():
            raise SessionAnalystInputError(f"JSONL línea {numero}: id_silabo vacío o inválido")
        id_silabo = id_silabo.strip()
        if id_silabo in respuestas:
            raise SessionAnalystInputError(f"JSONL contiene id_silabo duplicado: {id_silabo}")
        registro_sha256 = fila.get("registro_sha256")
        catalogo_sha256 = fila.get("catalogo_sha256")
        if not isinstance(registro_sha256, str) or len(registro_sha256) != 64:
            raise SessionAnalystInputError(f"JSONL línea {numero}: registro_sha256 inválido")
        if not isinstance(catalogo_sha256, str) or len(catalogo_sha256) != 64:
            raise SessionAnalystInputError(f"JSONL línea {numero}: catalogo_sha256 inválido")
        competencias = fila["competencias"]
        if not isinstance(competencias, list):
            raise SessionAnalystInputError(f"JSONL línea {numero}: competencias debe ser una lista")
        campos_competencia = set(analista_tecnico.CompetenciaTecnicaInferida.model_fields)
        campos_evidencia = set(analista_tecnico.EvidenciaCompetenciaTecnica.model_fields)
        for competencia in competencias:
            if not isinstance(competencia, Mapping):
                raise SessionAnalystInputError(
                    f"JSONL línea {numero}: cada competencia debe ser un objeto"
                )
            if competencia.keys() - campos_competencia:
                raise SessionAnalystInputError(
                    f"JSONL línea {numero}: campos desconocidos en competencia"
                )
            evidencias = competencia.get("evidencia")
            if isinstance(evidencias, list) and any(
                not isinstance(evidencia, Mapping) or bool(evidencia.keys() - campos_evidencia)
                for evidencia in evidencias
            ):
                raise SessionAnalystInputError(
                    f"JSONL línea {numero}: campos desconocidos en evidencia"
                )
        try:
            respuesta = analista_tecnico.RespuestaCompetenciasTecnicas.model_validate(
                {"competencias": competencias}, strict=True
            )
        except Exception as exc:
            raise SessionAnalystInputError(
                f"JSONL línea {numero}: respuesta estructurada inválida: {exc}"
            ) from exc
        respuestas[id_silabo] = (respuesta, registro_sha256, catalogo_sha256)
    return respuestas, hashlib.sha256(contenido).hexdigest()


def analizar_respuestas_sesion(
    registros: Sequence[Mapping[str, object]],
    ruta_respuestas: Path | str,
    catalogo_tecnico: analista_tecnico.CatalogoTecnico | Path | str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, str]]:
    """Bind exactly one authored response to every extracted syllabus and validate all claims."""

    catalogo = analista_tecnico._resolver_catalogo(catalogo_tecnico)
    if catalogo is None:
        raise SessionAnalystInputError("Se requiere el catálogo técnico oficial")
    ruta = Path(ruta_respuestas).expanduser()
    respuestas, respuestas_sha256 = _leer_respuestas(ruta)

    registros_por_id: dict[str, Mapping[str, object]] = {}
    for registro in registros:
        id_silabo = analista_tecnico._texto(registro.get("id_silabo"))
        if not id_silabo:
            raise SessionAnalystInputError("Fuente extraída con id_silabo vacío")
        if id_silabo in registros_por_id:
            raise SessionAnalystInputError(f"id_silabo fuente duplicado: {id_silabo}")
        registros_por_id[id_silabo] = registro

    desconocidos = respuestas.keys() - registros_por_id.keys()
    faltantes = registros_por_id.keys() - respuestas.keys()
    if desconocidos:
        raise SessionAnalystInputError(
            "JSONL contiene id_silabo desconocido: " + ", ".join(sorted(desconocidos))
        )
    if faltantes:
        raise SessionAnalystInputError(
            "JSONL tiene respuestas faltantes para: " + ", ".join(sorted(faltantes))
        )

    propuestas: list[dict[str, object]] = []
    auditoria: list[dict[str, object]] = []
    for id_silabo, registro in registros_por_id.items():
        respuesta, registro_sha256, catalogo_sha256 = respuestas[id_silabo]
        esperado_registro_sha256 = sha256_registro_canonico(registro)
        if registro_sha256 != esperado_registro_sha256:
            raise SessionAnalystInputError(
                f"registro_sha256 obsoleto o incorrecto para {id_silabo}"
            )
        if catalogo_sha256 != catalogo.sha256:
            raise SessionAnalystInputError(
                f"catalogo_sha256 obsoleto o incorrecto para {id_silabo}"
            )
        carrera = analista_tecnico._texto(registro.get("carrera"))
        candidatos_lista = catalogo.para_carrera(carrera)
        candidatos = {candidato.referencia: candidato for candidato in candidatos_lista}
        contexto = analista_tecnico.construir_contexto_tecnico(registro, candidatos_lista)
        claves_propuestas: set[str] = set()
        filas_silabo: list[dict[str, object]] = []
        for propuesta in respuesta.competencias:
            referencia = analista_tecnico._texto(propuesta.catalogo_ref)
            if referencia and referencia not in candidatos:
                raise SessionAnalystInputError(
                    f"Referencia de catálogo fuera de carrera o desconocida para {id_silabo}: "
                    f"{referencia}"
                )
            clave = (
                "ref:" + referencia
                if referencia
                else "nombre:" + analista_tecnico.clave_catalogo(propuesta.nombre_competencia)
            )
            if clave in claves_propuestas:
                raise SessionAnalystInputError(
                    f"Propuesta técnica duplicada para {id_silabo}: {clave}"
                )
            claves_propuestas.add(clave)
            logros_fuente = {
                analista_tecnico._texto(logro.get("texto"))
                for logro in analista_tecnico._lista_mapeos(contexto.get("logros"))
            }
            if any(logro not in logros_fuente for logro in propuesta.logros):
                raise SessionAnalystInputError(
                    f"Los logros declarados no son citas literales para {id_silabo}"
                )
            if not all(
                analista_tecnico._evidencia_valida(evidencia, contexto)
                for evidencia in propuesta.evidencia
            ):
                raise SessionAnalystInputError(
                    f"evidencia no literal o no respaldada por logro para {id_silabo}"
                )
            if analista_tecnico._propuesta_nueva_repite_logro(propuesta, contexto):
                raise SessionAnalystInputError(
                    f"Propuesta nueva repite un logro sin abstracción para {id_silabo}"
                )
            fila = analista_tecnico._materializar_propuesta(
                propuesta,
                contexto,
                candidatos,
                exigir_logro=True,
                catalogo=catalogo,
            )
            if fila is None:
                raise SessionAnalystInputError(
                    f"Propuesta no materializable o sin logro literal para {id_silabo}"
                )
            if not referencia:
                fila["origen_propuesta"] = "SESSION_AUTHORED_NUEVA"
            filas_silabo.append(fila)
        propuestas.extend(filas_silabo)
        if not filas_silabo:
            auditoria.append(
                {
                    "codigo": "SILABO_SIN_PROPUESTA_TECNICA",
                    "id_silabo": id_silabo,
                    "mensaje": "La respuesta de sesión no contiene propuestas técnicas.",
                }
            )
    provenance = {
        "respuesta_origen": ruta.name,
        "respuestas_sha256": respuestas_sha256,
        "catalogo_sha256": catalogo.sha256,
        "vinculacion": "id_silabo+registro_sha256+catalogo_sha256",
    }
    return propuestas, auditoria, provenance
