"""Validación determinista de decisiones curriculares recibidas del analista."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.silabos.herramientas import (
    herramienta_nueva_evidenciada,
    nombre_herramienta_coincide,
)
from agente.normalizador.silabos.politica_curricular import (
    MOTIVO_COMPETENCIA_GENERICA,
    es_competencia_generica,
)

if TYPE_CHECKING:
    from agente.normalizador.silabos.analista_llm import DecisionCurricular


_ANCLAS_NO_SEMANTICAS = frozenset(
    {
        "para",
        "desde",
        "sobre",
        "entre",
        "mediante",
        "nivel",
        "forma",
        "proceso",
        "procesos",
        "profesional",
        "profesionales",
        "curricular",
        "curriculares",
    }
)

_VERBOS_HABILIDAD = {
    "analizar",
    "aplicar",
    "argumentar",
    "calcular",
    "comunicar",
    "construir",
    "crear",
    "desarrollar",
    "disenar",
    "elaborar",
    "evaluar",
    "explicar",
    "gestionar",
    "identificar",
    "interpretar",
    "investigar",
    "planificar",
    "proponer",
    "segmentar",
    "seleccionar",
    "utilizar",
    "formular",
    "medir",
    "administrar",
    "coordinar",
    "diagnosticar",
    "ejecutar",
    "generar",
    "optimizar",
    "presentar",
    "reconocer",
    "relacionar",
    "sustentar",
    "definir",
    "comparar",
    "estructurar",
    "implementar",
    "examinar",
    "detectar",
    "distinguir",
    "determinar",
    "diferenciar",
    "modelar",
    "representar",
    "fundamentar",
    "delimitar",
    "caracterizar",
    "articular",
    "procesar",
    "priorizar",
    "conceptualizar",
    "emplear",
    "contrastar",
    "preparar",
    "registrar",
    "vincular",
    "simular",
    "resolver",
    "valorar",
    "ajustar",
    "adaptar",
    "organizar",
    "monitorear",
    "auditar",
    "estimar",
    "predecir",
    "seguir",
    "tabular",
    "criticar",
    "ejemplificar",
    "defender",
    "realizar",
    "configurar",
    "integrar",
    "describir",
    "clasificar",
    "redactar",
    "categorizar",
}
_FORMAS_CONJUGADAS_HABILIDAD = {
    "calcula": "calcular",
    "interpreta": "interpretar",
    "evalua": "evaluar",
    "modela": "modelar",
    "gestiona": "gestionar",
    "clasifica": "clasificar",
    "optimiza": "optimizar",
}
_NOMINALIZACIONES_HABILIDAD = {
    "administracion": "administrar",
    "analisis": "analizar",
    "aplicacion": "aplicar",
    "argumentacion": "argumentar",
    "calculo": "calcular",
    "comunicacion": "comunicar",
    "construccion": "construir",
    "creacion": "crear",
    "desarrollo": "desarrollar",
    "diseno": "disenar",
    "elaboracion": "elaborar",
    "evaluacion": "evaluar",
    "explicacion": "explicar",
    "formulacion": "formular",
    "generacion": "generar",
    "gestion": "gestionar",
    "identificacion": "identificar",
    "interpretacion": "interpretar",
    "investigacion": "investigar",
    "medicion": "medir",
    "optimizacion": "optimizar",
    "planificacion": "planificar",
    "presentacion": "presentar",
    "reconocimiento": "reconocer",
    "segmentacion": "segmentar",
    "seleccion": "seleccionar",
    "sustentacion": "sustentar",
    "utilizacion": "utilizar",
    "fundamentacion": "fundamentar",
    "pronostico": "pronosticar",
    "resolucion": "resolver",
    "anticipacion": "anticipar",
    "descripcion": "describir",
    "preparacion": "preparar",
    "estructuracion": "estructurar",
    "deteccion": "detectar",
    "implementacion": "implementar",
    "monitoreo": "monitorear",
    "prototipado": "prototipar",
    "diagnostico": "diagnosticar",
    "clasificacion": "clasificar",
}
_HABILIDADES_GENERICAS = {
    "comunicar",
    "integrar",
    "aplicar conceptos",
    "usar herramientas",
    "analizar información",
}


def _validar_decision(
    decision: DecisionCurricular,
    caso: dict[str, object],
) -> list[str]:
    errores: list[str] = []
    nombre_habilidad = clave_concepto(decision.habilidad.nombre)
    if nombre_habilidad in _HABILIDADES_GENERICAS:
        errores.append("HABILIDAD_GENERICA")
    tokens = nombre_habilidad.split()
    if len(tokens) < 2 or not any(token in _VERBOS_HABILIDAD for token in tokens[:2]):
        errores.append("HABILIDAD_SIN_VERBO_OBSERVABLE")
    if not clave_concepto(decision.competencia.nombre):
        errores.append("COMPETENCIA_VACIA")
    elif es_competencia_generica(decision.competencia.nombre):
        errores.append(MOTIVO_COMPETENCIA_GENERICA)
    fuente_completa = " ".join(
        str(caso.get(campo) or "")
        for campo in ("curso", "sumilla", "logro_general", "logro", "contenido_relacionado")
    )
    fuente_clave = clave_concepto(fuente_completa)
    if not _competencia_anclada_en_fuente_o_declarada(
        decision.competencia.nombre,
        fuente_clave,
        caso,
    ):
        errores.append("COMPETENCIA_SIN_ANCLA_FUENTE")
    evidencias = evidencia_decision(decision)
    evidencias_en_fuente = [
        evidencia for evidencia in evidencias if _evidencia_en_texto(evidencia, fuente_clave)
    ]
    if not evidencias:
        errores.append("SIN_EVIDENCIA_LLM")
    elif not evidencias_en_fuente:
        errores.append("EVIDENCIA_NO_ENCONTRADA")
    else:
        errores.extend(_errores_grounding_decision(decision, evidencias_en_fuente))
    herramientas_detectadas = caso.get("herramientas_detectadas")
    if not isinstance(herramientas_detectadas, list):
        herramientas_detectadas = []
    disponibles = {clave_concepto(str(nombre)) for nombre in herramientas_detectadas}
    for herramienta in decision.herramientas:
        herramienta_existente = nombre_herramienta_coincide(herramienta.nombre, disponibles)
        herramienta_nueva = herramienta_nueva_evidenciada(
            herramienta.nombre, herramienta.evidencia, caso
        )
        if not herramienta_existente and not herramienta_nueva:
            errores.append(f"HERRAMIENTA_NO_DETECTADA:{herramienta.nombre}")
    return errores


def _errores_grounding_decision(
    decision: DecisionCurricular,
    evidencias: list[str],
) -> list[str]:
    """Verify that one literal syllabus quote anchors the proposed skill.

    A valid quote alone is insufficient: the skill must share at least two
    normalized content anchors with one cited fragment (or all anchors when it
    has fewer than two). A competence may be broader than the skill, but its
    lexical relation can only add diagnostic context; it never substitutes the
    syllabus evidence that anchors the skill.
    """

    habilidad = _anclas_grounding(decision.habilidad.nombre)
    competencia = _anclas_grounding(decision.competencia.nombre)
    minimas_habilidad = min(2, len(habilidad))
    habilidad_anclada = any(
        len(habilidad & _anclas_grounding(evidencia)) >= minimas_habilidad
        for evidencia in evidencias
    )
    errores: list[str] = []
    if not habilidad or not habilidad_anclada:
        errores.append("HABILIDAD_SIN_ANCLA_EVIDENCIA")
        if not competencia or not (competencia & habilidad):
            errores.append("COMPETENCIA_SIN_ANCLA_HABILIDAD")
    return errores


def _anclas_grounding(texto: str) -> set[str]:
    """Reduce texto a raíces conservadoras, evitando conectores y etiquetas vagas."""

    return {
        token[:5]
        for token in clave_concepto(texto).split()
        if len(token) >= 3 and token not in _ANCLAS_NO_SEMANTICAS
    }


def _competencia_anclada_en_fuente_o_declarada(
    competencia: str,
    fuente_normalizada: str,
    caso: dict[str, object],
) -> bool:
    """Require the competence to be source-grounded or explicitly declared."""

    anclas_competencia = _anclas_grounding(competencia)
    if anclas_competencia & _anclas_grounding(fuente_normalizada):
        return True
    declaraciones = caso.get("competencias_declaradas")
    if not isinstance(declaraciones, list):
        return False
    clave_competencia = clave_concepto(competencia)
    if not clave_competencia:
        return False
    for declaracion in declaraciones:
        if isinstance(declaracion, dict):
            nombre = str(declaracion.get("nombre") or "")
        else:
            nombre = str(declaracion or "")
        if clave_concepto(nombre) == clave_competencia:
            return True
    return False


def _reporte_sin_decision_llm(
    caso: dict[str, object],
) -> dict[str, object]:
    """Registra un logro que el analista no representó, sin fabricar una decisión."""

    reporte: dict[str, object] = {
        "tipo": "decision_curricular",
        "estado": "REVISAR_SIN_DECISION_LLM",
        "id_habilidad_fuente": str(caso["id_habilidad_fuente"]),
        "problemas": ["SIN_DECISION_LLM"],
    }
    return reporte


def _reporte_reintento_omitidos(
    clave_lote: str,
    ids_habilidad_fuente: list[str],
    ids_recuperados: list[str],
    detalle: str = "",
) -> dict[str, object]:
    """Registra el único reintento permitido para IDs omitidos en un lote."""

    recuperados = list(dict.fromkeys(ids_recuperados))
    reporte: dict[str, object] = {
        "tipo": "analista_reintento",
        "estado": "COMPLETADO" if not detalle else "ERROR",
        "clave_lote": clave_lote,
        "ids_habilidad_fuente": ids_habilidad_fuente,
        "ids_recuperados": recuperados,
        "ids_sin_decision": [
            id_habilidad for id_habilidad in ids_habilidad_fuente if id_habilidad not in recuperados
        ],
    }
    if detalle:
        reporte["detalle"] = detalle
    return reporte


def _asegurar_cobertura_reportes(
    casos: tuple[dict[str, object], ...],
    reportes: list[dict[str, object]],
) -> None:
    """Evita que un caso fuente termine sin una decisión ni una traza auditable."""

    ids_reportados = {
        str(reporte["id_habilidad_fuente"])
        for reporte in reportes
        if isinstance(reporte.get("id_habilidad_fuente"), str)
        and (
            str(reporte.get("estado", "")) == "ACEPTADA"
            or str(reporte.get("estado", "")).startswith(("REVISAR", "ERROR"))
        )
    }
    for caso in casos:
        if str(caso["id_habilidad_fuente"]) not in ids_reportados:
            reportes.append(_reporte_sin_decision_llm(caso))


def _completar_evidencia(
    decision: DecisionCurricular,
    caso: dict[str, object],
) -> DecisionCurricular:
    """Completa evidencia omitida por el LLM usando el logro ya extraído."""

    if evidencia_decision(decision):
        return decision
    logro = str(caso.get("logro") or "").strip()
    if not logro:
        return decision
    return decision.model_copy(update={"evidencia": [logro]})


def evidencia_decision(decision: DecisionCurricular) -> list[str]:
    """Devuelve las citas declaradas por el analista sin duplicarlas."""

    citas: list[str] = []
    for valor in decision.evidencia:
        texto = str(valor or "").strip()
        if texto and texto not in citas:
            citas.append(texto)
    return citas


def _normalizar_habilidad_nominalizada(
    decision: DecisionCurricular,
) -> DecisionCurricular:
    """Reemplaza solo la primera nominalización explícitamente admitida."""

    nombre = decision.habilidad.nombre
    primera_palabra, separador, resto = nombre.partition(" ")
    infinitivo = _NOMINALIZACIONES_HABILIDAD.get(clave_concepto(primera_palabra))
    if infinitivo is None or not separador or not resto.startswith("de "):
        return decision
    if primera_palabra[:1].isupper():
        infinitivo = infinitivo.capitalize()
    habilidad = decision.habilidad.model_copy(
        update={"nombre": f"{infinitivo} {resto.removeprefix('de ')}"}
    )
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad_forma_conjugada(
    decision: DecisionCurricular,
) -> DecisionCurricular:
    """Convierte únicamente formas conjugadas incluidas en el mapa cerrado."""

    nombre = decision.habilidad.nombre
    primera_palabra, separador, resto = nombre.partition(" ")
    infinitivo = _FORMAS_CONJUGADAS_HABILIDAD.get(clave_concepto(primera_palabra))
    if infinitivo is None or not separador:
        return decision
    if primera_palabra[:1].isupper():
        infinitivo = infinitivo.capitalize()
    habilidad = decision.habilidad.model_copy(update={"nombre": f"{infinitivo}{separador}{resto}"})
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad_frase_cerrada(
    decision: DecisionCurricular,
    perfil: Mapping[str, object] | None,
) -> DecisionCurricular:
    """Aplica únicamente equivalencias explícitas del perfil de carrera."""

    nombre = decision.habilidad.nombre
    reglas = perfil.get("normalizaciones_habilidad") if isinstance(perfil, Mapping) else None
    if not isinstance(reglas, Mapping):
        return decision
    reemplazo = next(
        (
            str(valor).strip()
            for origen, valor in reglas.items()
            if clave_concepto(origen) == clave_concepto(nombre) and str(valor).strip()
        ),
        None,
    )
    if reemplazo is None:
        return decision
    if nombre[:1].islower():
        reemplazo = reemplazo[:1].lower() + reemplazo[1:]
    habilidad = decision.habilidad.model_copy(update={"nombre": reemplazo})
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad(
    decision: DecisionCurricular,
    perfil: Mapping[str, object] | None = None,
) -> DecisionCurricular:
    """Normaliza formas globales y equivalencias explícitas del perfil."""

    decision = _normalizar_habilidad_forma_conjugada(decision)
    decision = _normalizar_habilidad_nominalizada(decision)
    return _normalizar_habilidad_frase_cerrada(decision, perfil)


def _evidencia_en_texto(fragmento: str, fuente_normalizada: str) -> bool:
    evidencia = clave_concepto(fragmento)
    if len(evidencia) < 3:
        return False
    if evidencia in fuente_normalizada:
        return True
    tokens = set(evidencia.split())
    return len(tokens & set(fuente_normalizada.split())) / len(tokens) >= 0.75


def _reporte_decision(
    decision: DecisionCurricular,
    estado: str,
    problemas: list[str] | None = None,
) -> dict[str, object]:
    fila = decision.model_dump(mode="json")
    fila.update(
        {
            "tipo": "decision_curricular",
            "estado": estado,
            "problemas": problemas or [],
        }
    )
    return fila
