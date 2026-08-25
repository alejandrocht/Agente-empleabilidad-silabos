"""Tests for explicit curricular pending states and import release safety."""

from __future__ import annotations

import json
from pathlib import Path

from agente.db.neo4j_importador import ImportadorNeo4j
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH
from agente.normalizador.modelos import ArchivoSilabo, ResultadoValidacionSilabos
from agente.normalizador.silabos import analista_llm
from agente.normalizador.silabos.salida import (
    ARCHIVOS_SALIDA,
    construir_salidas_curriculares,
    evaluar_release_gate,
)


def _validacion() -> ResultadoValidacionSilabos:
    return ResultadoValidacionSilabos(
        archivo="curso.docx",
        carrera="MARKETING",
        periodo="2026-1",
        sha256="entrada",
        valida=True,
        archivos=(ArchivoSilabo("curso.docx", "docx", 1),),
        hallazgos=(),
    )


def _registro() -> dict[str, object]:
    return {
        "id_silabo": "SIL_1",
        "id_curso": "CUR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "origen": {"archivo": "curso.docx", "formato": "docx"},
        "datos": {
            "curso": "Investigación de mercados",
            "logros_especificos": [
                {"etiqueta": "L1", "descripcion": "Analizar campañas de marketing"}
            ],
            "competencias_declaradas": [
                {
                    "codigo": "G1",
                    "nombre": "Gestión de campañas",
                    "descripcion": "Diseñar y evaluar campañas de marketing.",
                }
            ],
            "herramientas_evidencia": [],
        },
    }


def test_concepto_llm_fuera_del_catalogo_queda_pendiente_de_ampliacion(
    tmp_path: Path,
) -> None:
    registro = _registro()
    descripcion = "Analizar campañas de marketing"
    id_habilidad = analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", descripcion)
    decision = analista_llm.DecisionCurricular(
        id_habilidad_fuente=id_habilidad,
        competencia=analista_llm.ConceptoPropuesto(
            nombre="Diseño de campañas omnicanal",
            descripcion="Diseñar campañas omnicanal con evidencia curricular.",
        ),
        habilidad=analista_llm.ConceptoPropuesto(
            nombre="Optimizar campañas omnicanal",
            descripcion="Optimizar campañas omnicanal con evidencia curricular.",
        ),
        evidencia=[descripcion],
        confianza=0.98,
    )

    resultado = construir_salidas_curriculares(
        [registro],
        _validacion(),
        tmp_path / "NOR_TEST",
        CatalogoCHH((), (), (), {}, ("test",), "catalogo-v1"),
        decisiones_llm={id_habilidad: decision},
    )

    salida = tmp_path / "NOR_TEST" / "salidas"
    assert not any((salida / nombre).is_file() for nombre, _ in ARCHIVOS_SALIDA)
    assert (salida / "reportes" / "candidatos_curriculares.json").is_file()
    pendientes = [
        json.loads(line)
        for line in (
            tmp_path / "NOR_TEST" / "salidas" / "reportes" / "pendientes_curriculares.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    pendientes_por_tipo = {fila["tipo"]: fila for fila in pendientes}
    assert pendientes_por_tipo["competencia"]["estado_resolucion"] == (
        "PENDIENTE_AMPLIACION_PERFIL"
    )
    assert pendientes_por_tipo["habilidad"]["estado_resolucion"] == (
        "PENDIENTE_AMPLIACION_PERFIL"
    )
    assert pendientes_por_tipo["habilidad"]["propuesta"]["nombre"] == (
        "Optimizar campañas omnicanal"
    )
    assert resultado.relaciones == 0


def test_release_gate_bloquea_provenance_incompleto() -> None:
    gate = evaluar_release_gate(
        carrera="MARKETING",
        periodo="2026-1",
        registros=1,
        logros_fuente=1,
        filas_por_archivo={
            "catalogo_competencias.csv": [
                {"id_competencia": "COMP_1"},
            ],
            "catalogo_habilidades.csv": [],
            "catalogo_herramientas.csv": [],
            "cobertura_curricular.csv": [],
        },
        competencias_fuente=[],
        habilidades_fuente=[],
        herramientas_fuente=[],
        relaciones_canonicas=set(),
        pendientes=[],
        hallazgos=[],
    )

    assert gate["decision"] == "BLOCK_IMPORT"
    assert "COMP_1" in gate["checks"]["provenance"]["missing_competencies"]


def test_importador_bloquea_ejecucion_sin_release_gate(tmp_path: Path) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "curriculo.zip")
    (directorio / "manifest.json").write_text(
        json.dumps(
            {
                "id_ejecucion": id_ejecucion,
                "tipo": "silabos",
                "estado": "limpiado",
                "validacion_silabos": {"valida": True},
            }
        ),
        encoding="utf-8",
    )
    salidas = directorio / "salidas"
    salidas.mkdir()
    for archivo, esquema in ARCHIVOS_SALIDA:
        (salidas / archivo).write_text(
            ",".join(esquema) + "\n",
            encoding="utf-8",
        )

    preview = ImportadorNeo4j(gestor, driver_factory=lambda: object()).previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(error["codigo"] == "RELEASE_GATE_AUSENTE" for error in preview["errores"])


def test_importador_bloquea_pendiente_aunque_un_gate_legacy_diga_allow(
    tmp_path: Path,
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "curriculo.zip",
        {"carrera": "Marketing", "periodo": "2026-1"},
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "limpiado"
    gestor._persistir(ejecucion)
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    (reportes / "pendientes_curriculares.jsonl").write_text(
        json.dumps(
            {
                "id_pendiente": "PEN_1",
                "tipo": "herramienta",
                "propuesta": {"nombre": "CampaignOS"},
                "evidencia": ["CampaignOS"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reportes / "release_gate.json").write_text(
        json.dumps({"decision": "ALLOW_IMPORT"}),
        encoding="utf-8",
    )

    preview = ImportadorNeo4j(gestor, driver_factory=lambda: object()).previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(error["codigo"] == "PENDING_DECISIONS" for error in preview["errores"])
