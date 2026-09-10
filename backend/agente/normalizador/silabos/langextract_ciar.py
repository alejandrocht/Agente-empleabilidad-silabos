"""Pure CIAR contract for grounded LangExtract syllabus proposals.

This module deliberately does not import or invoke LangExtract. It accepts its
result shape through duck typing so production wiring can be added later.
"""

from __future__ import annotations

import json
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
La competencia es una capacidad profesional o de dominio específica respaldada por
el clúster técnico de evidencia, por ejemplo Ciberseguridad, Desarrollo de software,
Administración de sistemas ERP o Análisis de procesos. Una competencia institucional
o transversal puede conservarse solo como contexto declarado, no como
`competencia_propuesta`, cuando la evidencia respalda una propuesta de dominio
específica. Incluye atributos `habilidad_propuesta`, `competencia_propuesta` opcional,
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

Catalog tool candidates:
When detected catalog tool candidates are supplied in the document, they are the
only tools eligible for `herramientas_catalogo`. Attach one only when its literal
source evidence and the proposed skill support the relationship. Assign every
candidate whose literal mention supports the package's skill; omitting a supported
candidate is an error. Select the exact
candidate using `id_catalogo`, `start_pos`, and `end_pos`; retain its canonical
name and evidence unchanged. Put a literal `evidencia_uso` from that candidate's
`contexto_fuente` in the assignment and name the canonical tool in
`contexto_relacion`. Copy `evidencia_uso` character-for-character from
`contexto_fuente` (same casing, accents and punctuation); a paraphrase or an
invented fragment is rejected. Candidate evidence can come from any syllabus
section.
Never assign a candidate merely because it appears in the same course. Leave it
unassigned when the relationship is not supported. `herramientas_catalogo` is an
optional list of objects with `id_catalogo`, `start_pos`, `end_pos`, and
`evidencia_uso`.

Uncatalogued tool proposals:
Catalog candidates always take priority. Only when an explicitly named concrete
tool is absent from those candidates may it be emitted in
`herramientas_propuestas`. This is HITL-only, never has a canonical ID, and must
stay attached to one package with a non-empty proposed competency and skill.
Each object needs `nombre`, `tipo_ontologia`, `seccion_fuente`, `cita_fuente`
with exact literal `texto`, `start_pos`, and `end_pos`, plus `evidencia_uso`.
`tipo_ontologia` must be `software`, `framework`, `lenguaje`, `plataforma`,
`sistema_empresarial`, or the canonical library category `biblioteca`.
Normalize `libreria` and `library` as `biblioteca`.
The name itself must occur literally inside `cita_fuente`; do not infer tools
from activities, algorithms, methods, resource categories, or generic phrases.
Do not emit a proposal for a catalog candidate: link the candidate canonically
through `herramientas_catalogo` or leave it unassigned. Every concrete tool
explicitly named in the weekly activity that supports the skill must be emitted:
link it through `herramientas_catalogo` when it is a candidate, or propose it
here when it is absent from the candidates. Omitting an explicitly cited concrete
tool is an error. Copy `evidencia_uso` character-for-character from `cita_fuente`.

Selección de herramientas:
Una herramienta debe ser un nombre concreto citado literalmente en la actividad de
fuente. Solo se admite cuando su cita de fuente es literal y verificable con su
sección de fuente, su tipo ontológico está admitido y existe evidencia de uso
vinculada a la habilidad propuesta. Una mera aparición en el documento no demuestra
uso. Declara cada herramienta como un objeto con `nombre`, `tipo_ontologia`,
`seccion_fuente`, `cita_fuente` (`texto`, `start_pos`, `end_pos`) y `evidencia_uso`.
Usa solo `programa_semanal` como sección de evidencia para herramientas. No propongas
una herramienta desde bibliografía, metodología, administración o numeración de
tablas. Las categorías, métodos, estándares y nombres genéricos quedan ausentes o
pendientes; no infieras productos a partir de una categoría.

La `cita_fuente` de cada herramienta debe solaparse con la cita de la evidencia
principal del mismo paquete: extiende la cita principal hasta abarcar la mención de
la herramienta en lugar de citar un tramo separado. Si la herramienta aparece en otra
actividad, emite un `pendiente` en vez de forzar el vínculo. `evidencia_uso` debe ser
un fragmento textual contenido dentro de esa misma `cita_fuente`.

