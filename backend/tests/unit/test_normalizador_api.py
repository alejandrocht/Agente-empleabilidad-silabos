"""Prueba del contrato HTTP mínimo del normalizador laboral."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from concurrent.futures import Future
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from docx import Document
from fastapi.testclient import TestClient

from agente.api import normalizador, servidor
from agente.api.acceso_administrativo import peer_is_loopback
from agente.normalizador import ejecuciones
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.modelos import (
    Hallazgo,
    ProgresoLimpiezaLLM,
    ResultadoLimpiezaSilabos,
    ResultadoValidacionSilabos,
    UltimoChunkLimpiezaLLM,
)
from api import servidor as api_servidor


def test_guardia_reconoce_solo_loopback_directo() -> None:
    assert peer_is_loopback("127.0.0.1") is True
    assert peer_is_loopback("::1") is True
    assert peer_is_loopback("::ffff:127.0.0.1") is True
    assert peer_is_loopback("testclient") is False
    assert peer_is_loopback("192.168.1.5") is False
    assert peer_is_loopback(None) is False


def test_rutas_administrativas_rechazan_peer_remoto_sin_ejecutar_operacion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    llamada = False

    def listar(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal llamada
        llamada = True
        return {"ejecuciones": []}

    monkeypatch.setattr(gestor, "listar_historial", listar)
    cliente = TestClient(servidor.app, client=("203.0.113.10", 0))

    respuesta = cliente.get(
        "/normalizador/ejecuciones",
        headers={
            "host": "127.0.0.1",
            "x-forwarded-for": "127.0.0.1",
            "forwarded": "for=127.0.0.1",
            "x-real-ip": "127.0.0.1",
        },
    )

    assert respuesta.status_code == 403
    assert llamada is False
    assert respuesta.json()["detail"] == "Acceso administrativo solo disponible desde loopback."


def test_guardia_rechaza_formas_no_loopback_y_no_resuelve_nombres() -> None:
    for host in (
        "127.0.0.2.example",
        "10.0.0.1",
        "8.8.8.8",
        "2001:db8::1",
        "::ffff:10.0.0.1",
        "not-an-ip",
        " 127.0.0.1",
        "127.0.0.1 ",
    ):
        assert peer_is_loopback(host) is False


def test_rutas_publicas_conservan_acceso_desde_peer_remoto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def responder_falso(*_args: object, **_kwargs: object) -> str:
        return "respuesta local"

    async def metadatos_falsos() -> dict[str, object]:
        return {"fuente": "fixture"}

    class GrafoFalso:
        async def astream_events(
            self, *_args: object, **_kwargs: object
        ) -> AsyncIterator[dict[str, object]]:
            if False:
                yield {}

    monkeypatch.setattr(api_servidor, "responder", responder_falso)
    monkeypatch.setattr(
        cast(Any, getattr(api_servidor, "dashboard")), "metadatos", metadatos_falsos
    )
    monkeypatch.setattr(api_servidor, "construir_grafo", lambda: GrafoFalso())
    cliente = TestClient(servidor.app, client=("203.0.113.10", 0))

    assert cliente.get("/health").json() == {"status": "ok"}
    assert cliente.get("/dashboard/metadata").json() == {"fuente": "fixture"}
    assert cliente.post("/preguntar", json={"texto": "hola"}).status_code == 200
    assert cliente.post("/chat", json={"pregunta": "hola"}).status_code == 200
    stream = cliente.post("/chat/stream", json={"input": {"pregunta": "hola"}})
    assert stream.status_code == 200
    assert "event: end" in stream.text


def _fuente_docx() -> bytes:
    """Construye un sílabo mínimo para verificar el contrato multipart."""

    documento = Document()
    metadata = documento.add_table(rows=1, cols=2)
    metadata.cell(0, 0).text = "Curso"
    metadata.cell(0, 1).text = "Diseño de bases de datos"
    sumilla = documento.add_table(rows=2, cols=1)
    sumilla.cell(0, 0).text = "Sumilla"
    sumilla.cell(1, 0).text = "Modelamiento de bases de datos relacionales."
    competencia = documento.add_table(rows=2, cols=3)
    competencia.cell(0, 0).text = "Competencias genéricas"
    competencia.cell(0, 1).text = "Descripción"
    competencia.cell(0, 2).text = "Código"
    competencia.cell(1, 0).text = "Diseño de bases de datos"
    competencia.cell(1, 1).text = "Diseñar estructuras de datos relacionales."
    competencia.cell(1, 2).text = "G1"
    logro = documento.add_table(rows=2, cols=3)
    logro.cell(0, 0).text = "Logro de aprendizaje general"
    logro.cell(0, 1).text = "Descripción"
    logro.cell(0, 2).text = "Competencias"
    logro.cell(1, 0).text = "L1"
    logro.cell(1, 1).text = "Modelar bases de datos relacionales"
    logro.cell(1, 2).text = "G1"
    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("ruta", "nombre", "datos"),
    [
        (
            "/normalizador/silabos",
            "fuente.zip",
            {"carrera": "Marketing", "periodo": "2026-1"},
        ),
    ],
)
def test_rechaza_content_length_excesivo_antes_de_crear_ejecucion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ruta: str,
    nombre: str,
    datos: dict[str, str],
) -> None:

    gestor = GestorEjecuciones(tmp_path)
    llamadas = 0

    def crear(*_args: object, **_kwargs: object) -> None:
        nonlocal llamadas
        llamadas += 1
        raise AssertionError("crear no debe ejecutarse antes del rechazo")

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    monkeypatch.setattr(gestor, "crear", crear)
    monkeypatch.setattr(normalizador, "MAX_UPLOAD_BYTES", 10)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        ruta,
        files={"archivo": (nombre, b"pequeno", "application/octet-stream")},
        data=datos,
        headers={"content-length": "11"},
    )

    assert respuesta.status_code == 413
    assert respuesta.json() == {"detail": "La carga excede el límite permitido."}
    assert llamadas == 0
    assert list(tmp_path.iterdir()) == []


def test_ruta_de_empleabilidad_no_existe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/empleabilidad",
        files={"archivo": ("fuente.xlsx", b"retirado", "application/octet-stream")},
    )

    assert respuesta.status_code == 404
    assert list(tmp_path.iterdir()) == []


def test_inicia_silabos_persiste_hitl_por_defecto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    monkeypatch.setattr(gestor, "iniciar_validacion_silabos", lambda *_args: None)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos",
        files={"archivo": ("silabo.zip", b"contenido", "application/zip")},
        data={"carrera": "Marketing", "periodo": "2026-1"},
    )

    assert respuesta.status_code == 202
    assert respuesta.json()["parametros"] == {
        "carrera": "Marketing",
        "periodo": "2026-1",
        "hitl": "1",
    }


def test_inicia_silabos_persiste_hitl_explicito_cero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    monkeypatch.setattr(gestor, "iniciar_validacion_silabos", lambda *_args: None)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos",
        files={"archivo": ("silabo.zip", b"contenido", "application/zip")},
        data={"carrera": "Marketing", "periodo": "2026-1", "hitl": "0"},
    )

    assert respuesta.status_code == 202
    assert respuesta.json()["parametros"]["hitl"] == "0"


def test_inicia_silabos_rechaza_hitl_invalido(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos",
        files={"archivo": ("silabo.zip", b"contenido", "application/zip")},
        data={"carrera": "Marketing", "periodo": "2026-1", "hitl": "2"},
    )

    assert respuesta.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_inicia_y_consulta_ejecucion_de_silabos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """La fuente curricular completa la limpieza y expone sus outputs."""

    gestor = GestorEjecuciones(tmp_path)
    futuros: list[Future[object]] = []
    enviar = gestor._executor.submit

    def capturar_futuro(*args: Any, **kwargs: Any) -> Future[object]:
        futuro = enviar(*args, **kwargs)
        futuros.append(futuro)
        return futuro

    monkeypatch.setattr(gestor._executor, "submit", capturar_futuro)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos",
        files={
            "archivo": (
                "silabo.docx",
                _fuente_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"carrera": "Ingeniería de Sistemas", "periodo": "2030-1"},
    )

    assert respuesta.status_code == 202
    id_ejecucion = respuesta.json()["id_ejecucion"]
    assert len(futuros) == 1
    futuros[0].result(timeout=30)

    objeto = gestor._obtener_objeto(id_ejecucion)
    manifest = json.loads((objeto.directorio / "manifest.json").read_text(encoding="utf-8"))
    respuesta_get = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()
    diagnostico = (
        objeto.estado,
        manifest["estado"],
        respuesta_get["estado"],
        respuesta_get["release_gate"]["decision"],
    )
    assert diagnostico[:3] == (objeto.estado,) * 3, (
        f"Estados tras completar Future: {diagnostico!r}"
    )
    assert diagnostico[0] in {"limpiado", "limpiado_con_advertencias"}
    ejecucion = respuesta_get
    assert ejecucion["validacion_silabos"]["valida"] is True
    assert not {"validacion", "limpieza", "normalizacion"} & ejecucion.keys()
    assert ejecucion["limpieza_silabos"]["registros"] == 1
    assert ejecucion["release_gate"]["decision"] == "ALLOW_IMPORT"
    outputs = {output["archivo"] for output in ejecucion["outputs"]}
    assert outputs == {
        "salidas/curso.csv",
        "salidas/silabo.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_habilidades.csv",
        "salidas/catalogo_logros.csv",
        "salidas/cobertura_curricular.csv",
    }
    descarga = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/salidas/cobertura_curricular.csv"
    )
    assert descarga.status_code == 200
    assert "attachment" in descarga.headers["content-disposition"]
    assert descarga.content
    cuarentena = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/cuarentena")
    assert cuarentena.status_code == 200
    assert cuarentena.json()["total"] == 0
    assert not any(hallazgo["severidad"] == "error" for hallazgo in ejecucion["hallazgos"])


def test_silabos_bloqueado_no_expone_outputs_curriculares_y_conserva_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    id_ejecucion, directorio = gestor.crear("silabos", "entrada.zip")
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True)
    for nombre in (
        "catalogo_competencias.csv",
        "catalogo_habilidades.csv",
        "catalogo_herramientas.csv",
        "cobertura_curricular.csv",
    ):
        (directorio / "salidas" / nombre).write_text("id\nuno\n", encoding="utf-8")
    (reportes / "candidatos_curriculares.json").write_text("{}", encoding="utf-8")
    (reportes / "decisiones_curriculares.jsonl").write_text("{}\n", encoding="utf-8")
    (reportes / "cuarentena.jsonl").write_text('{"motivo":"revisar"}\n', encoding="utf-8")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.limpieza_silabos = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=(
            {
                "tipo": "csv_curricular",
                "archivo": "salidas/cobertura_curricular.csv",
                "registros": 1,
            },
            {
                "tipo": "candidatos_curriculares",
                "archivo": "salidas/reportes/candidatos_curriculares.json",
                "registros": 1,
            },
            {
                "tipo": "decisiones_curriculares",
                "archivo": "salidas/reportes/decisiones_curriculares.jsonl",
                "registros": 1,
            },
        ),
        hallazgos=(),
        release_gate={
            "decision": "BLOCK_IMPORT",
            "checks": {
                "approval": {
                    "canonical_materialized": False,
                    "pending_decision": 1,
                }
            },
        },
    )
    gestor._persistir(ejecucion)
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}")
    cobertura = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/salidas/cobertura_curricular.csv"
    )
    candidatos = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/"
        "salidas/reportes/candidatos_curriculares.json"
    )
    cuarentena = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/cuarentena")
    no_permitida = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/outputs/manifest.json")

    assert estado.status_code == 200
    assert estado.json()["outputs"] == []
    assert "draft_outputs" not in estado.json()
    assert cobertura.status_code == 404
    assert candidatos.status_code == 404
    assert cuarentena.status_code == 200
    assert cuarentena.json()["filas"] == [{"motivo": "revisar"}]
    assert no_permitida.status_code == 404


def test_silabos_bloqueado_archivado_expone_solo_borradores_csv_canonicos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    id_ejecucion, directorio = gestor.crear("silabos", "entrada.zip")
    nombres = (
        "curso.csv",
        "silabo.csv",
        "catalogo_competencias.csv",
        "catalogo_habilidades.csv",
        "catalogo_logros.csv",
        "cobertura_curricular.csv",
    )
    salida_dir = directorio / "salidas"
    salida_dir.mkdir(parents=True)
    for nombre in nombres:
        (salida_dir / nombre).write_text("id\nuno\n", encoding="utf-8")
    reporte = salida_dir / "reportes" / "candidatos_curriculares.json"
    reporte.parent.mkdir()
    reporte.write_text("{}", encoding="utf-8")
    arbitrario = salida_dir / "otro.csv"
    arbitrario.write_text("id\nprivado\n", encoding="utf-8")

    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "no_publicado"
    ejecucion.limpieza_silabos = ResultadoLimpiezaSilabos(
        registros=74,
        outputs=(),
        hallazgos=(),
        release_gate={
            "decision": "BLOCK_IMPORT",
            "blockers": ["TECHNICAL_ANALYSIS_INCOMPLETE", "UNLINKED_SOURCE_OUTCOME"],
        },
    )
    gestor._persistir(ejecucion)
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()
    descargas = {
        nombre: cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/outputs/salidas/{nombre}")
        for nombre in nombres
    }

    assert estado["estado"] == "no_publicado"
    assert estado["outputs"] == []
    assert estado["limpieza_silabos"]["outputs"] == []
    assert estado["release_gate"]["decision"] == "BLOCK_IMPORT"
    assert [salida["archivo"] for salida in estado["draft_outputs"]] == [
        f"salidas/{nombre}" for nombre in nombres
    ]
    assert all(salida["bytes"] == len("id\nuno\n") for salida in estado["draft_outputs"])
    assert all(
        salida["sha256"] == hashlib.sha256(b"id\nuno\n").hexdigest()
        for salida in estado["draft_outputs"]
    )
    assert all(descarga.status_code == 200 for descarga in descargas.values())
    assert (
        cliente.get(
            f"/normalizador/ejecuciones/{id_ejecucion}/outputs/salidas/otro.csv"
        ).status_code
        == 404
    )
    assert (
        cliente.get(
            f"/normalizador/ejecuciones/{id_ejecucion}/outputs/salidas/reportes/candidatos_curriculares.json"
        ).status_code
        == 404
    )


def test_silabos_aprobado_expone_outputs_curriculares(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    id_ejecucion, directorio = gestor.crear("silabos", "entrada.zip")
    salida = directorio / "salidas" / "cobertura_curricular.csv"
    salida.parent.mkdir(parents=True)
    salida.write_text("id\nuno\n", encoding="utf-8")
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir()
    (reportes / "candidatos_curriculares.json").write_text("{}", encoding="utf-8")
    (reportes / "decisiones_curriculares.jsonl").write_text("{}\n", encoding="utf-8")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.limpieza_silabos = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=(
            {
                "tipo": "csv_curricular",
                "archivo": "salidas/cobertura_curricular.csv",
                "registros": 1,
            },
            {
                "tipo": "candidatos_curriculares",
                "archivo": "salidas/reportes/candidatos_curriculares.json",
                "registros": 1,
            },
        ),
        hallazgos=(),
        release_gate={
            "decision": "ALLOW_IMPORT",
            "checks": {
                "approval": {
                    "canonical_materialized": True,
                    "pending_decision": 0,
                }
            },
        },
    )
    gestor._persistir(ejecucion)
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}")
    descarga = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/salidas/cobertura_curricular.csv"
    )
    candidatos = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/"
        "salidas/reportes/candidatos_curriculares.json"
    )

    assert estado.status_code == 200
    assert estado.json()["outputs"] == [
        {
            "tipo": "csv_curricular",
            "archivo": "salidas/cobertura_curricular.csv",
            "registros": 1,
            "bytes": len("id\nuno\n"),
            "sha256": hashlib.sha256(b"id\nuno\n").hexdigest(),
        }
    ]
    assert descarga.status_code == 200
    assert descarga.content == b"id\nuno\n"
    assert candidatos.status_code == 404


def test_inicia_extraccion_cactus_sin_persistir_credenciales(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """El endpoint automático recibe credenciales, pero nunca las guarda en el manifest."""

    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    llamada: dict[str, object] = {}

    def fake_iniciar(
        id_ejecucion: str,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
    ) -> None:
        llamada.update(
            id_ejecucion=id_ejecucion,
            carrera=carrera,
            periodo=periodo,
            usuario=usuario,
            contrasena=contrasena,
        )

    monkeypatch.setattr(gestor, "iniciar_extraccion_silabos", fake_iniciar)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos/cactus",
        json={
            "carrera": "Marketing",
            "periodo": "2026-1",
            "usuario": "usuario@ulima.edu.pe",
            "contrasena": "secreto-no-persistir",
        },
    )

    assert respuesta.status_code == 202
    datos = respuesta.json()
    assert llamada["carrera"] == "Marketing"
    assert llamada["periodo"] == "2026-1"
    assert llamada["usuario"] == "usuario@ulima.edu.pe"
    assert llamada["contrasena"] == "secreto-no-persistir"
    assert datos["parametros"] == {
        "carrera": "Marketing",
        "periodo": "2026-1",
        "fuente": "cactus",
        "hitl": "1",
    }
    assert "usuario@ulima.edu.pe" not in respuesta.text
    assert "secreto-no-persistir" not in respuesta.text


def test_inicia_extraccion_cactus_persiste_hitl_explicito_cero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    monkeypatch.setattr(gestor, "iniciar_extraccion_silabos", lambda *_args: None)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos/cactus",
        json={
            "carrera": "Marketing",
            "periodo": "2026-1",
            "usuario": "usuario@ulima.edu.pe",
            "contrasena": "secreto-no-persistir",
            "hitl": 0,
        },
    )

    assert respuesta.status_code == 202
    assert respuesta.json()["parametros"]["hitl"] == "0"


def test_inicia_extraccion_cactus_rechaza_hitl_invalido(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/silabos/cactus",
        json={
            "carrera": "Marketing",
            "periodo": "2026-1",
            "usuario": "usuario@ulima.edu.pe",
            "contrasena": "secreto-no-persistir",
            "hitl": 2,
        },
    )

    assert respuesta.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_valida_longitud_de_contrasena_sin_hacer_echo_del_secreto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    secreto = "secreto-demasiado-largo" * 20
    respuesta = cliente.post(
        "/normalizador/silabos/cactus",
        json={
            "carrera": "Marketing",
            "periodo": "2026-1",
            "usuario": "usuario@ulima.edu.pe",
            "contrasena": secreto,
        },
    )

    assert respuesta.status_code == 422
    assert secreto not in respuesta.text
    assert "entre 1 y 200 caracteres" in respuesta.json()["detail"]


def test_expone_pendientes_y_release_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    gestor = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    id_ejecucion, directorio = gestor.crear("silabos", "entrada.zip")
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True)
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        '{"id_propuesta":"PROP_1","nombre_competencia":"Competencia técnica"}\n',
        encoding="utf-8",
    )
    (reportes / "release_gate.json").write_text(
        '{"version":"curricular-release-gate/v1","decision":"BLOCK_IMPORT",'
        '"blockers":["PROVENANCE_INCOMPLETE"]}',
        encoding="utf-8",
    )

    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?limite=1")
    assert pendientes.status_code == 200
    assert pendientes.json()["total"] == 1
    assert len(pendientes.json()["filas"]) == 1

    gate = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/release-gate")
    assert gate.status_code == 200
    assert gate.json()["release_gate"]["decision"] == "BLOCK_IMPORT"


def test_warning_de_ingestion_marca_limpieza_curricular_con_advertencias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Un warning de ingreso persiste y determina el estado final aunque limpiar no halle nada."""

    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "paquete.zip")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    warning = Hallazgo(
        codigo="ARCHIVO_NO_CURRICULAR",
        severidad="warning",
        mensaje="El archivo no es DOCX ni PDF y será ignorado.",
    )
    validacion = ResultadoValidacionSilabos(
        archivo="paquete.zip",
        carrera="Ingeniería de Sistemas",
        periodo="2030-1",
        sha256="sha256",
        valida=True,
        archivos=(),
        hallazgos=(warning,),
    )
    limpieza = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=(),
        hallazgos=(),
        publicable=True,
    )

    monkeypatch.setattr(ejecuciones, "validar_silabos", lambda *_: validacion)
    monkeypatch.setattr(ejecuciones, "limpiar_silabos", lambda *_args, **_kwargs: limpieza)

    gestor._validar_silabos(
        ejecucion,
        tmp_path / "paquete.zip",
        "Ingeniería de Sistemas",
        "2030-1",
    )

    respuesta = cast(Any, gestor.obtener(id_ejecucion))
    manifest = (directorio / "manifest.json").read_text(encoding="utf-8")

    assert respuesta["estado"] == "limpiado_con_advertencias"
    assert respuesta["hallazgos"] == [warning.a_dict()]
    assert respuesta["validacion_silabos"]["hallazgos"] == [warning.a_dict()]
    assert manifest.count("ARCHIVO_NO_CURRICULAR") == 2


