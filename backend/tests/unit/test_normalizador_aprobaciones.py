"""Public-interface tests for the curricular approval checkpoint."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agente.api import normalizador, servidor
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH
from agente.normalizador.modelos import ArchivoSilabo, ResultadoValidacionSilabos
from agente.normalizador.silabos import analista_llm, aprobaciones
from agente.normalizador.silabos.analista_llm import ConceptoPropuesto, DecisionCurricular
from agente.normalizador.silabos.salida import construir_salidas_curriculares


def _csv(ruta: Path, columnas: tuple[str, ...]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()


def _preparar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    gestor = GestorEjecuciones(tmp_path / "ejecuciones")
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "curriculo.zip",
        {"carrera": "Marketing", "periodo": "2026-1"},
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "limpiado"
    gestor._persistir(ejecucion)

    salida = directorio / "salidas"
    reportes = salida / "reportes"
    reportes.mkdir(parents=True)
    _csv(salida / "catalogo_competencias.csv", aprobaciones.COMPETENCIAS_SCHEMA)
    _csv(salida / "catalogo_habilidades.csv", aprobaciones.HABILIDADES_SCHEMA)
    _csv(salida / "catalogo_herramientas.csv", aprobaciones.HERRAMIENTAS_SCHEMA)
    _csv(salida / "cobertura_curricular.csv", aprobaciones.COBERTURA_SCHEMA)
    (reportes / "pendientes_curriculares.jsonl").write_text(
        "\n".join(
            json.dumps(fila, ensure_ascii=False)
            for fila in (
                {
                    "id_pendiente": "PEN_COMP",
                    "tipo": "competencia",
                    "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "archivo": "curso.docx",
                    "id_habilidad_fuente": "HAB_SRC_1",
                    "descripcion_fuente": "Diseñar campañas.",
                    "propuesta": {
                        "nombre": "Diseño omnicanal",
                        "descripcion": "Diseñar campañas omnicanal.",
                        "tipo": "dura",
                    },
                    "evidencia": ["Diseñar campañas omnicanal."],
                },
                {
                    "id_pendiente": "PEN_TOOL",
                    "tipo": "herramienta",
                    "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "archivo": "curso.docx",
                    "id_habilidad_fuente": "HAB_SRC_1",
                    "descripcion_fuente": "Usar plataforma.",
                    "propuesta": {
                        "nombre": "CampaignOS",
                        "descripcion": "Plataforma curricular.",
                        "tipo": "herramienta",
                    },
                    "evidencia": ["Usar CampaignOS."],
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for nombre in (
        "competencias_fuente.jsonl",
        "habilidades_fuente.jsonl",
        "herramientas_fuente.jsonl",
        "cobertura_curricular_canonica.jsonl",
    ):
        (reportes / nombre).write_text("", encoding="utf-8")
    (reportes / "release_gate.json").write_text(
        json.dumps(
            {
                "version": "curricular-release-gate/v1",
                "decision": "BLOCK_IMPORT",
                "checks": {
                    "source_coverage": {"records": 1, "logros_fuente": 1},
                    "structural_errors": {"ok": True},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(aprobaciones, "ruta_catalogos", lambda: tmp_path / "catalogos")
    return directorio, id_ejecucion


def test_aprobar_y_mantener_pendiente_promueve_solo_al_perfil_y_conserva_evidencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_COMP", "decision": "ADD"},
            {"id_pendiente": "PEN_TOOL", "decision": "KEEP_PENDING"},
        ],
        actor="revisor@example.com",
    )

    assert resultado["aprobacion"]["accepted"] == 1
    assert resultado["aprobacion"]["remaining_pending"] == 1
    perfil = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    assert (perfil / "catalogo_competencias.csv").is_file()
    assert (
        list(csv.DictReader((perfil / "catalogo_herramientas.csv").open(encoding="utf-8-sig")))
        == []
    )
    pendientes = [
        json.loads(line)
        for line in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {fila["id_pendiente"]: fila["decision"] for fila in pendientes} == {
        "PEN_COMP": "ADD",
        "PEN_TOOL": "KEEP_PENDING",
    }
    assert pendientes[1]["evidencia"] == ["Usar CampaignOS."]
    decisiones = (
        (directorio / "salidas/reportes/decisiones_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(decisiones) == 2
    assert all("revisor@example.com" in linea for linea in decisiones)


def test_decision_de_paquete_resuelve_todas_las_filas_accionables_de_forma_atomica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    paquete = aprobaciones._paquetes(directorio, aprobaciones._filas_clasificadas(directorio))[0]

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [{"id_paquete_chh": paquete["id_paquete_chh"], "decision": "KEEP_PENDING"}],
        actor="package-reviewer",
    )

    assert resultado["aprobacion"]["accepted_in_request"] == 0
    assert resultado["aprobacion"]["kept_pending_in_request"] == 2
    filas = [
        json.loads(line)
        for line in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {fila["decision"] for fila in filas} == {"KEEP_PENDING"}
    assert {fila["id_paquete_chh"] for fila in filas} == {paquete["id_paquete_chh"]}


def test_repetir_la_misma_decision_es_idempotente_y_los_ids_duplicados_se_rechazan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    solicitud = [{"id_pendiente": "PEN_COMP", "decision": "ADD"}]

    primera = aprobaciones.aplicar_decisiones_curriculares(directorio, solicitud)
    segunda = aprobaciones.aplicar_decisiones_curriculares(directorio, solicitud)

    assert primera["aprobacion"] == segunda["aprobacion"]
    assert (
        len(
            (directorio / "salidas/reportes/decisiones_curriculares.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        == 1
    )
    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="duplicados"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [
                {"id_pendiente": "PEN_TOOL", "decision": "ADD"},
                {"id_pendiente": "PEN_TOOL", "decision": "KEEP_PENDING"},
            ],
        )


def test_aprobar_los_tres_extremos_materializa_una_cadena_chh_valida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    filas.append(
        {
            "id_pendiente": "PEN_SKILL",
            "tipo": "habilidad",
            "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "archivo": "curso.docx",
            "id_habilidad_fuente": "HAB_SRC_1",
            "descripcion_fuente": "Analizar campañas.",
            "propuesta": {
                "nombre": "Analizar campañas",
                "descripcion": "Analizar campañas.",
            },
            "evidencia": ["Analizar campañas."],
        }
    )
    ruta.write_text("".join(json.dumps(fila) + "\n" for fila in filas), encoding="utf-8")

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_COMP", "decision": "ADD"},
            {"id_pendiente": "PEN_TOOL", "decision": "ADD"},
            {"id_pendiente": "PEN_SKILL", "decision": "ADD"},
        ],
    )

    gate = resultado["aprobacion"]["release_gate"]
    assert gate["decision"] == "ALLOW_IMPORT"
    assert gate["checks"]["chh_graph"]["ok"] is True
    cobertura = list(
        csv.DictReader((directorio / "salidas/cobertura_curricular.csv").open(encoding="utf-8-sig"))
    )
    assert len(cobertura) == 1
    assert cobertura[0]["id_herramienta"]


def test_no_permite_aprobacion_de_ejecucion_en_curso_o_id_desconocido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    (directorio / "manifest.json").write_text(json.dumps({"estado": "limpiando"}), encoding="utf-8")
    with pytest.raises(aprobaciones.AprobacionNoPermitida, match="terminado"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio, [{"id_pendiente": "PEN_COMP", "decision": "ADD"}]
        )


def test_no_permite_promover_un_pendiente_de_otra_carrera_o_periodo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    filas[0]["carrera"] = "INGENIERIA_DE_SISTEMAS"
    filas[0]["periodo"] = "2030-1"
    ruta.write_text("".join(json.dumps(fila) + "\n" for fila in filas), encoding="utf-8")

    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="alcance"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [{"id_pendiente": "PEN_COMP", "decision": "ADD"}],
        )


def test_endpoint_expone_y_aplica_el_checkpoint_curricular(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    gestor_api = GestorEjecuciones(directorio.parent)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)

    cliente = TestClient(servidor.app)
    pendientes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    )
    assert pendientes.status_code == 200
    assert pendientes.json()["total"] == 2

    respuesta = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "actor": "revisor@example.com",
            "decisiones": [{"id_pendiente": "PEN_COMP", "decision": "ADD"}],
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["accepted"] == 1

    restantes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    )
    assert restantes.json()["total"] == 1
    assert restantes.json()["filas"][0]["id_pendiente"] == "PEN_TOOL"

    reloaded = GestorEjecuciones(directorio.parent)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", reloaded)
    estado_reiniciado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}")
    assert estado_reiniciado.status_code == 200
    assert estado_reiniciado.json()["aprobacion_curricular"]["accepted"] == 1


def test_endpoint_acepta_decision_de_paquete_y_expone_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    gestor_api = GestorEjecuciones(directorio.parent)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)
    cliente = TestClient(servidor.app)

    pendientes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    ).json()
    assert pendientes["paquetes_total"] == 1
    assert pendientes["revision"]
    package_id = pendientes["paquetes"][0]["id_paquete_chh"]
    respuesta = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "paquetes": [{"id_paquete_chh": package_id, "decision": "KEEP_PENDING"}],
            "revision": pendientes["revision"],
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["kept_pending_in_request"] == 2


def test_endpoint_rechaza_payload_con_listas_de_decision_ambiguas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, id_ejecucion = _preparar(tmp_path, monkeypatch)
    gestor_api = GestorEjecuciones(tmp_path / "ejecuciones")
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)
    respuesta = TestClient(servidor.app).post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [{"id_pendiente": "PEN_COMP", "decision": "KEEP_PENDING"}],
            "paquetes": [{"id_paquete_chh": "PKG_UNKNOWN", "decision": "KEEP_PENDING"}],
        },
    )

    assert respuesta.status_code == 422
    assert "Payload ambiguo" in respuesta.json()["detail"]


def test_relaciones_de_evidencia_no_cruzan_competencias_de_otro_source_package() -> None:
    scope = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_1",
    }
    fila = {**scope, "id_pendiente": "PEN_1"}
    archivos = {
        "catalogo_competencias.csv": [{"id_competencia": "COMP_1"}, {"id_competencia": "COMP_2"}],
        "catalogo_habilidades.csv": [{"id_habilidad": "HAB_1"}],
        "catalogo_herramientas.csv": [],
    }
    fuentes = {
        "competencias_fuente.jsonl": [
            {**scope, "id_competencia_canonica": "COMP_1"},
            {**{**scope, "id_habilidad_fuente": "SRC_2"}, "id_competencia_canonica": "COMP_2"},
        ],
        "habilidades_fuente.jsonl": [{**scope, "id_habilidad_canonica": "HAB_1"}],
        "herramientas_fuente.jsonl": [],
    }
    relaciones: list[dict[str, str]] = []

    aprobaciones._añadir_relaciones_de_evidencia(
        fila,
        "habilidad",
        "HAB_1",
        archivos,
        fuentes,
        relaciones,
    )

    assert [relation["id_competencia"] for relation in relaciones] == ["COMP_1"]


def test_clasifica_repetidas_exactas_semanticas_y_herramienta_no_relacionada() -> None:
    filas = aprobaciones.clasificar_propuestas(
        [
            {
                "id_pendiente": "PEN_EXACT_2",
                "tipo": "competencia",
                "propuesta": {"nombre": "Gestión de campañas", "descripcion": "Diseñar campañas."},
                "evidencia": ["Diseñar campañas."],
                "confianza": 0.91,
            },
            {
                "id_pendiente": "PEN_EXACT_1",
                "tipo": "competencia",
                "propuesta": {
                    "nombre": "Gestión de campañas",
                    "descripcion": "Gestionar campañas.",
                },
                "evidencia": ["Gestionar campañas."],
                "confianza": 0.62,
            },
            {
                "id_pendiente": "PEN_SEM_1",
                "tipo": "habilidad",
                "propuesta": {
                    "nombre": "Análisis de datos empresariales",
                    "descripcion": "Analizar datos.",
                },
                "evidencia": ["Analizar datos."],
            },
            {
                "id_pendiente": "PEN_SEM_2",
                "tipo": "habilidad",
                "propuesta": {
                    "nombre": "Análisis de datos comerciales",
                    "descripcion": "Analizar datos.",
                },
                "evidencia": ["Analizar datos."],
            },
            {
                "id_pendiente": "PEN_TOOL",
                "tipo": "herramienta",
                "propuesta": {"nombre": "Slack", "descripcion": "Herramienta de colaboración."},
                "evidencia": ["Evaluar estados financieros."],
            },
        ]
    )

    por_id = {fila["id_pendiente"]: fila for fila in filas}
    assert por_id["PEN_EXACT_1"]["duplicado_exacto"] is True
    assert por_id["PEN_EXACT_2"]["duplicado_exacto"] is True
    assert (
        por_id["PEN_EXACT_1"]["grupo_duplicado_exacto"]
        == por_id["PEN_EXACT_2"]["grupo_duplicado_exacto"]
    )
    assert por_id["PEN_EXACT_2"]["auto_deduplicated"] is False
    assert por_id["PEN_EXACT_2"]["exact_duplicate_representative_id"] == "PEN_EXACT_2"
    assert por_id["PEN_EXACT_2"]["requiere_decision"] is True
    assert por_id["PEN_EXACT_1"]["auto_deduplicated"] is True
    assert por_id["PEN_EXACT_1"]["exact_duplicate_representative_id"] == "PEN_EXACT_2"
    assert por_id["PEN_EXACT_1"]["estado_resolucion"] == "AUTO_DEDUPLICADA"
    assert por_id["PEN_EXACT_1"]["requiere_decision"] is False
    assert por_id["PEN_EXACT_1"]["clasificacion"]["requires_human_decision"] is False
    assert por_id["PEN_SEM_1"]["posible_duplicado_semantico"] is True
    assert por_id["PEN_SEM_2"]["posible_duplicado_semantico"] is True
    assert por_id["PEN_TOOL"]["herramienta_no_relacionada"] is True
    assert "SUSPICIOUS_UNRELATED_TOOL" in por_id["PEN_TOOL"]["flags"]
    assert {fila["id_pendiente"] for fila in filas} == {
        "PEN_EXACT_1",
        "PEN_EXACT_2",
        "PEN_SEM_1",
        "PEN_SEM_2",
        "PEN_TOOL",
    }


def test_deduplicacion_exacta_se_limita_al_paquete_fuente_y_no_cruza_cursos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    pendientes = [
        {
            "id_pendiente": "PEN_EXACT_REP",
            "tipo": "competencia",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_habilidad_fuente": "SRC_1",
            "propuesta": {"nombre": "Gestión de campañas", "descripcion": "Diseñar."},
            "evidencia": ["Diseñar campañas omnicanal."],
            "confianza": 0.95,
        },
        {
            "id_pendiente": "PEN_EXACT_SUPPRESSED",
            "tipo": "competencia",
            "id_curso": "CUR_2",
            "id_silabo": "SIL_2",
            "id_habilidad_fuente": "SRC_2",
            "propuesta": {"nombre": "Gestión de campañas", "descripcion": "Gestionar."},
            "evidencia": ["Gestionar campañas omnicanal."],
            "confianza": 0.40,
        },
        {
            "id_pendiente": "PEN_SEM_1",
            "tipo": "habilidad",
            "id_curso": "CUR_3",
            "id_silabo": "SIL_3",
            "id_habilidad_fuente": "SRC_3",
            "propuesta": {"nombre": "Analizar datos empresariales"},
            "evidencia": ["Analizar datos."],
        },
        {
            "id_pendiente": "PEN_SEM_2",
            "tipo": "habilidad",
            "id_curso": "CUR_4",
            "id_silabo": "SIL_4",
            "id_habilidad_fuente": "SRC_4",
            "propuesta": {"nombre": "Analizar datos comerciales"},
            "evidencia": ["Analizar datos."],
        },
    ]
    (directorio / "salidas/reportes/pendientes_curriculares.jsonl").write_text(
        "".join(json.dumps(fila) + "\n" for fila in pendientes),
        encoding="utf-8",
    )

    cola = aprobaciones.pendientes_para_revision(directorio)
    assert {fila["id_pendiente"] for fila in cola} == {
        "PEN_EXACT_REP",
        "PEN_EXACT_SUPPRESSED",
        "PEN_SEM_1",
        "PEN_SEM_2",
    }
    resumen = aprobaciones.resumen_aprobacion_curricular(directorio)
    assert resumen["pendientes_por_decidir"] == 4
    assert resumen["remaining_pending"] == 4
    assert resumen["clasificacion"]["auto_deduplicated_rows"] == 0

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [{"id_pendiente": "PEN_EXACT_REP", "decision": "ADD"}],
    )
    aprobacion = resultado["aprobacion"]
    assert aprobacion["pendientes_por_decidir"] == 3
    assert aprobacion["remaining_pending"] == 3
    assert aprobacion["release_gate"]["checks"]["approval"]["pending_decision"] == 3
    assert "PENDING_DECISIONS" in aprobacion["release_gate"]["blockers"]

    persistidas = [
        json.loads(line)
        for line in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    independiente = next(
        fila for fila in persistidas if fila["id_pendiente"] == "PEN_EXACT_SUPPRESSED"
    )
    assert independiente["evidencia"] == ["Gestionar campañas omnicanal."]
    assert independiente["auto_deduplicated"] is False

    aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_EXACT_SUPPRESSED", "decision": "ADD"},
            {"id_pendiente": "PEN_SEM_1", "decision": "KEEP_PENDING"},
            {"id_pendiente": "PEN_SEM_2", "decision": "KEEP_PENDING"},
        ],
    )
    competencias = list(
        csv.DictReader(
            (directorio / "salidas/catalogo_competencias.csv").open(encoding="utf-8-sig")
        )
    )
    assert [fila["nombre_competencia"] for fila in competencias] == ["Gestión de campañas"]


def test_no_materializa_csv_canónico_mientras_haya_propuestas_sin_decidir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validacion = ResultadoValidacionSilabos(
        archivo="curso.docx",
        carrera="MARKETING",
        periodo="2026-1",
        sha256="entrada",
        valida=True,
        archivos=(ArchivoSilabo("curso.docx", "docx", 1),),
        hallazgos=(),
    )
    registro = {
        "id_silabo": "SIL_1",
        "id_curso": "CUR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "origen": {"archivo": "curso.docx", "formato": "docx"},
        "datos": {
            "curso": "Marketing",
            "logros_especificos": [{"etiqueta": "L1", "descripcion": "Analizar campañas."}],
            "competencias_declaradas": [],
            "herramientas_evidencia": [],
        },
    }
    id_habilidad_fuente = analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", "Analizar campañas.")
    resultado = DecisionCurricular(
        id_habilidad_fuente=id_habilidad_fuente,
        competencia=ConceptoPropuesto(
            nombre="Diseño omnicanal", descripcion="Diseñar campañas omnicanal."
        ),
        habilidad=ConceptoPropuesto(nombre="Analizar campañas", descripcion="Analizar campañas."),
        evidencia=["Analizar campañas."],
        confianza=0.9,
    )

    construir_salidas_curriculares(
        [registro],
        validacion,
        tmp_path / "NOR_0123456789abcdef",
        CatalogoCHH((), (), (), {}, ("test",), "catalogo-v1"),
        decisiones_llm={id_habilidad_fuente: resultado},
    )

    salida = tmp_path / "NOR_0123456789abcdef" / "salidas"
    reportes = salida / "reportes"
    assert (reportes / "competencias_fuente.jsonl").is_file()
    assert (reportes / "pendientes_curriculares.jsonl").is_file()
    assert (reportes / "candidatos_curriculares.json").is_file()
    assert not any((salida / nombre).exists() for nombre, _ in aprobaciones.ARCHIVOS_SALIDA)
    politica = json.loads((reportes / "candidatos_curriculares.json").read_text())[
        "decision_policy"
    ]
    assert politica["exact_duplicates"] == "AUTO_DEDUPLICATE"
    assert politica["semantic_duplicates"] == "REVIEW_ONLY"
    assert politica["suspicious_tools"] == "REVIEW_ONLY"
    assert politica["auto_delete"] is False
    assert politica["auto_merge"] is False

    (tmp_path / "NOR_0123456789abcdef" / "manifest.json").write_text(
        json.dumps(
            {
                "id_ejecucion": "NOR_0123456789abcdef",
                "tipo": "silabos",
                "estado": "limpiado",
                "parametros": {"carrera": "MARKETING", "periodo": "2026-1"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(aprobaciones, "ruta_catalogos", lambda: tmp_path / "catalogos")
    gestor_api = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)
    filas = [
        json.loads(line)
        for line in (reportes / "pendientes_curriculares.jsonl").read_text().splitlines()
    ]
    cliente = TestClient(servidor.app)
    pendientes = cliente.get(
        "/normalizador/ejecuciones/NOR_0123456789abcdef/pendientes?incluir_resueltas=false"
    )
    assert pendientes.status_code == 200
    assert pendientes.json()["total"] == 2
    respuesta = cliente.post(
        "/normalizador/ejecuciones/NOR_0123456789abcdef/pendientes/decidir",
        json={
            "actor": "test",
            "decisiones": [
                {
                    "id_pendiente": fila["id_pendiente"],
                    "decision": "ADD" if fila["tipo"] == "competencia" else "KEEP_PENDING",
                }
                for fila in filas
            ],
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["pendientes_por_decidir"] == 0
    assert all((salida / nombre).is_file() for nombre, _ in aprobaciones.ARCHIVOS_SALIDA)
    assert (
        json.loads((reportes / "candidatos_curriculares.json").read_text())["materialized"] is True
    )