El `nombre` de la herramienta es el producto concreto tal como aparece citado en la
actividad, sin anteponerle su categoría ni expandirlo. Un nombre que empieza por una
palabra de categoría (`diagrama`, `notación`, `sistema`, `herramienta`, `lenguaje`,
`plataforma`, `framework`, `software`, `modelo`, `técnica`, `estándar`) describe una
clase de artefactos, no un producto: eso va a `pendiente`.

La `competencia_propuesta` nombra el dominio profesional del clúster de evidencia.
Correcto: `Ciberseguridad`, `Desarrollo de software`, `Administración de sistemas ERP`,
`Análisis de datos`, `Gestión de redes`. Incorrecto como `competencia_propuesta`:
`Resolución de problemas`, `Trabajo en equipo`, `Pensamiento crítico`, `Comunicación
efectiva`, `Aprendizaje autónomo`. No repitas el nombre de la asignatura: nombra el
dominio específico del clúster de evidencia (por ejemplo, en un curso de aprendizaje
de máquina: `Preprocesamiento de datos`, `Modelado predictivo`), no el área general.
Si el sílabo solo declara una competencia
transversal, deriva la competencia de dominio desde la evidencia técnica semanal y
menciona la transversal dentro de `contexto_relacion`."""

_TIPOS_HERRAMIENTA_ADMITIDOS = {
    "software",
    "framework",
    "lenguaje",
    "plataforma",
    "sistema_empresarial",
    "biblioteca",
}
_ALIASES_TIPO_HERRAMIENTA = {
    "libreria": "biblioteca",
    "biblioteca": "biblioteca",
    "library": "biblioteca",
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
# A category head noun names a class of artifacts, never a concrete product.
# Matching the head token keeps "StarUML" and "Diagrams.net" while still
# rejecting "diagrama de clases", "notación UML" or "sistema ERP".
_CABEZAS_HERRAMIENTA_GENERICAS = {
    "algoritmo",
    "algoritmos",
    "diagrama",
    "diagramas",
    "notacion",
    "notación",
    "modelo",
    "modelos",
    "metodologia",
    "metodología",
    "tecnica",
    "técnica",
    "tecnicas",
    "técnicas",
    "estandar",
    "estándar",
    "estandares",
    "estándares",
    "sistema",
    "sistemas",
    "herramienta",
    "herramientas",
    "lenguaje",
    "lenguajes",
    "plataforma",
    "plataformas",
    "framework",
    "frameworks",
    "metodo",
    "metodos",
    "método",
    "métodos",
    "recurso",
    "recursos",
    "software",
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
    catalog_tool_candidates: tuple[Mapping[str, object], ...] = ()
    structured_payload: Mapping[str, object] | None = None
    source_text: str | None = None
    source_evidence_map: tuple["SourceEvidenceSpan", ...] = ()


@dataclass(frozen=True, slots=True)
class SourceEvidenceSpan:
    """Maps a source-backed substring in the compact model payload to its source span."""

    payload_start: int
    payload_end: int
    source_start: int
    source_end: int


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
    herramientas_catalogo: tuple[dict[str, object], ...] = ()
    herramientas_propuestas: tuple[dict[str, object], ...] = ()


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
    attributes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EjemploLangExtractCIAR:
    text: str
    extractions: tuple[EjemploExtraccionCIAR, ...]


def construir_payload_langextract(documento: DocumentoRazonadoCIAR) -> dict[str, str]:
    """Build the variable model input without leaking source-processing metadata."""

    if documento.structured_payload is not None:
        contenido = json.dumps(documento.structured_payload, ensure_ascii=False, separators=(",", ":"))
    else:
        contenido = documento.contenido_documental
        if documento.catalog_tool_candidates:
            contenido += (
                "\n\n[DETECTED CATALOG TOOL CANDIDATES]\n"
                + json.dumps(documento.catalog_tool_candidates, ensure_ascii=False, sort_keys=True)
            )
    return {"text_or_documents": contenido}


_EJEMPLO_TEXTO_PAQUETE = (
    "[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]\n"
    "Ejemplo sintético CIAR: Semana 1. Analiza datos de ventas con Python "
    "para elaborar un reporte de indicadores."
)
_EJEMPLO_CITA_PAQUETE = "Analiza datos de ventas con Python"
_EJEMPLO_TEXTO_SEGURIDAD = (
    "[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]\n"
    "Ejemplo sintético CIAR: Semana 4. Configura reglas de firewall en pfSense "
    "y contrasta el tráfico bloqueado, fomentando el trabajo en equipo."
)
_EJEMPLO_CITA_SEGURIDAD = "Configura reglas de firewall en pfSense"
_EJEMPLO_TEXTO_SIN_HERRAMIENTA = (
    "[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]\n"
    "Ejemplo sintético CIAR: Semana 6. Estima costos del proyecto a partir del "
    "alcance acordado con el cliente."
)
_EJEMPLO_CITA_SIN_HERRAMIENTA = "Estima costos del proyecto a partir del alcance acordado"


def _cita_ejemplo(texto: str, fragmento: str) -> dict[str, object]:
    """Derive example offsets from the text so they never drift when it is edited."""

    inicio = texto.index(fragmento)
    return {"texto": fragmento, "start_pos": inicio, "end_pos": inicio + len(fragmento)}


def _ejemplo_catalogo() -> tuple[str, EjemploExtraccionCIAR]:
    """Synthetic few-shot: a detected candidate linked through `herramientas_catalogo`."""

    linea = (
        "Ejemplo sintético CIAR: Semana 3. Programa una interfaz de consola con "
        "Java para registrar pedidos."
    )
    texto = "[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]\n" + linea
    inicio = texto.index("Java")
    candidata = {
        "id": "HERR_EJEMPLO_0001",
        "nombre": "Java",
        "evidencia_literal": "Java",
        "seccion_fuente": "silabo_completo",
        "contexto_fuente": linea,
        "start_pos": inicio,
        "end_pos": inicio + len("Java"),
    }
    texto += "\n\n[DETECTED CATALOG TOOL CANDIDATES]\n" + json.dumps(
        [candidata], ensure_ascii=False, sort_keys=True
    )
    extraccion = EjemploExtraccionCIAR(
        extraction_class="paquete_respaldado",
        extraction_text="Programa una interfaz de consola con Java",
        attributes={
            "habilidad_propuesta": "Programar una interfaz de consola",
            "competencia_propuesta": "Desarrollo de software",
            "herramientas_catalogo": [
                {
                    "id_catalogo": "HERR_EJEMPLO_0001",
                    "start_pos": inicio,
                    "end_pos": inicio + len("Java"),
                    "evidencia_uso": "con Java",
                }
            ],
            "contexto_relacion": (
                "Programar una interfaz de consola con Java permite registrar "
                "pedidos; Java queda vinculado como herramienta de catálogo."
            ),
        },
    )
    return texto, extraccion


def _herramienta_ejemplo(
    nombre: str, tipo_ontologia: str, texto: str, cita: str, evidencia_uso: str
) -> dict[str, object]:
    return {
        "nombre": nombre,
        "tipo_ontologia": tipo_ontologia,
        "seccion_fuente": "programa_semanal",
        "cita_fuente": _cita_ejemplo(texto, cita),
        "evidencia_uso": evidencia_uso,
    }


def construir_ejemplos_langextract() -> tuple[object, ...]:
    """Return synthetic C-H-H examples, never evidence from CIAR documents."""

    texto_catalogo, extraccion_catalogo = _ejemplo_catalogo()
    ejemplos = (
        EjemploLangExtractCIAR(
            text=_EJEMPLO_TEXTO_PAQUETE,
            extractions=(
                EjemploExtraccionCIAR(
                    extraction_class="paquete_respaldado",
                    extraction_text=_EJEMPLO_CITA_PAQUETE,
                    attributes={
                        "habilidad_propuesta": "Analizar datos de ventas",
                        "competencia_propuesta": "Análisis de datos",
                        "herramientas": [
                            _herramienta_ejemplo(
                                "Python",
                                "lenguaje",
                                _EJEMPLO_TEXTO_PAQUETE,
                                _EJEMPLO_CITA_PAQUETE,
                                "con Python",
                            ),
                        ],
                        "contexto_relacion": (
                            "La habilidad analiza datos de ventas con Python para "
                            "elaborar un reporte de indicadores."
                        ),
                    },
                ),
            ),
        ),
        EjemploLangExtractCIAR(
            text=_EJEMPLO_TEXTO_SEGURIDAD,
            extractions=(
                EjemploExtraccionCIAR(
                    extraction_class="paquete_respaldado",
                    extraction_text=_EJEMPLO_CITA_SEGURIDAD,
                    attributes={
                        "habilidad_propuesta": "Configurar reglas de firewall",
                        "competencia_propuesta": "Ciberseguridad",
                        "herramientas": [
                            _herramienta_ejemplo(
                                "pfSense",
                                "software",
                                _EJEMPLO_TEXTO_SEGURIDAD,
                                _EJEMPLO_CITA_SEGURIDAD,
                                "en pfSense",
                            ),
                        ],
                        "contexto_relacion": (
                            "La competencia de dominio se deriva del clúster técnico "
                            "semanal; el trabajo en equipo queda solo como contexto "
                            "transversal declarado."
                        ),
                    },
                ),
            ),
        ),
        EjemploLangExtractCIAR(
            text=_EJEMPLO_TEXTO_SIN_HERRAMIENTA,
            extractions=(
                EjemploExtraccionCIAR(
                    extraction_class="paquete_respaldado",
                    extraction_text=_EJEMPLO_CITA_SIN_HERRAMIENTA,
                    attributes={
                        "habilidad_propuesta": "Estimar costos del proyecto",
                        "competencia_propuesta": "Gestión de proyectos",
                        "contexto_relacion": (
                            "La actividad no cita ninguna herramienta concreta, así "
                            "que el paquete queda sin herramientas."
                        ),
                    },
                ),
            ),
        ),
        EjemploLangExtractCIAR(
            text=texto_catalogo,
            extractions=(extraccion_catalogo,),
        ),
        EjemploLangExtractCIAR(
            text="Ejemplo sintético CIAR: Semana 8. Se elabora un diagrama de clases.",
            extractions=(
                EjemploExtraccionCIAR(
                    extraction_class="pendiente",
                    extraction_text="diagrama de clases",
                    attributes={
                        "motivo": (
                            "El nombre describe una categoría de artefacto, no un "
                            "producto concreto."
                        )
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
    resultado: object,
    *,
    profile: str = "strict",
    catalog_tool_candidates: tuple[Mapping[str, object], ...] = (),
    source_text: str | None = None,
    source_evidence_map: tuple[SourceEvidenceSpan, ...] = (),
) -> ResultadoExtraccionCIAR:
    """Map LangExtract-like results into accepted CIAR proposals and pending rows."""

    if profile not in {"strict", "baseline", "benchmark"}:
        raise ValueError(f"Unknown LangExtract profile: {profile}")

    texto_fuente = _texto(_campo(resultado, "text"))
    extracciones = _campo(resultado, "extractions", ())
    paquetes: list[PaqueteRespaldadoCIAR] = []
    pendientes: list[PendienteCIAR] = []

    for extraccion in _iterable(extracciones):
        clase = _texto(_campo(extraccion, "extraction_class")).casefold()
        if clase in {"paquete_respaldado", "paquete"}:
            paquete, pendientes_paquete = _adaptar_paquete(
                texto_fuente,
                extraccion,
                profile=profile,
                catalog_tool_candidates=catalog_tool_candidates,
                source_text=source_text,
                source_evidence_map=source_evidence_map,
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
    texto_fuente: str,
    extraccion: object,
    *,
    profile: str,
    catalog_tool_candidates: tuple[Mapping[str, object], ...],
    source_text: str | None,
    source_evidence_map: tuple[SourceEvidenceSpan, ...],
) -> tuple[PaqueteRespaldadoCIAR | None, tuple[PendienteCIAR, ...]]:
    atributos = _mapping(_campo(extraccion, "attributes", {}))
    habilidad = _texto(atributos.get("habilidad_propuesta"))
    principal, error, diagnostico = _cita_principal(texto_fuente, extraccion, atributos)
    if error is not None:
        return None, (_pendiente(error, extraccion, atributos, diagnostico),)
    if principal is None:
        return None, (_pendiente("CITA_PRINCIPAL_SIN_INTERVALO", extraccion, atributos),)
    if source_evidence_map:
        if source_text is None:
            return None, (_pendiente("CITA_PRINCIPAL_SIN_FUENTE", extraccion, atributos),)
        principal_fuente = _mapear_cita_a_fuente(principal, source_text, source_evidence_map)
        if principal_fuente is None:
            return None, (_pendiente("CITA_PRINCIPAL_NO_LITERAL_EN_FUENTE", extraccion, atributos),)
        principal = principal_fuente

    complementaria, error, _ = _cita_complementaria(texto_fuente, atributos)
    if error is not None:
        return None, (_pendiente(error, extraccion, atributos),)
    if complementaria is not None and source_evidence_map and source_text is not None:
        complementaria = _mapear_cita_a_fuente(
            complementaria, source_text, source_evidence_map
        )
        if complementaria is None:
            return None, (_pendiente("CITA_COMPLEMENTARIA_NO_LITERAL_EN_FUENTE", extraccion, atributos),)

    if profile in {"baseline", "benchmark"}:
        herramientas = _herramientas_baseline(atributos.get("herramientas"))
        herramientas_catalogo: tuple[dict[str, object], ...] = ()
        herramientas_propuestas: tuple[dict[str, object], ...] = ()
        pendientes_herramientas: tuple[PendienteCIAR, ...] = ()
        if catalog_tool_candidates:
            # With detected candidates the raw profile still admits tools through
            # the same literal-evidence contract: catalog tools must be linked by
            # candidate id, and uncatalogued tools stay HITL proposals.
            competencia_declarada = _texto(atributos.get("competencia_propuesta"))
            contexto_declarado = _texto(atributos.get("contexto_relacion"))
            declaradas = atributos.get("herramientas_propuestas") or atributos.get(
                "herramientas"
            )
            herramientas, herramientas_propuestas, pendientes_herramientas = (
                _herramientas_admitidas(
                    texto_fuente,
                    declaradas,
                    habilidad,
                    principal,
                    competencia_declarada,
                    catalog_tool_candidates,
                    extraccion,
                    atributos,
                )
            )
            herramientas_catalogo, pendientes_catalogo = _herramientas_catalogo_admitidas(
                atributos.get("herramientas_catalogo"),
                catalog_tool_candidates,
                source_text or texto_fuente,
                habilidad,
                competencia_declarada,
                contexto_declarado,
                extraccion,
                atributos,
            )
            pendientes_herramientas += pendientes_catalogo
        return (
            PaqueteRespaldadoCIAR(
                habilidad_propuesta=habilidad,
                competencia_propuesta=_texto(atributos.get("competencia_propuesta")) or None,
                herramientas=herramientas,
                evidencia_principal=principal,
                evidencia_complementaria=complementaria,
                contexto_relacion=_texto(atributos.get("contexto_relacion")) or None,
                herramientas_catalogo=herramientas_catalogo,
                herramientas_propuestas=herramientas_propuestas,
            ),
            tuple(pendientes_herramientas),
        )

    herramientas_declaradas = atributos.get(
        "herramientas_propuestas", atributos.get("herramientas")
    )
    if not habilidad:
        codigo = (
            "HERRAMIENTA_SIN_HABILIDAD"
            if _iterable(herramientas_declaradas)
            or _iterable(atributos.get("herramientas_catalogo"))
            else "HABILIDAD_SIN_RESPALDO"
        )
        return None, (_pendiente(codigo, extraccion, atributos),)
    if not _habilidad_accion_objeto(habilidad):
        return None, (_pendiente("HABILIDAD_SIN_ACCION_Y_OBJETO", extraccion, atributos),)

    herramientas, herramientas_propuestas, pendientes_herramienta = _herramientas_admitidas(
        texto_fuente,
        herramientas_declaradas,
        habilidad,
        principal,
        _texto(atributos.get("competencia_propuesta")),
        catalog_tool_candidates,
        extraccion,
        atributos,
    )
    herramientas_catalogo, pendientes_catalogo = _herramientas_catalogo_admitidas(
        atributos.get("herramientas_catalogo"),
        catalog_tool_candidates,
        source_text or texto_fuente,
        habilidad,
        _texto(atributos.get("competencia_propuesta")),
        _texto(atributos.get("contexto_relacion")),
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
            herramientas_catalogo=herramientas_catalogo,
            herramientas_propuestas=herramientas_propuestas,
        ),
        pendientes_herramienta + pendientes_catalogo,
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


def _mapear_cita_a_fuente(
    cita: CitaLiteralCIAR,
    source_text: str,
    source_evidence_map: tuple[SourceEvidenceSpan, ...],
) -> CitaLiteralCIAR | None:
    """Translate compact-payload offsets without weakening literal validation."""

    for span in source_evidence_map:
        if not (span.payload_start <= cita.start_pos and cita.end_pos <= span.payload_end):
            continue
        start = span.source_start + (cita.start_pos - span.payload_start)
        end = start + len(cita.texto)
        if source_text[start:end] == cita.texto:
            return CitaLiteralCIAR(texto=cita.texto, start_pos=start, end_pos=end)

    occurrences: list[int] = []
    cursor = source_text.find(cita.texto)
    while cursor >= 0:
        occurrences.append(cursor)
        cursor = source_text.find(cita.texto, cursor + 1)
    if len(occurrences) == 1:
        start = occurrences[0]
        return CitaLiteralCIAR(texto=cita.texto, start_pos=start, end_pos=start + len(cita.texto))
    return None


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
    competencia: str,
    candidatas_catalogo: tuple[Mapping[str, object], ...],
    extraccion: object,
    atributos: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[dict[str, object], ...], tuple[PendienteCIAR, ...]]:
    aceptadas: list[str] = []
    propuestas: list[dict[str, object]] = []
    pendientes: list[PendienteCIAR] = []
    for candidata in _iterable(valor):
        herramienta = _mapping(candidata)
        nombre = _texto(herramienta.get("nombre"))
        codigo = _rechazo_herramienta(
            texto_fuente, herramienta, habilidad, evidencia_principal
        )
        cita, _, _ = _validar_cita(
            texto_fuente, _mapping(herramienta.get("cita_fuente")), "HERRAMIENTA"
        )
        if codigo is None and not competencia:
            codigo = "HERRAMIENTA_NUEVA_SIN_COMPETENCIA"
        if codigo is None and (cita is None or nombre not in cita.texto):
            codigo = "HERRAMIENTA_CITA_NO_LITERAL"
        if codigo is None and _herramienta_esta_en_catalogo(nombre, candidatas_catalogo):
            codigo = "HERRAMIENTA_CATALOGO_DEBE_VINCULARSE"
        if codigo is not None:
            atributos_pendiente = dict(atributos)
            atributos_pendiente["evidencia_principal"] = nombre
            pendientes.append(
                _pendiente(codigo, extraccion, atributos_pendiente)
            )
            continue
        aceptadas.append(nombre)
        assert cita is not None
        propuestas.append(
            {
                "nombre": nombre,
                "tipo_ontologia": _tipo_ontologia_herramienta(
                    herramienta.get("tipo_ontologia")
                ),
                "estado": "PROPUESTA_HITL",
                "requiere_aprobacion_humana": True,
                "seccion_fuente": _texto(herramienta.get("seccion_fuente")),
                "evidencia_literal": cita.texto,
                "start_pos": cita.start_pos,
                "end_pos": cita.end_pos,
                "evidencia_uso": _texto(herramienta.get("evidencia_uso")),
            }
        )
    ordenadas = sorted(
        {
            (propuesta["nombre"], propuesta["start_pos"], propuesta["end_pos"]): propuesta
            for propuesta in propuestas
        }.values(),
        key=lambda propuesta: (
            int(propuesta["start_pos"]),
            int(propuesta["end_pos"]),
            str(propuesta["nombre"]),
        ),
    )
    return tuple(dict.fromkeys(aceptadas)), tuple(ordenadas), tuple(pendientes)


def _herramientas_catalogo_admitidas(
    valor: object,
    candidatas: tuple[Mapping[str, object], ...],
    texto_fuente: str,
    habilidad: str,
    competencia: str,
    contexto_relacion: str,
    extraccion: object,
    atributos: Mapping[str, object],
) -> tuple[tuple[dict[str, object], ...], tuple[PendienteCIAR, ...]]:
    candidatas_por_ubicacion = {
        (
            _texto(candidata.get("id")),
            candidata.get("start_pos"),
            candidata.get("end_pos"),
        ): candidata
        for candidata in candidatas
    }
    aceptadas: list[dict[str, object]] = []
    pendientes: list[PendienteCIAR] = []
    for asignacion in _iterable(valor):
        declarada = _mapping(asignacion)
        clave = (
            _texto(declarada.get("id_catalogo")),
            declarada.get("start_pos"),
            declarada.get("end_pos"),
        )
        candidata = candidatas_por_ubicacion.get(clave)
        codigo = _rechazo_herramienta_catalogo(
            candidata, texto_fuente, habilidad, competencia, contexto_relacion, declarada
        )
        if codigo is not None:
            atributos_pendiente = dict(atributos)
            atributos_pendiente["evidencia_principal"] = _texto(
                declarada.get("id_catalogo")
            )
            pendientes.append(_pendiente(codigo, extraccion, atributos_pendiente))
            continue
        assert candidata is not None
        inicio = candidata["start_pos"]
        fin = candidata["end_pos"]
        assert isinstance(inicio, int)
        assert isinstance(fin, int)
        aceptadas.append(
            {
                "id": candidata["id"],
                "nombre": candidata["nombre"],
                "evidencia_literal": candidata["evidencia_literal"],
                "seccion_fuente": candidata["seccion_fuente"],
                "start_pos": inicio,
                "end_pos": fin,
            }
        )
    ordenadas = sorted(
        {(
            herramienta["id"],
            herramienta["start_pos"],
            herramienta["end_pos"],
        ): herramienta for herramienta in aceptadas}.values(),
        key=lambda herramienta: (
            int(herramienta["start_pos"]),
            int(herramienta["end_pos"]),
            str(herramienta["id"]),
        ),
    )
    return tuple(ordenadas), tuple(pendientes)


def _rechazo_herramienta_catalogo(
    candidata: Mapping[str, object] | None,
    texto_fuente: str,
    habilidad: str,
    competencia: str,
    contexto_relacion: str,
    declarada: Mapping[str, object],
) -> str | None:
    if candidata is None:
        return "HERRAMIENTA_CATALOGO_NO_DETECTADA"
    inicio = candidata.get("start_pos")
    fin = candidata.get("end_pos")
    evidencia = _texto(candidata.get("evidencia_literal"))
    if not _intervalo_valido(inicio, fin, len(texto_fuente)):
        return "HERRAMIENTA_CATALOGO_CITA_NO_LITERAL"
    assert isinstance(inicio, int)
    assert isinstance(fin, int)
    if not evidencia or texto_fuente[inicio:fin] != evidencia:
        return "HERRAMIENTA_CATALOGO_CITA_NO_LITERAL"
    evidencia_uso = _texto(declarada.get("evidencia_uso"))
    contexto_fuente = _texto(candidata.get("contexto_fuente"))
    if not evidencia_uso or not _fragmento_contiene(contexto_fuente, evidencia_uso):
        return "HERRAMIENTA_CATALOGO_USO_SIN_RESPALDO"
    nombre = _texto(candidata.get("nombre"))
    if (
        not habilidad
        or not competencia
        or not contexto_relacion
        or nombre.casefold() not in contexto_relacion.casefold()
    ):
        return "HERRAMIENTA_CATALOGO_RELACION_SIN_RESPALDO"
    return None


def _fragmento_contiene(contenedor: str, fragmento: str) -> bool:
    """Containment tolerant to casing and whitespace only, never to rewording."""

    def normalizar(valor: str) -> str:
        return " ".join(valor.split()).casefold()

    return normalizar(fragmento) in normalizar(contenedor)


def _herramienta_esta_en_catalogo(
    nombre: str, candidatas_catalogo: tuple[Mapping[str, object], ...]
) -> bool:
    nombre_normalizado = nombre.casefold()
    return any(
        nombre_normalizado
        in {
            _texto(candidata.get("nombre")).casefold(),
            _texto(candidata.get("evidencia_literal")).casefold(),
        }
        for candidata in candidatas_catalogo
    )


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
    tipo = _tipo_ontologia_herramienta(herramienta.get("tipo_ontologia"))
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
    if not evidencia_uso or not _fragmento_contiene(cita.texto, evidencia_uso):
        return "HERRAMIENTA_USO_SIN_RESPALDO"
    if not _intervalos_se_solapan(cita, evidencia_principal):
        return "HERRAMIENTA_USO_SIN_RESPALDO"
    if not habilidad:
        return "HERRAMIENTA_SIN_HABILIDAD"
    return None


def _tipo_ontologia_herramienta(valor: object) -> str:
    tipo = _texto(valor)
    return _ALIASES_TIPO_HERRAMIENTA.get(tipo.casefold(), tipo)


def _habilidad_accion_objeto(habilidad: str) -> bool:
    palabras = habilidad.split()
    return len(palabras) >= 2 and palabras[0].casefold().endswith(("ar", "er", "ir"))


def _nombre_herramienta_generico(nombre: str) -> bool:
    normalizado = nombre.casefold()
    if normalizado in _NOMBRES_HERRAMIENTA_GENERICOS:
        return True
    palabras = normalizado.split()
    return bool(palabras) and palabras[0] in _CABEZAS_HERRAMIENTA_GENERICAS


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
