"""Inference of technical competencies with a career-scoped local-model context."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openpyxl import load_workbook
from pydantic import BaseModel, Field

from agente.config.settings import ConfiguracionNormalizadorCurricular
from agente.llm.fabrica import obtener_llm

COLUMNAS_CATALOGO_TECNICO_XLSX = ("Carrera", "Habilidad tecnica", "Descripcion")
COLUMNAS_CATALOGO_TECNICO_CSV = (
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
    "codigo_competencia",
    "carreras_origen",
    "cantidad_carreras",
    "cantidad_apariciones_catalogo",
    "cantidad_silabos_relacionados",
    "cantidad_logros_relacionados",
    "descripciones_alternativas",
)
_FilaCatalogo = tuple[int, str, str, str]


@dataclass(frozen=True)
class CandidatoTecnico:
    """One source row; its reference is not a graph identifier."""

    referencia: str
    carrera: str
    nombre: str
    descripcion: str
    fila: int

    def a_dict(self) -> dict[str, str]:
        return {
            "catalogo_ref": self.referencia,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
        }


@dataclass(frozen=True)
class CatalogoTecnico:
    """Immutable catalog snapshot used by one local-model run."""

    candidatos: tuple[CandidatoTecnico, ...]
    origen: str
    sha256: str
    hoja: str

    def para_carrera(self, carrera: str) -> tuple[CandidatoTecnico, ...]:
        carrera_exacta = _texto(carrera)
        return tuple(
            sorted(
                (candidato for candidato in self.candidatos if candidato.carrera == carrera_exacta),
                key=lambda candidato: (clave_catalogo(candidato.nombre), candidato.referencia),
            )
        )

    def a_dict(self) -> dict[str, object]:
        return {
            "origen": self.origen,
            "sha256": self.sha256,
            "hoja": self.hoja,
            "candidatos": len(self.candidatos),
        }


def clave_catalogo(valor: object) -> str:
    """Normalize names for sorting, duplicate detection, and stable references."""

    texto = _texto(valor).replace("_", " ")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()


def _materializar_candidatos(filas: Iterable[_FilaCatalogo]) -> tuple[CandidatoTecnico, ...]:
    candidatos: list[CandidatoTecnico] = []
    vistos: dict[tuple[str, str], int] = {}
    for numero_fila, carreras_crudas, nombre, descripcion in filas:
        if not any((carreras_crudas, nombre, descripcion)):
            continue
        if not carreras_crudas or not nombre or not descripcion:
            raise ValueError(f"Fila {numero_fila} incompleta en el catálogo técnico")
        carreras = tuple(
            dict.fromkeys(
                carrera
                for fragmento in carreras_crudas.split(";")
                if (carrera := _texto(fragmento))
            )
        )
        if not carreras:
            raise ValueError(f"Fila {numero_fila} sin carreras en el catálogo técnico")
        material = "\x1f".join((carreras_crudas, nombre, descripcion)).encode("utf-8")
        referencia = f"CATTEC_{hashlib.sha256(material).hexdigest()[:16]}"
        for carrera in carreras:
            clave = (carrera, clave_catalogo(nombre))
            anterior = vistos.get(clave)
            if anterior is not None:
                raise ValueError(
                    "Competencia técnica duplicada para la misma carrera: "
                    f"filas {anterior} y {numero_fila}"
                )
            vistos[clave] = numero_fila
            candidatos.append(
                CandidatoTecnico(
                    referencia=referencia,
                    carrera=carrera,
                    nombre=nombre,
                    descripcion=descripcion,
                    fila=numero_fila,
                )
            )
    if not candidatos:
        raise ValueError("El catálogo técnico no contiene filas de datos")
    return tuple(candidatos)


def _cargar_filas_csv(origen: Path) -> tuple[tuple[CandidatoTecnico, ...], str]:
    with origen.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        encabezado = tuple(lector.fieldnames or ())
        if encabezado != COLUMNAS_CATALOGO_TECNICO_CSV:
            raise ValueError(
                "Esquema inválido para el catálogo técnico: "
                f"esperado={COLUMNAS_CATALOGO_TECNICO_CSV}; recibido={encabezado}"
            )
        filas: list[_FilaCatalogo] = []
        for fila in lector:
            if None in fila:
                raise ValueError(f"Fila {lector.line_num} con número de columnas inválido")
            if _texto(fila["tipo_competencia"]).casefold() != "tecnica":
                raise ValueError(f"Fila {lector.line_num} no es una competencia técnica")
            filas.append(
                (
                    lector.line_num,
                    _texto(fila["carreras_origen"]),
                    _texto(fila["nombre_competencia"]),
                    _texto(fila["descripcion_breve_competencia"]),
                )
            )
    return _materializar_candidatos(filas), "CSV"


def _cargar_filas_xlsx(origen: Path) -> tuple[tuple[CandidatoTecnico, ...], str]:
    libro = load_workbook(origen, read_only=True, data_only=True)
    try:
        if not libro.worksheets:
            raise ValueError("El catálogo técnico no contiene hojas")
        hoja = libro.worksheets[0]
        filas_xlsx = hoja.iter_rows(values_only=True)
        encabezado = tuple(_texto(valor) for valor in (next(filas_xlsx, ()) or ()))
        if encabezado != COLUMNAS_CATALOGO_TECNICO_XLSX:
            raise ValueError(
                "Esquema inválido para el catálogo técnico: "
                f"esperado={COLUMNAS_CATALOGO_TECNICO_XLSX}; recibido={encabezado}"
            )
        filas: list[_FilaCatalogo] = []
        for numero_fila, fila in enumerate(filas_xlsx, start=2):
            valores = tuple(fila or ())
            if not any(_texto(valor) for valor in valores):
                continue
            if len(valores) != len(COLUMNAS_CATALOGO_TECNICO_XLSX):
                raise ValueError(f"Fila {numero_fila} con número de columnas inválido")
            carrera, nombre, descripcion = (_texto(valor) for valor in valores)
            filas.append((numero_fila, carrera, nombre, descripcion))
        return _materializar_candidatos(filas), hoja.title
    finally:
        libro.close()


def cargar_catalogo_tecnico(ruta: Path | str) -> CatalogoTecnico:
    """Load the supported technical catalog formats without career aliases."""

    origen = Path(ruta).expanduser().resolve()
    if not origen.is_file():
        raise FileNotFoundError(f"No existe el catálogo técnico: {origen}")
    digest = hashlib.sha256(origen.read_bytes()).hexdigest()
    if origen.suffix.casefold() == ".csv":
        candidatos, hoja = _cargar_filas_csv(origen)
    elif origen.suffix.casefold() == ".xlsx":
        candidatos, hoja = _cargar_filas_xlsx(origen)
    else:
        raise ValueError("El catálogo técnico debe ser un archivo CSV o XLSX")
    return CatalogoTecnico(candidatos, origen.name, digest, hoja)


class EvidenciaCompetenciaTecnica(BaseModel):
    fuente: Literal["logro"]
    fragmento: str = Field(min_length=5, max_length=1200)


class CompetenciaTecnicaInferida(BaseModel):
    catalogo_ref: str | None = Field(default=None, max_length=80)
    nombre_competencia: str = Field(min_length=3, max_length=240)
    descripcion_breve_competencia: str = Field(min_length=10, max_length=1200)
    logros: list[str] = Field(default_factory=list, max_length=8)
    evidencia: list[EvidenciaCompetenciaTecnica] = Field(min_length=1, max_length=8)
    justificacion: str = Field(min_length=10, max_length=1200)
    requiere_revision: bool = True


class RespuestaCompetenciasTecnicas(BaseModel):
    competencias: list[CompetenciaTecnicaInferida] = Field(default_factory=list, max_length=12)


SYSTEM_PROMPT_TECNICO = (
    "You are a senior curricular analyst. Analyze one syllabus for one career. "
    "Infer only technical competencies demonstrable through curricular learning outcomes. "
    "The only valid evidence is the learning outcomes: no period, course summary, or weekly "
    "program is provided. Do not request or return confidence. Do not use generic or "
    "institutional competencies as technical competencies, do not invent tools, and do not "
    "expose chain of thought. The career catalog contains candidates, not facts: choose a "
    "candidate only if the syllabus learning outcomes support it. If none applies, use "
    "catalogo_ref=null and propose a new technical competency, which will remain pending human "
    "approval. For every proposal, include at least one specific learning outcome copied "
    "literally and literal evidence from a learning outcome. Do not summarize or paraphrase "
    "learning outcomes. Do not return graph IDs, institutional codes, or relationships. When "
    "using a candidate, copy its exact catalogo_ref; Python will preserve the original name and "
    "description from the catalog. If there is insufficient technical evidence, return "
    "competencias=[] and do not force a match; the run will reject that syllabus rather than "
    "inventing a competency."
)


def _texto(valor: object) -> str:
    return " ".join(str(valor or "").split())


def _clave_texto(valor: object) -> str:
    return _texto(valor).casefold()


def _lista_mapeos(valor: object) -> list[Mapping[str, object]]:
    if not isinstance(valor, Sequence) or isinstance(valor, (str, bytes)):
        return []
    return [fila for fila in valor if isinstance(fila, Mapping)]


def construir_contexto_tecnico(
    registro: Mapping[str, object],
    candidatos: Sequence[CandidatoTecnico] = (),
) -> dict[str, object]:
    """Reduce one syllabus to the evidence and career candidates allowed in the prompt."""

    datos = registro.get("datos")
    if not isinstance(datos, Mapping):
        raise ValueError("El registro no contiene datos curriculares")
    logros: list[dict[str, object]] = []
    logro_general = _texto(datos.get("logro_general"))
    if logro_general:
        logros.append({"tipo": "general", "orden": "", "texto": logro_general})
    for indice, logro in enumerate(_lista_mapeos(datos.get("logros_especificos")), start=1):
        texto = _texto(logro.get("descripcion") or logro.get("logro"))
        if texto:
            logros.append(
                {
                    "tipo": "especifico",
                    "orden": _texto(logro.get("orden")) or str(indice),
                    "texto": texto,
                }
            )
    return {
        "id_curso": _texto(registro.get("id_curso")),
        "id_silabo": _texto(registro.get("id_silabo")),
        "carrera": _texto(registro.get("carrera")),
        "periodo": _texto(registro.get("periodo")),
        "nombre_curso": _texto(datos.get("nombre_curso") or datos.get("curso")),
        "logros": logros,
        "catalogo_tecnico": [candidato.a_dict() for candidato in candidatos],
    }


def _payload_prompt(contexto: Mapping[str, object]) -> dict[str, object]:
    return {
        clave: contexto.get(clave)
        for clave in ("carrera", "nombre_curso", "logros", "catalogo_tecnico")
    }


def construir_prompt_tecnico(contexto: Mapping[str, object]) -> list[tuple[str, str]]:
    """Build the calibrated system/user messages without exposing graph identity."""

    return [
        ("system", SYSTEM_PROMPT_TECNICO),
        (
            "human",
            "Analizá este sílabo y devolvé únicamente el JSON solicitado:\n"
            + json.dumps(_payload_prompt(contexto), ensure_ascii=False, separators=(",", ":")),
        ),
    ]


def _resolver_catalogo(
    catalogo_tecnico: CatalogoTecnico | Path | str | None,
) -> CatalogoTecnico | None:
    if catalogo_tecnico is None or isinstance(catalogo_tecnico, CatalogoTecnico):
        return catalogo_tecnico
    return cargar_catalogo_tecnico(catalogo_tecnico)


def _evidencia_valida(
    evidencia: EvidenciaCompetenciaTecnica,
    contexto: Mapping[str, object],
) -> bool:
    if evidencia.fuente != "logro":
        return False
    return any(
        evidencia.fragmento in _texto(logro.get("texto"))
        for logro in _lista_mapeos(contexto.get("logros"))
    )


def _logros_especificos(
    contexto: Mapping[str, object],
    propuesta: CompetenciaTecnicaInferida,
) -> list[str] | None:
    disponibles = {
        _clave_texto(logro.get("texto")): _texto(logro.get("texto"))
        for logro in _lista_mapeos(contexto.get("logros"))
        if _texto(logro.get("tipo")) == "especifico" and _texto(logro.get("texto"))
    }
    encontrados: list[str] = []
    for logro in propuesta.logros:
        original = disponibles.get(_clave_texto(logro))
        if original is None:
            return None
        encontrados.append(original)
    return list(dict.fromkeys(encontrados))


def _id_propuesta(
    contexto: Mapping[str, object],
    propuesta: CompetenciaTecnicaInferida,
    logros: Sequence[str],
) -> str:
    material = "\x1f".join(
        (
            _texto(contexto.get("id_silabo")),
            _texto(propuesta.catalogo_ref),
            _texto(propuesta.nombre_competencia),
            _texto(propuesta.descripcion_breve_competencia),
            *sorted(logros),
        )
    ).encode("utf-8")
    return f"PROP_TEC_{hashlib.sha256(material).hexdigest()[:16]}"


def _materializar_propuesta(
    propuesta: CompetenciaTecnicaInferida,
    contexto: Mapping[str, object],
    candidatos: Mapping[str, CandidatoTecnico],
    exigir_logro: bool,
    catalogo: CatalogoTecnico | None,
) -> dict[str, object] | None:
    referencia = _texto(propuesta.catalogo_ref)
    candidato = candidatos.get(referencia) if referencia else None
    if referencia and candidato is None:
        return None
    logros = _logros_especificos(contexto, propuesta)
    if exigir_logro and not logros:
        return None
    if logros is None:
        return None
    if not all(_evidencia_valida(item, contexto) for item in propuesta.evidencia):
        return None

    if candidato is None:
        nombre = _texto(propuesta.nombre_competencia)
        descripcion = _texto(propuesta.descripcion_breve_competencia)
        origen = "LLM_NUEVA"
    else:
        nombre = candidato.nombre
        descripcion = candidato.descripcion
        origen = "CATALOGO_CARRERA"
    fila: dict[str, object] = {
        "id_propuesta": _id_propuesta(contexto, propuesta, logros or []),
        "id_curso": _texto(contexto.get("id_curso")),
        "id_silabo": _texto(contexto.get("id_silabo")),
        "carrera": _texto(contexto.get("carrera")),
        "periodo": _texto(contexto.get("periodo")),
        "catalogo_ref": candidato.referencia if candidato is not None else "",
        "nombre_competencia": nombre,
        "descripcion_breve_competencia": descripcion,
        "origen_propuesta": origen,
        "estado_aprobacion": "PENDIENTE_APROBACION",
        "logros": logros or [],
        "evidencia": [item.model_dump(mode="json") for item in propuesta.evidencia],
        "justificacion": _texto(propuesta.justificacion),
        "requiere_revision": True,
    }
    if catalogo is not None:
        fila["catalogo_origen"] = catalogo.origen
        fila["catalogo_sha256"] = catalogo.sha256
        fila["catalogo_hoja"] = catalogo.hoja
    return fila


def inferir_competencias_tecnicas(
    registros: Sequence[Mapping[str, object]],
    configuracion: ConfiguracionNormalizadorCurricular,
    catalogo_tecnico: CatalogoTecnico | Path | str | None = None,
) -> list[dict[str, object]]:
    """Return pending technical proposals; Python owns IDs and relationships."""

    if not configuracion.usar_llm:
        return []
    catalogo = _resolver_catalogo(catalogo_tecnico)
    llm = obtener_llm("analista_curricular", configuracion_curricular=configuracion)
    analista = llm.with_structured_output(
        RespuestaCompetenciasTecnicas,
        method="json_schema",
    )
    resultado: list[dict[str, object]] = []
    vistos: set[tuple[str, str, tuple[str, ...]]] = set()
    for registro in registros:
        carrera = _texto(registro.get("carrera"))
        candidatos_lista = catalogo.para_carrera(carrera) if catalogo is not None else ()
        candidatos = {candidato.referencia: candidato for candidato in candidatos_lista}
        contexto = construir_contexto_tecnico(registro, candidatos_lista)
        respuesta = analista.invoke(construir_prompt_tecnico(contexto))
        if not isinstance(respuesta, RespuestaCompetenciasTecnicas):
            respuesta = RespuestaCompetenciasTecnicas.model_validate(respuesta)
        propuestas_validas = 0
        for propuesta in respuesta.competencias:
            fila = _materializar_propuesta(
                propuesta,
                contexto,
                candidatos,
                exigir_logro=catalogo_tecnico is not None,
                catalogo=catalogo,
            )
            if fila is None:
                continue
            propuestas_validas += 1
            clave = (
                _texto(fila["id_silabo"]),
                _texto(fila["catalogo_ref"]) or _clave_texto(fila["nombre_competencia"]),
                tuple(fila["logros"]) if isinstance(fila["logros"], list) else (),
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            resultado.append(fila)
        if propuestas_validas == 0:
            id_silabo = _texto(contexto.get("id_silabo")) or "<sin id>"
            raise ValueError(
                f"El sílabo {id_silabo} no produjo ninguna propuesta técnica "
                "con evidencia literal válida."
            )
    return resultado


def escribir_propuestas_tecnicas(
    ruta: Path | str,
    propuestas: Sequence[Mapping[str, object]],
) -> None:
    """Persist proposals as JSONL without materializing graph nodes or relations."""

    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="\n") as archivo:
        for propuesta in propuestas:
            archivo.write(
                json.dumps(dict(propuesta), ensure_ascii=False, separators=(",", ":")) + "\n"
            )
