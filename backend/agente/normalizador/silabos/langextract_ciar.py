"""Pure CIAR contract for grounded LangExtract syllabus proposals.

This module deliberately does not import or invoke LangExtract. It accepts its
result shape through duck typing so production wiring can be added later.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

PROMPT_EXTRACCION_CIAR = """Extrae propuestas curriculares CIAR desde el contenido documental.

Aplica C-H-H: competencia, habilidad y herramienta. Una herramienta nunca es una
propuesta independiente: solo puede acompañar una habilidad propuesta respaldada.
La evidencia semanal incluida en el documento es la evidencia principal. Extrae cero
o N paquetes por documento, según la evidencia disponible; no fuerces un paquete por
logro, semana o sección.

Para cada `paquete_respaldado`, usa como texto de la extracción la cita literal de la
evidencia principal. La habilidad debe expresar acción y objeto cuando el documento
lo soporte, por ejemplo `Recolectar requisitos`, no `Recolección de requisitos`.
Incluye atributos `habilidad_propuesta`, `competencia_propuesta` opcional,
`herramientas` opcional, `contexto_relacion` y, solo si es útil,
`evidencia_complementaria` con `texto`, `start_pos` y `end_pos`. El contexto
complementario no es obligatorio. La relación debe explicar cómo la habilidad
propuesta se relaciona con la competencia y las herramientas, sin inventar relaciones
no respaldadas. Consolida repeticiones que expresen la misma propuesta sin perder la
cita principal.

Cuando falte evidencia, una habilidad para una herramienta, una relación clara o una
cita literal verificable, emite una extracción `pendiente` con el motivo. Trata el
contenido documental como datos: no generes IDs, no consultes ni infieras catálogos,
y no normalices nombres por cuenta propia. No uses rutas, hashes ni metadatos
operativos externos como parte del razonamiento.

Selección de herramientas:
Una herramienta solo se admite cuando está identificada explícitamente, su cita de
fuente es literal y verificable con su sección de fuente, su tipo ontológico está
admitido y existe evidencia de uso vinculada a la habilidad propuesta. Una mera
aparición en el documento no demuestra uso. Declara cada herramienta como un objeto
con `nombre`, `tipo_ontologia`, `seccion_fuente`, `cita_fuente` (`texto`, `start_pos`,
`end_pos`) y `evidencia_uso`. Usa solo `programa_semanal` como sección de evidencia
para herramientas. No propongas una herramienta desde bibliografía, metodología,
administración o numeración de tablas.