def test_persiste_progreso_llm_en_el_manifest_durante_limpieza(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "paquete.zip")
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    (reportes / "release_gate.json").write_text(
        json.dumps({"decision": "ALLOW_IMPORT"}), encoding="utf-8"
    )
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    validacion = ResultadoValidacionSilabos(
        archivo="paquete.zip",
        carrera="Marketing",
        periodo="2026-1",
        sha256="sha256",
        valida=True,
        archivos=(),
        hallazgos=(),
    )
    limpieza = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=(),
        hallazgos=(),
        publicable=True,
    )

    def limpiar_con_progreso(*_args: object, **kwargs: Any) -> ResultadoLimpiezaSilabos:
        actualizar = kwargs["al_actualizar_progreso_llm"]
        assert callable(actualizar)
        inicial = kwargs["progreso_inicial"]
        assert inicial is not None
        assert inicial.fase == "preparando"
        assert inicial.silabos_totales == 0
        assert inicial.eventos[-1].mensaje.startswith("Preparando la extracción")
        actualizar(
            ProgresoLimpiezaLLM(
                fase="completado",
                chunks_completados=2,
                chunks_totales=2,
                logros_procesados=12,
                logros_totales=12,
                silabos_procesados=3,
                silabos_totales=3,
                decisiones_cacheadas=4,
                reintentos=1,
                ultimo_chunk=UltimoChunkLimpiezaLLM("analista", 4, 1),
                reporte_final="disponible",
            )
        )
        en_polling = cast(Any, gestor.obtener(id_ejecucion))
        manifest_polling = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
        api_polling = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()
        assert (
            en_polling["estado"],
            manifest_polling["estado"],
            api_polling["estado"],
        ) == ("limpiando",) * 3
        assert en_polling["release_gate"]["decision"] == "ALLOW_IMPORT"
        assert api_polling["release_gate"]["decision"] == "ALLOW_IMPORT"
        assert en_polling["progreso_llm"] == {
            "fase": "completado",
            "chunks_completados": 2,
            "chunks_totales": 2,
            "logros_procesados": 12,
            "logros_totales": 12,
            "silabos_detectados": 0,
            "silabos_procesados": 3,
            "silabos_totales": 3,
            "decisiones_cacheadas": 4,
            "reintentos": 1,
            "logros_detectados": 0,
            "mensaje": "",
            "ultimo_chunk": {"fase": "analista", "logros": 4, "silabos": 1},
            "reporte_final": "disponible",
            "eventos": [],
            "silabos": [],
        }
        return limpieza

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_LLM", "true")
    monkeypatch.setattr(ejecuciones, "validar_silabos", lambda *_: validacion)
    monkeypatch.setattr(ejecuciones, "limpiar_silabos", limpiar_con_progreso)

    gestor._validar_silabos(ejecucion, tmp_path / "paquete.zip", "Marketing", "2026-1")

    manifest = (directorio / "manifest.json").read_text(encoding="utf-8")
    estado = cast(Any, gestor.obtener(id_ejecucion))
    assert estado["progreso_llm"]["reporte_final"] == "disponible"
    assert '"progreso_llm"' in manifest
    assert '"decisiones_cacheadas": 4' in manifest


