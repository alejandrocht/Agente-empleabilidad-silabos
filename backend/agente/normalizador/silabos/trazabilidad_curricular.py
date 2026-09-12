"""Stable curricular traceability primitives."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.modelos import Hallazgo

ESTADO_PENDIENTE_CATALOGACION = "PENDIENTE_CATALOGACION"
ESTADO_PENDIENTE_PERFIL = "PENDIENTE_AMPLIACION_PERFIL"
ESTADO_REVISION_HUMANA = "REQUIERE_REVISION_HUMANA"

_CARRERAS_POR_NOMBRE: dict[str, str] = {
    "INGENIERIA_AMBIENTAL": "CAR_16a641c270b45a22",
    "INGENIERIA_MECATRONICA": "CAR_6659c30f0631de14",
    "INGENIERIA_INDUSTRIAL": "CAR_e3be6803d0ccd399",
    "INGENIERIA_DE_SISTEMAS": "CAR_01375f53651cff38",
    "INGENIERIA_CIVIL": "CAR_e36deec09aa73922",
    "ARQUITECTURA": "CAR_b698d86c67a2cff8",
    "ADMINISTRACION": "CAR_6cf69ce9e7aca4e0",
    "MARKETING": "CAR_9f09cddacdb2e0c1",
    "NEGOCIOS_INTERNACIONALES": "CAR_d4038d81b261ec58",
    "CONTABILIDAD_Y_FINANZAS": "CAR_525cfd02ce6f836c",
    "PSICOLOGIA": "CAR_adb019dcde61d092",
    "ECONOMIA": "CAR_7f7e4d7eba491f6f",
    "COMUNICACION": "CAR_8f496feec94eb1ce",
    "DERECHO": "CAR_b8b3a9403ceee5e6",
}
_ALIASES_CARRERA = {"SISTEMAS": "INGENIERIA_DE_SISTEMAS"}


def _clave_carrera(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", _texto(valor))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r"[^A-Z0-9]+", "_", texto.upper()).strip("_")


def _id_carrera(carrera: str) -> str:
    clave = _ALIASES_CARRERA.get(_clave_carrera(carrera), _clave_carrera(carrera))
    return _CARRERAS_POR_NOMBRE.get(clave, "")


def _modalidad_curso(valor: object) -> str:
    """Publica modos de entrega; nunca la naturaleza académica de la asignatura."""

    clave = _clave_carrera(valor).replace("_", " ")
    if "PRESENCIAL" in clave:
        return "Presencial"
    if "HIBRID" in clave:
        return "Híbrido"
    if "VIRTUAL" in clave:
        return "Virtual"
    return ""


_ORDINALES_CICLO: dict[str, str] = {
    "PRIMERO": "1",
    "SEGUNDO": "2",
    "TERCERO": "3",
    "CUARTO": "4",
    "QUINTO": "5",
    "SEXTO": "6",
    "SEPTIMO": "7",
    "OCTAVO": "8",
    "NOVENO": "9",
    "DECIMO": "10",
}
_NUMEROS_CREDITOS: dict[str, str] = {
    "UNO": "1",
    "UNA": "1",
    "DOS": "2",
    "TRES": "3",
    "CUATRO": "4",
    "CINCO": "5",
    "SEIS": "6",
    "SIETE": "7",
    "OCHO": "8",
    "NUEVE": "9",
    "DIEZ": "10",
}


def _naturaleza_curso(valor: object) -> str:
    """Publica la naturaleza declarada de la asignatura, sin inferir modalidad."""

    texto = _texto(valor)
    if not texto:
        return ""
    clave = _clave_carrera(texto)
    if "OBLIGAT" in clave:
        return "Obligatorio"
    if "ELECTIV" in clave:
        return "Electivo"
    return texto[:1].upper() + texto[1:].lower()


def _numero_creditos(valor: object) -> str:
    """curso.csv publica los créditos como número entero."""

    texto = _texto(valor)
    if not texto:
        return ""
    coincidencia = re.search(r"\d+", texto)
    if coincidencia:
        return coincidencia.group(0)
    palabras = _clave_carrera(texto).split("_")
    for palabra in palabras:
        if palabra in _NUMEROS_CREDITOS:
            return _NUMEROS_CREDITOS[palabra]
    return ""


def _numero_ciclo(valor: object) -> str:
    """curso.csv publica el ciclo como número, tomando el primer ordinal declarado."""

    texto = _texto(valor)
    if not texto:
        return ""
    palabras = _clave_carrera(texto).split("_")
    posiciones = [
        (palabras.index(palabra), numero)
        for palabra, numero in _ORDINALES_CICLO.items()
        if palabra in palabras
    ]
    if posiciones:
        return min(posiciones)[1]
    coincidencia = re.search(r"\d+", texto)
    return coincidencia.group(0) if coincidencia else ""


def _filas_curso(
    registros: list[dict[str, object]],
    carrera_ejecucion: str,
    id_carrera: str,
    hallazgos: list[Hallazgo],
    cuarentena: list[dict[str, object]],
) -> list[dict[str, str]]:
    """Materialize one stable row per course without inferring unknown careers."""

    if not id_carrera:
        _error(
            hallazgos,
            cuarentena,
            "CARRERA_AUTORITATIVA_DESCONOCIDA",
            "La carrera de la ejecución no tiene una asociación CAR autorizada.",
            "curso.csv",
            "",
            carrera_ejecucion,
        )
        return []

    cursos: dict[str, dict[str, str]] = {}
    campos = ("nombre_curso", "coordinador", "creditos", "nivel", "tipo_curso", "codigo_curso")
    for registro in registros:
        if _texto(registro.get("carrera")).upper() != carrera_ejecucion:
            continue
        datos_objeto = registro.get("datos")
        datos = datos_objeto if isinstance(datos_objeto, dict) else {}
        id_curso = _texto(registro.get("id_curso"))
        archivo = _archivo_origen(registro)
        if not id_curso:
            continue
        fila = {
            "id_curso": id_curso,
            "nombre_curso": _texto(datos.get("nombre_curso") or datos.get("curso")),
            "coordinador": _texto(datos.get("coordinador")),
            "creditos": _numero_creditos(datos.get("creditos")),
            "nivel": _numero_ciclo(datos.get("nivel") or datos.get("ciclo")),
            "tipo_curso": _naturaleza_curso(datos.get("tipo_curso")),
            "codigo_curso": _texto(datos.get("codigo_curso")),
            "id_carrera": id_carrera,
        }
        anterior = cursos.get(id_curso)
        if anterior is not None:
            conflictos = [
                campo
                for campo in campos
                if anterior[campo] and fila[campo] and anterior[campo] != fila[campo]
            ]
            if conflictos:
                _error(
                    hallazgos,
                    cuarentena,
                    "CURSO_DUPLICADO_CON_CONFLICTO",
                    "El mismo id_curso declara metadatos incompatibles.",
                    "curso.csv",
                    id_curso,
                    ", ".join(conflictos),
                )
                continue
            for campo in campos:
                if not anterior[campo]:
                    anterior[campo] = fila[campo]
            continue
        cursos[id_curso] = fila
        for campo in ("coordinador", "creditos", "nivel", "tipo_curso", "codigo_curso"):
            if not fila[campo]:
                hallazgos.append(
                    Hallazgo(
                        codigo="METADATO_CURSO_AUSENTE",
                        severidad="warning",
                        mensaje="El sílabo no declaró un metadato opcional del curso.",
                        hoja=archivo,
                        campo=campo,
                        detalle=id_curso,
                    )
                )
    return [cursos[id_curso] for id_curso in sorted(cursos)]


def _error(
    hallazgos: list[Hallazgo],
    cuarentena: list[dict[str, object]],
    codigo: str,
    mensaje: str,
    archivo: str,
    id_silabo: str,
    detalle: str = "",
) -> None:
    hallazgos.append(
        Hallazgo(
            codigo=codigo,
            severidad="error",
            mensaje=mensaje,
            hoja=archivo or None,
            detalle=detalle or id_silabo,
        )
    )
    cuarentena.append(
        {
            "id_silabo": id_silabo,
            "archivo": archivo,
            "codigo": codigo,
            "mensaje": mensaje,
            "detalle": detalle,
        }
    )


def _warning(
    hallazgos: list[Hallazgo],
    codigo: str,
    mensaje: str,
    archivo: str,
    id_silabo: str,
    detalle: str = "",
) -> None:
    hallazgos.append(
        Hallazgo(
            codigo=codigo,
            severidad="warning",
            mensaje=mensaje,
            hoja=archivo or None,
            detalle=detalle or id_silabo,
        )
    )


def _fila_cobertura(
    relacion: tuple[str, str, str, str, str],
    prefijo: str,
    *,
    id_ejecucion: str = "",
    id_logro: str = "",
    id_competencia_fuente: str = "",
    id_habilidad_fuente: str = "",
    id_herramienta_fuente: str = "",
    id_competencia_canonica: str = "",
    id_habilidad_canonica: str = "",
    id_herramienta_canonica: str = "",
    source_ref: str = "",
) -> dict[str, str]:
    id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta = relacion
    fila = {
        "id_cob_curricular": _hash_id(
            prefijo,
            id_curso,
            id_silabo,
            id_competencia,
            id_habilidad,
            id_herramienta,
        ),
        "id_curso": id_curso,
        "id_silabo": id_silabo,
        "id_competencia": id_competencia,
        "id_habilidad": id_habilidad,
        "id_herramienta": id_herramienta,
    }
    if any(
        (
            id_ejecucion,
            id_logro,
            id_competencia_fuente,
            id_habilidad_fuente,
            id_herramienta_fuente,
            id_competencia_canonica,
            id_habilidad_canonica,
            id_herramienta_canonica,
            source_ref,
        )
    ):
        fila.update(
            {
                "id_ejecucion": id_ejecucion,
                "id_logro": id_logro,
                "id_competencia_fuente": id_competencia_fuente,
                "id_habilidad_fuente": id_habilidad_fuente,
                "id_herramienta_fuente": id_herramienta_fuente,
                "id_competencia_canonica": id_competencia_canonica,
                "id_habilidad_canonica": id_habilidad_canonica,
                "id_herramienta_canonica": id_herramienta_canonica,
                "source_ref": source_ref,
            }
        )
    return fila


def _registrar_pendiente(
    pendientes: list[dict[str, object]],
    *,
    tipo: str,
    estado: str,
    motivo: str,
    id_curso: str,
    id_silabo: str,
    archivo: str,
    id_habilidad_fuente: str,
    descripcion: str,
    propuesta: dict[str, object] | None = None,
    evidencia: list[str] | None = None,
    evidencia_provenance: dict[str, str] | None = None,
    confianza: float | None = None,
) -> dict[str, object]:
    nombre_propuesta = _texto((propuesta or {}).get("nombre") or (propuesta or {}).get("id"))
    pendiente = {
        "id_pendiente": _hash_id(
            "PEN",
            tipo,
            id_silabo,
            id_habilidad_fuente,
            motivo,
            nombre_propuesta,
        ),
        "tipo": tipo,
        "estado_resolucion": estado,
        "motivo": motivo,
        "id_curso": id_curso,
        "id_silabo": id_silabo,
        "archivo": archivo,
        "id_habilidad_fuente": id_habilidad_fuente,
        "descripcion_fuente": descripcion,
        "propuesta": propuesta,
        "evidencia": list(evidencia or []),
        "evidencia_provenance": dict(evidencia_provenance or {}),
        "confianza": confianza,
    }
    pendientes.append(pendiente)
    return pendiente


def _pendientes_por_relacion_fuente(
    pendientes: Sequence[Mapping[str, object]],
    relaciones_fuente: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Materialize independent review rows for declared source relation units."""

    source_relations = tuple(relaciones_fuente)
    by_source_skill: dict[tuple[str, str, str], list[Mapping[str, object]]] = {}
    for relacion in source_relations:
        key = (
            _texto(relacion.get("id_curso")),
            _texto(relacion.get("id_silabo")),
            _texto(relacion.get("id_habilidad_fuente")),
        )
        if all(key):
            by_source_skill.setdefault(key, []).append(relacion)

    materialized: list[dict[str, object]] = []
    for pendiente in pendientes:
        row = dict(pendiente)
        key = (
            _texto(row.get("id_curso")),
            _texto(row.get("id_silabo")),
            _texto(row.get("id_habilidad_fuente")),
        )
        matches = by_source_skill.get(key, [])
        id_herramienta_fuente = _texto(row.get("id_herramienta_fuente"))
        if _texto(row.get("tipo")) == "herramienta" and id_herramienta_fuente:
            matches = [
                relacion
                for relacion in matches
                if _texto(relacion.get("id_herramienta_fuente")) == id_herramienta_fuente
            ]
        relation_ids = tuple(
            dict.fromkeys(_texto(relacion.get("id_cob_curricular")) for relacion in matches)
        )
        complete_ids = tuple(relation_id for relation_id in relation_ids if relation_id)
        if not matches or not complete_ids:
            if len(matches) > 1:
                row["package_identity_error"] = (
                    "Las relaciones fuente múltiples no tienen id_cob_curricular; "
                    "no se puede crear una decisión de paquete segura."
                )
            materialized.append(row)
            continue
        if len(complete_ids) != len(relation_ids):
            row["package_identity_error"] = (
                "Las relaciones fuente mezclan identidades ausentes y presentes; "
                "no se puede crear una decisión de paquete segura."
            )
            materialized.append(row)
            continue
        for relation_id in complete_ids:
            scoped = dict(row)
            scoped["id_pendiente_origen"] = _texto(row.get("id_pendiente"))
            scoped["id_pendiente"] = _hash_id("PEN_REL", scoped["id_pendiente_origen"], relation_id)
            scoped["id_cob_curricular"] = relation_id
            materialized.append(scoped)
    return materialized


def _archivo_origen(registro: dict[str, object]) -> str:
    origen = registro.get("origen")
    return _texto(origen.get("archivo")) if isinstance(origen, dict) else ""


def _source_ref(archivo: str, id_silabo: str) -> str:
    """Return a stable reference to the source curriculum artifact."""

    return archivo or id_silabo


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _hash_id(prefijo: str, *partes: str) -> str:
    payload = "|".join(clave_concepto(parte) for parte in partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _estado_resolucion_determinista(resolucion: ResolucionConcepto) -> str:  # noqa: F821
    if resolucion.concepto is not None:
        return "CANONIZADA"
    if resolucion.metodo == "AMBIGUA_O_INSUFICIENTE":
        return ESTADO_REVISION_HUMANA
    return ESTADO_PENDIENTE_CATALOGACION


def _propuesta_dict(nombre: str, descripcion: str, tipo: str) -> dict[str, object]:
    return {
        "nombre": _texto(nombre),
        "descripcion": _texto(descripcion),
        "tipo": _texto(tipo),
    }