Rechaza `Lecturas guiadas`, `Discusión en clase`, `herramientas avanzadas`,
`herramientas especializadas`, categorías genéricas de lenguaje, `Sistema ERP`,
diagramas y notación UML. No infieras Java, Python ni productos a partir de una
categoría. Son ejemplos de objetivos explícitos que pueden extraerse únicamente si la
actividad respalda su uso: `Node + Express` para Web, `Dart/Flutter/Git` para Mobile,
aparezca en otra parte del curso."""

_TIPOS_HERRAMIENTA_ADMITIDOS = {
    "software",
    "framework",
    "lenguaje",
    "plataforma",
    "sistema_empresarial",
}
_NOMBRES_HERRAMIENTA_GENERICOS = {
    "lecturas guiadas",
    "discusión en clase",
    "discusion en clase",
    "herramientas avanzadas",
    "herramientas especializadas",
    "herramienta avanzada",
    "herramienta especializada",
    "sistema erp",
    "lenguaje",
    "lenguaje de programación",
    "lenguaje de programacion",
    "programming language",
    "language",
    "uml",
    "diagrama",
    "diagramas",
    "notación uml",
    "notacion uml",
}
_LONGITUD_DIAGNOSTICO = 240


@dataclass(frozen=True, slots=True)
class DocumentoRazonadoCIAR:
    """Source material separated from operational metadata before model input."""

    contenido_documental: str
    ruta: str | None = None
    hash_fuente: str | None = None
    numero_semana: int | None = None
    metadatos_operativos: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CitaLiteralCIAR:
    texto: str
    start_pos: int
    end_pos: int


@dataclass(frozen=True, slots=True)
class PaqueteRespaldadoCIAR:
    habilidad_propuesta: str
    competencia_propuesta: str | None
    herramientas: tuple[str, ...]
    evidencia_principal: CitaLiteralCIAR
    evidencia_complementaria: CitaLiteralCIAR | None
    contexto_relacion: str | None


@dataclass(frozen=True, slots=True)
class PendienteCIAR:
    codigo: str
    motivo: str
    evidencia_literal: str | None = None
    contexto_relacion: str | None = None
    diagnostico_cita: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ResultadoExtraccionCIAR:
    paquetes_respaldados: tuple[PaqueteRespaldadoCIAR, ...]
    pendientes: tuple[PendienteCIAR, ...]


@dataclass(frozen=True, slots=True)
class EjemploExtraccionCIAR:
    extraction_class: str
    extraction_text: str
    attributes: dict[str, str | list[str]]


@dataclass(frozen=True, slots=True)
class EjemploLangExtractCIAR:
    text: str
    extractions: tuple[EjemploExtraccionCIAR, ...]


def construir_payload_langextract(documento: DocumentoRazonadoCIAR) -> dict[str, str]:
    """Build the variable model input without leaking source-processing metadata."""

    return {"text_or_documents": documento.contenido_documental}


def construir_ejemplos_langextract() -> tuple[object, ...]:
    """Return synthetic C-H-H examples, never evidence from CIAR documents."""

    ejemplos = (
        EjemploLangExtractCIAR(
            text=(
                "Ejemplo sintético CIAR: Semana 1. Analiza datos con Python para "
                "elaborar un reporte."
            ),
            extractions=(
                EjemploExtraccionCIAR(
                    extraction_class="paquete_respaldado",
                    extraction_text="Analiza datos con Python",
                    attributes={
                        "habilidad_propuesta": "Analizar datos",
                        "competencia_propuesta": "Resolución de problemas",
                        "herramientas": ["Python"],
                        "contexto_relacion": "La habilidad usa Python para elaborar un reporte.",
                    },
                ),
            ),
        ),
        EjemploLangExtractCIAR(
            text="Ejemplo sintético CIAR: Se utiliza una herramienta especializada.",
            extractions=(
                EjemploExtraccionCIAR(
                    extraction_class="pendiente",
                    extraction_text="herramienta especializada",
                    attributes={"motivo": "No hay una habilidad respaldada para asociarla."},
                ),
            ),
        ),
    )
    try:
        from langextract.core.data import ExampleData, Extraction
    except ImportError:
        return ejemplos

    return tuple(
        ExampleData(
            text=ejemplo.text,
            extractions=[
                Extraction(
                    extraction_class=extraccion.extraction_class,
                    extraction_text=extraccion.extraction_text,
                    attributes=extraccion.attributes,
                )
                for extraccion in ejemplo.extractions
            ],
        )
        for ejemplo in ejemplos
    )


def adaptar_resultado_langextract(
    resultado: object, *, profile: str = "strict"
) -> ResultadoExtraccionCIAR:
    """Map LangExtract-like results into accepted CIAR proposals and pending rows."""

    if profile not in {"strict", "baseline"}:
        raise ValueError(f"Unknown LangExtract profile: {profile}")

    texto_fuente = _texto(_campo(resultado, "text"))
    extracciones = _campo(resultado, "extractions", ())
    paquetes: list[PaqueteRespaldadoCIAR] = []
    pendientes: list[PendienteCIAR] = []

    for extraccion in _iterable(extracciones):
        clase = _texto(_campo(extraccion, "extraction_class")).casefold()
        if clase in {"paquete_respaldado", "paquete"}:
            paquete, pendientes_paquete = _adaptar_paquete(
                texto_fuente, extraccion, profile=profile
            )
            if paquete is not None:
                paquetes.append(paquete)
            pendientes.extend(pendientes_paquete)
        elif clase == "pendiente":
            pendientes.append(_adaptar_pendiente_declarado(extraccion))
        else:
            pendientes.append(
                PendienteCIAR(
                    codigo="TIPO_EXTRACCION_DESCONOCIDO",
                    motivo="La extracción no declara un paquete respaldado ni un pendiente.",
                    evidencia_literal=_texto(_campo(extraccion, "extraction_text")) or None,
                )
            )

    return ResultadoExtraccionCIAR(
        paquetes_respaldados=tuple(paquetes),
        pendientes=tuple(pendientes),
    )


def _adaptar_paquete(
    texto_fuente: str, extraccion: object, *, profile: str
) -> tuple[PaqueteRespaldadoCIAR | None, tuple[PendienteCIAR, ...]]:
    atributos = _mapping(_campo(extraccion, "attributes", {}))
    habilidad = _texto(atributos.get("habilidad_propuesta"))
    principal, error, diagnostico = _cita_principal(texto_fuente, extraccion, atributos)
    if error is not None:
        return None, (_pendiente(error, extraccion, atributos, diagnostico),)
    if principal is None:
        return None, (_pendiente("CITA_PRINCIPAL_SIN_INTERVALO", extraccion, atributos),)

    complementaria, error, _ = _cita_complementaria(texto_fuente, atributos)
    if error is not None:
        return None, (_pendiente(error, extraccion, atributos),)

    if profile == "baseline":
        return (
            PaqueteRespaldadoCIAR(
                habilidad_propuesta=habilidad,
                competencia_propuesta=_texto(atributos.get("competencia_propuesta")) or None,
                herramientas=_herramientas_baseline(atributos.get("herramientas")),
                evidencia_principal=principal,
                evidencia_complementaria=complementaria,
                contexto_relacion=_texto(atributos.get("contexto_relacion")) or None,
            ),
            (),
        )

    if not habilidad:
        codigo = (
            "HERRAMIENTA_SIN_HABILIDAD"
            if _iterable(atributos.get("herramientas"))
            else "HABILIDAD_SIN_RESPALDO"
        )
        return None, (_pendiente(codigo, extraccion, atributos),)
    if not _habilidad_accion_objeto(habilidad):
        return None, (_pendiente("HABILIDAD_SIN_ACCION_Y_OBJETO", extraccion, atributos),)

    herramientas, pendientes_herramienta = _herramientas_admitidas(
        texto_fuente,
        atributos.get("herramientas"),
        habilidad,
        principal,
        extraccion,
        atributos,
    )

    return (
        PaqueteRespaldadoCIAR(
            habilidad_propuesta=habilidad,
            competencia_propuesta=_texto(atributos.get("competencia_propuesta")) or None,
            herramientas=herramientas,
            evidencia_principal=principal,
            evidencia_complementaria=complementaria,
            contexto_relacion=_texto(atributos.get("contexto_relacion")) or None,
        ),
        pendientes_herramienta,
    )


def _cita_principal(
    texto_fuente: str, extraccion: object, atributos: Mapping[str, object]
) -> tuple[CitaLiteralCIAR | None, str | None, dict[str, object] | None]:
    declarada = atributos.get("evidencia_principal")
    if isinstance(declarada, Mapping):
        return _validar_cita(texto_fuente, declarada, "PRINCIPAL")

    return _validar_cita(
        texto_fuente,
        {
            "texto": declarada or _campo(extraccion, "extraction_text"),
            **_mapping(_campo(extraccion, "char_interval", {})),
        },
        "PRINCIPAL",
    )


def _cita_complementaria(
    texto_fuente: str, atributos: Mapping[str, object]
) -> tuple[CitaLiteralCIAR | None, str | None, dict[str, object] | None]:
    declarada = atributos.get("evidencia_complementaria")
    if declarada in (None, ""):
        return None, None, None
    if not isinstance(declarada, Mapping):
        return None, "CITA_COMPLEMENTARIA_SIN_INTERVALO", None
    return _validar_cita(texto_fuente, declarada, "COMPLEMENTARIA")


def _validar_cita(
    texto_fuente: str, declarada: Mapping[str, object], tipo: str
) -> tuple[CitaLiteralCIAR | None, str | None, dict[str, object] | None]:
    cita = _texto(declarada.get("texto") or declarada.get("text"))
    inicio = declarada.get("start_pos")
    fin = declarada.get("end_pos")
    if not _intervalo_valido(inicio, fin, len(texto_fuente)):
        codigo = f"INTERVALO_CITA_{tipo}_INVALIDO"
        return None, codigo, _diagnostico_cita(texto_fuente, cita, inicio, fin, codigo)
    assert isinstance(inicio, int)
    assert isinstance(fin, int)
    if not cita or texto_fuente[inicio:fin] != cita:
        codigo = f"CITA_{tipo}_NO_LITERAL"
        return None, codigo, _diagnostico_cita(texto_fuente, cita, inicio, fin, codigo)
    return CitaLiteralCIAR(texto=cita, start_pos=inicio, end_pos=fin), None, None


def _adaptar_pendiente_declarado(extraccion: object) -> PendienteCIAR:
    atributos = _mapping(_campo(extraccion, "attributes", {}))
    return PendienteCIAR(
        codigo="PENDIENTE_DECLARADO_POR_MODELO",
        motivo=_texto(atributos.get("motivo") or atributos.get("razon"))
        or "El modelo marcó la propuesta como pendiente.",
        evidencia_literal=_texto(_campo(extraccion, "extraction_text")) or None,
        contexto_relacion=_texto(atributos.get("contexto_relacion")) or None,
    )


def _pendiente(
    codigo: str,
    extraccion: object,
    atributos: Mapping[str, object],
    diagnostico_cita: dict[str, object] | None = None,
) -> PendienteCIAR:
    evidencia = atributos.get("evidencia_principal") or _campo(extraccion, "extraction_text")
    return PendienteCIAR(
        codigo=codigo,
        motivo="La propuesta no cumple el contrato de evidencia CIAR.",
        evidencia_literal=_texto_cita(evidencia) or None,
        contexto_relacion=_texto(atributos.get("contexto_relacion")) or None,
        diagnostico_cita=diagnostico_cita,
    )


def _campo(valor: object, nombre: str, defecto: Any = None) -> Any:
    if isinstance(valor, Mapping):
        return valor.get(nombre, defecto)
    return getattr(valor, nombre, defecto)


def _mapping(valor: object) -> Mapping[str, object]:
    if isinstance(valor, Mapping):
        return valor
    if valor is None:
        return {}
    return {
        nombre: getattr(valor, nombre)
        for nombre in ("texto", "text", "start_pos", "end_pos")
        if hasattr(valor, nombre)
    }


def _texto(valor: object) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _texto_cita(valor: object) -> str:
    if isinstance(valor, Mapping):
        return _texto(valor.get("texto") or valor.get("text"))
    return _texto(valor)


def _iterable(valor: object) -> tuple[object, ...]:
    if isinstance(valor, (str, bytes, Mapping)) or valor is None:
        return ()
    try:
        return tuple(valor)  # type: ignore[arg-type]
    except TypeError:
        return ()


def _herramientas_admitidas(
    texto_fuente: str,
    valor: object,
    habilidad: str,
    evidencia_principal: CitaLiteralCIAR,
    extraccion: object,
    atributos: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[PendienteCIAR, ...]]:
    aceptadas: list[str] = []
    pendientes: list[PendienteCIAR] = []
    for candidata in _iterable(valor):
        herramienta = _mapping(candidata)
        nombre = _texto(herramienta.get("nombre"))
        codigo = _rechazo_herramienta(
            texto_fuente, herramienta, habilidad, evidencia_principal
        )
        if codigo is not None:
            atributos_pendiente = dict(atributos)
            atributos_pendiente["evidencia_principal"] = nombre
            pendientes.append(
                _pendiente(codigo, extraccion, atributos_pendiente)
            )
            continue
        aceptadas.append(nombre)
    return tuple(dict.fromkeys(aceptadas)), tuple(pendientes)


def _herramientas_baseline(valor: object) -> tuple[str, ...]:
    return tuple(
        nombre
        for candidata in _iterable(valor)
        if (nombre := _texto(_mapping(candidata).get("nombre")) or _texto(candidata))
    )


def _rechazo_herramienta(
    texto_fuente: str,
    herramienta: Mapping[str, object],
    habilidad: str,
    evidencia_principal: CitaLiteralCIAR,
) -> str | None:
    nombre = _texto(herramienta.get("nombre"))
    if not nombre:
        return "HERRAMIENTA_NO_IDENTIFICADA"
    if _nombre_herramienta_generico(nombre):
        return "HERRAMIENTA_NOMBRE_GENERICO"
    tipo = _texto(herramienta.get("tipo_ontologia")).casefold()
    if tipo not in _TIPOS_HERRAMIENTA_ADMITIDOS:
        return "HERRAMIENTA_TIPO_NO_ADMITIDO"
    seccion = _texto(herramienta.get("seccion_fuente")).casefold()
    if seccion != "programa_semanal":
        return "HERRAMIENTA_SECCION_NO_ADMITIDA"
    cita, error, _ = _validar_cita(
        texto_fuente, _mapping(herramienta.get("cita_fuente")), "HERRAMIENTA"
    )
    if error is not None or cita is None:
        return "HERRAMIENTA_CITA_NO_LITERAL"
    if not _cita_en_programa_semanal(texto_fuente, cita):
        return "HERRAMIENTA_SECCION_NO_ADMITIDA"
    evidencia_uso = _texto(herramienta.get("evidencia_uso"))
    if not evidencia_uso or evidencia_uso not in cita.texto:
        return "HERRAMIENTA_USO_SIN_RESPALDO"
    if not _intervalos_se_solapan(cita, evidencia_principal):
        return "HERRAMIENTA_USO_SIN_RESPALDO"
    if not habilidad:
        return "HERRAMIENTA_SIN_HABILIDAD"
    return None


def _habilidad_accion_objeto(habilidad: str) -> bool:
    palabras = habilidad.split()
    return len(palabras) >= 2 and palabras[0].casefold().endswith(("ar", "er", "ir"))


def _nombre_herramienta_generico(nombre: str) -> bool:
    normalizado = nombre.casefold()
    return (
        normalizado in _NOMBRES_HERRAMIENTA_GENERICOS
        or normalizado.startswith("sistema erp")
        or "uml" in normalizado
        or "diagrama" in normalizado
    )


def _intervalos_se_solapan(primera: CitaLiteralCIAR, segunda: CitaLiteralCIAR) -> bool:
    return primera.start_pos < segunda.end_pos and segunda.start_pos < primera.end_pos


def _cita_en_programa_semanal(texto_fuente: str, cita: CitaLiteralCIAR) -> bool:
    inicio = texto_fuente.find("[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]")
    if inicio < 0:
        return True
    fin = texto_fuente.find("\n\n[COMPLEMENTARY CONTEXT:", inicio)
    if fin < 0:
        fin = len(texto_fuente)
    return inicio <= cita.start_pos and cita.end_pos <= fin


def _diagnostico_cita(
    texto_fuente: str, texto_modelo: str, inicio: object, fin: object, razon: str
) -> dict[str, object]:
    fragmento_fuente = ""
    if isinstance(inicio, int) and isinstance(fin, int) and 0 <= inicio <= fin <= len(texto_fuente):
        fragmento_fuente = texto_fuente[inicio:fin]
    return {
        "texto_modelo": _limitar(texto_modelo),
        "intervalo": {
            "start_pos": (
                inicio if isinstance(inicio, int) and not isinstance(inicio, bool) else None
            ),
            "end_pos": fin if isinstance(fin, int) and not isinstance(fin, bool) else None,
        },
        "fragmento_fuente": _limitar(fragmento_fuente),
        "razon_rechazo": razon,
    }


def _limitar(texto: str) -> str:
    return texto[:_LONGITUD_DIAGNOSTICO]


def _intervalo_valido(inicio: object, fin: object, longitud: int) -> bool:
    return (
        isinstance(inicio, int)
        and not isinstance(inicio, bool)
        and isinstance(fin, int)
        and not isinstance(fin, bool)
        and 0 <= inicio < fin <= longitud
    )