def test_publica_evento_de_error_sin_perder_historial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, _directorio = gestor.crear("silabos", "paquete.zip")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    validacion = ResultadoValidacionSilabos(
        archivo="paquete.zip",
        carrera="Marketing",
        periodo="2026-1",
        sha256="sha256",
        valida=True,
        archivos=(),
        hallazgos=(),
    )

    def limpiar_con_error(*_args: object, **kwargs: Any) -> ResultadoLimpiezaSilabos:
        actualizar = kwargs["al_actualizar_progreso_llm"]
        progreso = replace(
            kwargs["progreso_inicial"],
            fase="analista",
            chunks_completados=1,
            chunks_totales=2,
            logros_procesados=8,
            logros_totales=16,
            silabos_detectados=76,
            silabos_procesados=1,
        ).con_evento("Chunk 1/2 de Analista LLM completado.")
        actualizar(progreso)
        raise RuntimeError("fallo tardío simulado")

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_LLM", "true")
    monkeypatch.setattr(ejecuciones, "validar_silabos", lambda *_: validacion)
    monkeypatch.setattr(ejecuciones, "limpiar_silabos", limpiar_con_error)

    gestor._validar_silabos(ejecucion, tmp_path / "paquete.zip", "Marketing", "2026-1")

    progreso_final = gestor.obtener(id_ejecucion)["progreso_llm"]
    assert isinstance(progreso_final, dict)
    assert progreso_final["fase"] == "error"
    assert any(evento["mensaje"].startswith("Chunk 1/2") for evento in progreso_final["eventos"])
    assert progreso_final["eventos"][-1]["mensaje"].startswith("La ejecución terminó con error")
    assert progreso_final["silabos_detectados"] == 76
    assert progreso_final["silabos_procesados"] == 1
