"""Internal lexical and catalog resolution for curricular normalization."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH, clave_concepto
from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos.analista_llm import DecisionCurricular
from agente.normalizador.silabos.herramientas import (
    clave_herramienta_canonica,
    coincide_nombre_herramienta_en_texto,
    herramienta_nueva_evidenciada,
    nombre_herramienta_canonico,
)
from agente.normalizador.silabos.trazabilidad_curricular import (  # noqa: F401
    _ALIASES_CARRERA,
    _CARRERAS_POR_NOMBRE,
    ESTADO_PENDIENTE_CATALOGACION,
    ESTADO_PENDIENTE_PERFIL,
    ESTADO_REVISION_HUMANA,
    _archivo_origen,
    _clave_carrera,
    _error,
    _estado_resolucion_determinista,
    _fila_cobertura,
    _filas_curso,
    _hash_id,
    _id_carrera,
    _modalidad_curso,
    _pendientes_por_relacion_fuente,
    _propuesta_dict,
    _registrar_pendiente,
    _source_ref,
    _texto,
    _warning,
)


@dataclass(frozen=True, slots=True)
class ResolucionConcepto:
    """Auditable result of a canonical or textual resolution."""

    concepto: ConceptoCHH | None
    metodo: str
    puntaje: float | None = None
    puntaje_segundo: float | None = None


@dataclass(frozen=True, slots=True)
class HerramientaDetectada:
    """Tool found in a trusted curricular section."""

    concepto: ConceptoCHH
    seccion: str
    texto_evidencia: str
    coincidencia: str


@dataclass(frozen=True, slots=True)
class NormalizacionCurricular:
    """In-memory tables, evidence, and review state without I/O."""

    filas_por_archivo: dict[str, list[dict[str, str]]]
    competencias_fuente: dict[str, dict[str, object]]
    habilidades_fuente: dict[str, dict[str, object]]
    herramientas_fuente: dict[str, dict[str, object]]
    cobertura_fuente_lineage: dict[tuple[str, str, str, str, str], dict[str, str]]
    cobertura_canonica_lineage: dict[tuple[str, str, str, str, str], dict[str, str]]
    pendientes_curriculares: list[dict[str, object]]
    hallazgos: tuple[Hallazgo, ...]
    cuarentena: tuple[dict[str, object], ...]


_PALABRAS_NO_EVIDENCIA = {
    "a",
    "al",
    "ante",
    "bajo",
    "como",
    "con",
    "contra",
    "cual",
    "cuales",
    "de",
    "del",
    "desde",
    "donde",
    "durante",
    "el",
    "ella",
    "ellas",
    "ellos",
    "en",
    "entre",
    "es",
    "esta",
    "este",
    "estos",
    "la",
    "las",
    "lo",
    "los",
    "mediante",
    "para",
    "por",
    "que",
    "se",
    "segun",
    "sin",
    "sobre",
    "su",
    "sus",
    "un",
    "una",
    "unas",
    "uno",
    "unos",
    "y",
    "analiza",
    "analizar",
    "aplica",
    "aplicar",
    "argumenta",
    "argumentar",
    "conoce",
    "conocer",
    "construye",
    "construir",
    "crea",
    "crear",
    "describe",
    "describir",
    "determina",
    "determinar",
    "desarrolla",
    "desarrollar",
    "diseña",
    "diseñar",
    "elabora",
    "elaborar",
    "evalua",
    "evaluar",
    "examina",
    "examinar",
    "explica",
    "explicar",
    "fundamenta",
    "fundamentar",
    "genera",
    "generar",
    "identifica",
    "identificar",
    "interpreta",
    "interpretar",
    "organiza",
    "organizar",
    "plantea",
    "plantear",
    "propone",
    "proponer",
    "reconoce",
    "reconocer",
    "realiza",
    "realizar",
    "selecciona",
    "seleccionar",
    "utiliza",
    "utilizar",
}

TCompetencia = TypeVar("TCompetencia", ConceptoCHH, dict[str, str])


def _catalogo_curricular(
    registros: list[dict[str, object]],
    catalogo_base: CatalogoCHH,
    catalogo_carrera: CatalogoCHH | None,
) -> CatalogoCHH:
    """Build the competency scope for one normalization run."""

    declaraciones_fuente = _declaraciones_de_registros(registros)
    if catalogo_carrera is not None:
        catalogo_por_capas = catalogo_base.con_carrera(
            catalogo_carrera, origen="perfil_carrera", version="carrera"
        )
        competencias: list[ConceptoCHH] = list(catalogo_carrera.competencias)
        for declaracion in declaraciones_fuente:
            concepto = _concepto_declarado(declaracion, catalogo_carrera, catalogo_base)
            if not any(
                clave_concepto(item.nombre) == clave_concepto(concepto.nombre)
                for item in competencias
            ):
                competencias.append(concepto)
        return catalogo_por_capas.con_competencias(
            tuple(competencias), origen="perfil_carrera", version="carrera"
        )

    competencias = [
        _concepto_declarado(declaracion, None, catalogo_base)
        for declaracion in declaraciones_fuente
    ]
    return catalogo_base.con_competencias(
        tuple(competencias), origen="perfil_silabos", version="declaraciones"
    )


def _declaraciones_de_registros(registros: list[dict[str, object]]) -> list[dict[str, str]]:
    resultado: list[dict[str, str]] = []
    vistos: set[str] = set()
    for registro in registros:
        datos_objeto = registro.get("datos")
        datos = datos_objeto if isinstance(datos_objeto, dict) else {}
        for declaracion in _declaraciones(datos):
            clave = clave_concepto(declaracion["nombre"])
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            resultado.append(declaracion)
    return resultado


def _concepto_declarado(
    declaracion: dict[str, str], catalogo_carrera: CatalogoCHH | None, catalogo_base: CatalogoCHH
) -> ConceptoCHH:
    nombre = declaracion["nombre"]
    for catalogo in (catalogo_carrera, catalogo_base):
        if catalogo is None:
            continue
        existente = catalogo.obtener("competencia", nombre)
        if existente is not None:
            return existente
    tipo = declaracion.get("tipo") or "dura"
    return ConceptoCHH(
        id=_hash_id("COMP", nombre),
        nombre=nombre,
        descripcion=declaracion.get("descripcion", "") or f"Capacidad para {nombre.lower()}.",
        tipo=tipo,
    )


def _declaraciones(datos: dict[str, object]) -> list[dict[str, str]]:
    valor = datos.get("competencias_declaradas")
    if not isinstance(valor, list):
        return []
    resultado: list[dict[str, str]] = []
    for indice, item in enumerate(valor, start=1):
        if not isinstance(item, dict):
            continue
        nombre = _texto(item.get("nombre"))
        if nombre and clave_concepto(nombre) != "nombre":
            resultado.append(
                {
                    "orden": _texto(item.get("orden")) or str(indice),
                    "nombre": nombre,
                    "descripcion": _texto(item.get("descripcion")),
                    "codigo": _texto(item.get("codigo")),
                }
            )
    return resultado


def _id_competencia_fuente(id_silabo: str, declaracion: dict[str, str]) -> str:
    return _hash_id(
        "COMP_SRC",
        id_silabo,
        declaracion.get("orden") or clave_concepto(declaracion["nombre"]),
        declaracion["nombre"],
        declaracion["descripcion"],
    )


def _logros(datos: dict[str, object]) -> list[dict[str, object]]:
    valor = datos.get("logros_especificos")
    return [item for item in valor if isinstance(item, dict)] if isinstance(valor, list) else []


def _competencias_para_logro(
    logro: dict[str, object],
    declaraciones: list[dict[str, str]],
    datos: dict[str, object],
    descripcion: str,
    catalogo: CatalogoCHH,
) -> list[dict[str, str]]:
    """Resolve outcome-to-competency links only from textual source evidence."""

    textuales_declaradas = _competencias_declaradas_por_texto(declaraciones, datos, descripcion)
    if textuales_declaradas:
        return textuales_declaradas
    if not declaraciones:
        return _competencias_por_texto(catalogo, datos, descripcion)
    return []


def _competencias_por_texto(
    catalogo: CatalogoCHH, datos: dict[str, object], descripcion: str
) -> list[dict[str, str]]:
    """Find one canonical competency from curricular evidence."""

    evidencia_logro = _tokens_evidencia(descripcion)
    contexto = _contexto_curricular(datos, descripcion)
    evidencia_contexto = _tokens_evidencia(contexto)
    puntuadas: list[tuple[int, ConceptoCHH]] = []
    for candidato in catalogo.competencias:
        tokens_nombre = _tokens_evidencia(candidato.nombre)
        tokens_descripcion = _tokens_evidencia(candidato.descripcion)
        coincidencias_directas = _coincidencias(evidencia_logro, tokens_nombre)
        coincidencias_descripcion = _coincidencias(evidencia_logro, tokens_descripcion)
        if not coincidencias_directas and not coincidencias_descripcion:
            continue
        puntaje = (
            8 * len(coincidencias_directas)
            + 2 * len(coincidencias_descripcion)
            + 3 * len(_coincidencias(evidencia_contexto, tokens_nombre))
            + len(_coincidencias(evidencia_contexto, tokens_descripcion))
        )
        nombre_clave = clave_concepto(candidato.nombre)
        if nombre_clave and nombre_clave in clave_concepto(contexto):
            puntaje += 20
        if puntaje:
            puntuadas.append((puntaje, candidato))
    seleccion = _seleccionar_competencia_por_puntaje(puntuadas, lambda candidato: candidato.nombre)
    if seleccion is None:
        return []
    mejor_puntaje, segundo_puntaje, mejor = seleccion
    declaracion = _declaracion_desde_catalogo(mejor)
    declaracion["_metodo_resolucion"] = "COINCIDENCIA_TEXTUAL_CATALOGO"
    declaracion["_puntaje_resolucion"] = str(mejor_puntaje)
    declaracion["_puntaje_segundo"] = str(segundo_puntaje) if segundo_puntaje else ""
    return [declaracion]


def _competencias_declaradas_por_texto(
    declaraciones: list[dict[str, str]], datos: dict[str, object], descripcion: str
) -> list[dict[str, str]]:
    evidencia_logro = _tokens_evidencia(descripcion)
    evidencia_contexto = _tokens_evidencia(_contexto_curricular(datos, descripcion))
    puntuadas: list[tuple[int, dict[str, str]]] = []
    for declaracion in declaraciones:
        tokens_nombre = _tokens_evidencia(declaracion["nombre"])
        tokens_descripcion = _tokens_evidencia(declaracion["descripcion"])
        coincidencias_directas = _coincidencias(evidencia_logro, tokens_nombre)
        coincidencias_descripcion = _coincidencias(evidencia_logro, tokens_descripcion)
        if not coincidencias_directas and not coincidencias_descripcion:
            continue
        puntaje = (
            8 * len(coincidencias_directas)
            + 2 * len(coincidencias_descripcion)
            + 3 * len(_coincidencias(evidencia_contexto, tokens_nombre))
            + len(_coincidencias(evidencia_contexto, tokens_descripcion))
        )
        if puntaje:
            puntuadas.append((puntaje, declaracion))
    seleccion = _seleccionar_competencia_por_puntaje(
        puntuadas, lambda candidata: candidata["nombre"]
    )
    if seleccion is None:
        return []
    mejor_puntaje, segundo_puntaje, mejor = seleccion
    resultado = dict(mejor)
    resultado["_metodo_resolucion"] = "COINCIDENCIA_TEXTUAL_DECLARADA"
    resultado["_puntaje_resolucion"] = str(mejor_puntaje)
    resultado["_puntaje_segundo"] = str(segundo_puntaje) if segundo_puntaje else ""
    return [resultado]


def _seleccionar_competencia_por_puntaje(
    puntuadas: list[tuple[int, TCompetencia]], nombre: Callable[[TCompetencia], str]
) -> tuple[int, int, TCompetencia] | None:
    """Accept textual fallback only with sufficient separated evidence."""

    if not puntuadas:
        return None
    puntuadas.sort(key=lambda par: (-par[0], clave_concepto(nombre(par[1]))))
    mejor_puntaje, mejor = puntuadas[0]
    segundo_puntaje = puntuadas[1][0] if len(puntuadas) > 1 else 0
    if mejor_puntaje < 8 or (len(puntuadas) > 1 and mejor_puntaje - segundo_puntaje < 3):
        return None
    return mejor_puntaje, segundo_puntaje, mejor


def _contexto_curricular(datos: dict[str, object], descripcion: str) -> str:
    partes = [
        descripcion,
        _texto(datos.get("curso")),
        _texto(datos.get("sumilla")),
        _texto(datos.get("logro_general")),
        _texto(datos.get("texto_relevante")),
    ]
    programa = datos.get("programa_analitico")
    if isinstance(programa, list):
        partes.extend(_texto(item) for item in programa)
    return " ".join(parte for parte in partes if parte)


def _tokens_evidencia(texto: str) -> set[str]:
    tokens = {
        token
        for token in clave_concepto(texto).split()
        if len(token) >= 4 and token not in _PALABRAS_NO_EVIDENCIA
    }
    return tokens | {token[:6] for token in tokens if len(token) >= 6}


def _coincidencias(origen: set[str], destino: set[str]) -> set[str]:
    return {token for token in origen if token in destino}


def _declaracion_desde_catalogo(candidato: ConceptoCHH) -> dict[str, str]:
    return {
        "orden": "catalogo",
        "nombre": candidato.nombre,
        "descripcion": candidato.descripcion,
        "tipo": candidato.tipo,
    }


def _resolver_competencia(catalogo: CatalogoCHH, declaracion: dict[str, str]) -> ResolucionConcepto:
    nombre = declaracion["nombre"]
    existente = catalogo.obtener("competencia", nombre)
    tipo = declaracion.get("tipo") or "dura"
    descripcion = declaracion["descripcion"] or f"Capacidad para {nombre.lower()}."
    if existente is not None:
        return ResolucionConcepto(
            ConceptoCHH(existente.id, nombre, descripcion, tipo or existente.tipo),
            "NOMBRE_EXACTO",
            1.0,
        )
    return ResolucionConcepto(
        ConceptoCHH(_hash_id("COMP", nombre), nombre, descripcion, tipo), "DECLARACION_SILABO", 1.0
    )


def _resolver_habilidad_canonica(catalogo: CatalogoCHH, descripcion: str) -> ResolucionConcepto:
    """Resolve skills by name or description with threshold and margin."""

    nombre_fuente = _nombre_habilidad(descripcion)
    exacto = catalogo.obtener("habilidad", nombre_fuente)
    if exacto is not None:
        return ResolucionConcepto(exacto, "NOMBRE_EXACTO", 1.0)
    evidencia = _tokens_evidencia(descripcion)
    candidatos: list[tuple[float, str, ConceptoCHH]] = []
    for candidato in catalogo.habilidades:
        tokens_nombre = _tokens_evidencia(candidato.nombre)
        tokens_descripcion = _tokens_evidencia(candidato.descripcion)
        if len(tokens_nombre | tokens_descripcion) < 2:
            continue
        cobertura_nombre = (
            len(evidencia & tokens_nombre) / len(tokens_nombre) if tokens_nombre else 0.0
        )
        cobertura_descripcion = (
            len(evidencia & tokens_descripcion) / len(tokens_descripcion)
            if tokens_descripcion
            else 0.0
        )
        cobertura = max(cobertura_nombre, cobertura_descripcion)
        if cobertura < 0.75:
            continue
        frase = clave_concepto(candidato.nombre) in clave_concepto(descripcion)
        score = cobertura + (0.35 if frase else 0.0)
        metodo = (
            "COINCIDENCIA_NOMBRE"
            if cobertura_nombre >= cobertura_descripcion
            else "COINCIDENCIA_DESCRIPCION"
        )
        candidatos.append((score, metodo, candidato))
    candidatos.sort(key=lambda item: (-item[0], clave_concepto(item[2].nombre)))
    if not candidatos:
        return ResolucionConcepto(None, "SIN_CANDIDATA")
    mejor_score, metodo, mejor = candidatos[0]
    segundo_score = candidatos[1][0] if len(candidatos) > 1 else 0.0
    if mejor_score < 0.85 or (len(candidatos) > 1 and mejor_score - segundo_score < 0.15):
        return ResolucionConcepto(
            None,
            "AMBIGUA_O_INSUFICIENTE",
            round(mejor_score, 3),
            round(segundo_score, 3) if segundo_score else None,
        )
    return ResolucionConcepto(
        mejor, metodo, round(mejor_score, 3), round(segundo_score, 3) if segundo_score else None
    )


def _herramientas_explicitas(
    catalogo: CatalogoCHH, evidencias: tuple[dict[str, str], ...]
) -> tuple[HerramientaDetectada, ...]:
    """Find tools only in trusted structured sections."""

    encontrados: list[HerramientaDetectada] = []
    vistos: set[str] = set()
    for herramienta in sorted(
        catalogo.herramientas, key=lambda item: len(item.nombre), reverse=True
    ):
        nombre = herramienta.nombre.strip().lower()
        if len(nombre) < 2:
            continue
        variantes = {nombre}
        if nombre.startswith("microsoft "):
            producto = nombre.removeprefix("microsoft ")
            variantes.update({"ms " + producto, producto})
        for evidencia in evidencias:
            texto = evidencia["texto"]
            coincidencia = next(
                (
                    variante
                    for variante in variantes
                    if re.search(rf"(?<![a-z0-9]){re.escape(variante)}(?![a-z0-9])", texto.lower())
                ),
                None,
            )
            if coincidencia is None:
                continue
            clave = "|".join((herramienta.id, evidencia["seccion"], texto, coincidencia))
            if clave not in vistos:
                vistos.add(clave)
                encontrados.append(
                    HerramientaDetectada(herramienta, evidencia["seccion"], texto, coincidencia)
                )
    return tuple(encontrados)


def _evidencias_herramientas(datos: dict[str, object]) -> tuple[dict[str, str], ...]:
    valor = datos.get("herramientas_evidencia")
    if not isinstance(valor, list):
        return ()
    evidencias: list[dict[str, str]] = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        seccion = _texto(item.get("seccion"))
        texto = _texto(item.get("texto"))
        if seccion and texto:
            evidencias.append({"seccion": seccion, "texto": texto})
    return tuple(evidencias)


def _evidencias_herramientas_candidatas(datos: dict[str, object]) -> tuple[dict[str, str], ...]:
    """Return only extracted analytical-program citations for new tools."""

    detalle = datos.get("programa_analitico_detalle")
    if isinstance(detalle, list):
        evidencias = [
            evidencia
            for item in detalle
            if isinstance(item, dict)
            if (evidencia := _evidencia_programa_analitico(_texto(item.get("texto"))))
        ]
        if evidencias:
            return tuple(evidencias)
    programa = datos.get("programa_analitico")
    if not isinstance(programa, list):
        return ()
    return tuple(
        evidencia for item in programa if (evidencia := _evidencia_programa_analitico(_texto(item)))
    )


def _evidencia_programa_analitico(texto: str) -> dict[str, str] | None:
    """Preserve only usable extracted curriculum text as tool evidence."""

    clave = clave_concepto(texto)
    texto_minusculas = texto.lower()
    if (
        not texto
        or "bibliografia" in clave
        or any(url in texto_minusculas for url in ("http://", "https://", "www."))
    ):
        return None
    return {"origen": "programa_analitico", "seccion": "programa_analitico", "texto": texto}


def _nombre_habilidad(descripcion: str) -> str:
    texto = re.sub(r"^L\d+\s*[-:.)]?\s*", "", descripcion.strip(), flags=re.IGNORECASE)
    texto = texto.rstrip(" .;:")
    return texto[:1].upper() + texto[1:] if texto else ""


def _concepto_decidido(
    catalogo: CatalogoCHH, nombre: str, descripcion: str, tipo: str, prefijo: str
) -> ConceptoCHH:
    """Resolve an LLM proposal without allowing model-generated IDs."""

    existente = catalogo.obtener("competencia" if prefijo == "COMP" else "habilidad", nombre)
    if existente is not None:
        return existente
    return ConceptoCHH(
        id=_hash_id(prefijo, nombre),
        nombre=_texto(nombre),
        descripcion=_texto(descripcion) or f"Capacidad curricular para {_texto(nombre).lower()}.",
        tipo=_tipo_competencia(tipo) if prefijo == "COMP" else tipo,
    )


def _tipo_competencia(tipo: str) -> str:
    """Reduce LLM labels to the two values allowed by the CSV contract."""

    clave = clave_concepto(tipo)
    return "blanda" if "blanda" in clave or "soft" in clave else "dura"


def _herramientas_llm_nuevas(
    decision: DecisionCurricular | None,
    datos: dict[str, object],
    detectadas: tuple[HerramientaDetectada, ...],
) -> tuple[tuple[ConceptoCHH, dict[str, str]], ...]:
    """Create new tools only when the syllabus supports them literally."""

    if decision is None:
        return ()
    existentes = {clave_herramienta_canonica(item.concepto.nombre) for item in detectadas}
    resultado: list[tuple[ConceptoCHH, dict[str, str]]] = []
    evidencias = _evidencias_herramientas_candidatas(datos)
    for propuesta in decision.herramientas:
        nombre_canonico = nombre_herramienta_canonico(propuesta.nombre)
        clave_canonica = clave_herramienta_canonica(nombre_canonico)
        if clave_canonica in existentes:
            continue
        caso: dict[str, object] = {"evidencia_herramientas_candidata": list(evidencias)}
        if not herramienta_nueva_evidenciada(nombre_canonico, propuesta.evidencia, caso):
            continue
        evidencia = next(
            (
                item
                for item in evidencias
                if coincide_nombre_herramienta_en_texto(nombre_canonico, item["texto"])
            ),
            None,
        )
        if evidencia is None:
            continue
        concepto = ConceptoCHH(
            id=_hash_id("HERR", nombre_canonico),
            nombre=nombre_canonico,
            descripcion=f"Referenced in the analytical program: {evidencia['texto']}",
            tipo="herramienta",
        )
        resultado.append((concepto, evidencia))
        existentes.add(clave_canonica)
    return tuple(resultado)
