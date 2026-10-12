"""Adaptador del pipeline de empleabilidad que ya existe en el proyecto.

La carpeta ``empleabilidad_normalizacion`` es la fuente de verdad para esta
fuente: limpia el Excel, normaliza carreras, selecciona IDs ``COMP_TEC`` del
catálogo cerrado y deja las publicaciones listas para Neo4j.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from agente.normalizador.modelos import (
    Hallazgo,
    ResultadoLimpieza,
    ResultadoNormalizacion,
    ResultadoValidacionEntrada,
)


def ruta_pipeline_legacy() -> Path:
    return Path(__file__).resolve().parents[4] / "empleabilidad_normalizacion"


def disponible() -> bool:
    raiz = ruta_pipeline_legacy()
    return (raiz / "steps" / "01_limpieza" / "limpiar.py").is_file() and (
        raiz / "catalogo_competencias_tecnicas.xlsx"
    ).is_file()


def _ejecutar(comando: list[str], raiz: Path) -> None:
    resultado = subprocess.run(
        comando,
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if resultado.returncode:
        detalle = (resultado.stderr or resultado.stdout or "").strip()[-1200:]
        raise RuntimeError(f"El pipeline legado falló ({resultado.returncode}): {detalle}")


def _meta(ruta: Path, tipo: str, registros: int) -> dict[str, object]:
    digest = hashlib.sha256(ruta.read_bytes()).hexdigest()
    return {
        "tipo": tipo,
        "archivo": ruta.name,
        "registros": registros,
        "bytes": ruta.stat().st_size,
        "sha256": digest,
    }


def _filas(ruta: Path) -> list[dict[str, str]]:
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def _escribir_csv(ruta: Path, filas: list[dict[str, Any]], columnas: list[str]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def _cargar_importador_legacy() -> Any:
    ruta = ruta_pipeline_legacy() / "steps" / "08_neo4j" / "importar_neo4j.py"
    especificacion = importlib.util.spec_from_file_location("pipeline_empleo_neo4j", ruta)
    if especificacion is None or especificacion.loader is None:
        raise RuntimeError("No se pudo cargar el lector de salidas del pipeline legado.")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _preparar_salidas_neo4j(
    directorio: Path,
    csv_filtrado: Path,
    catalogo: Path,
    ciiu: Path,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    modulo = _cargar_importador_legacy()
    catalogo_filas, ids_catalogo = modulo.read_catalog(catalogo)
    descripciones_ciiu = modulo.read_ciiu_catalog(ciiu)
    datos = modulo.read_publications(csv_filtrado, ids_catalogo, descripciones_ciiu)
    salida = directorio / "salidas"

    empresas = datos["companies"]
    ofertas = datos["offers"]
    puestos = [
        {**fila, "id_ofe_laboral": oferta_id}
        for oferta_id in {str(item["id_ofe_laboral"]) for item in ofertas}
        for fila in datos["positions"]
        if any(
            str(oferta.get("id_puesto")) == str(fila.get("id_puesto"))
            for oferta in ofertas
            if str(oferta.get("id_ofe_laboral")) == oferta_id
        )
    ]
    requisitos = [
        {**fila, "id_oferta_laboral": fila.get("id_ofe_laboral", "")}
        for fila in datos["requirements"]
    ]

    _escribir_csv(salida / "empresa.csv", empresas, list(empresas[0]) if empresas else [
        "id_empresa", "nombre", "ruc", "ruc_original", "razon_social", "tipo", "descripcion_breve"
    ])
    _escribir_csv(salida / "oferta_laboral.csv", ofertas, list(ofertas[0]) if ofertas else [
        "id_ofe_laboral", "fecha_publicacion", "fecha_finalizacion", "area", "area_especifica",
        "cargo", "tipo_puesto", "descripcion_breve", "id_empresa", "id_industria",
        "id_carrera", "id_puesto",
    ])
    _escribir_csv(salida / "puesto.csv", puestos, list(puestos[0]) if puestos else [
        "id_puesto", "nombre", "ciclo_requerido", "id_ofe_laboral"
    ])
    _escribir_csv(salida / "habilidades_empleabilidad.csv", catalogo_filas, [
        "id_habilidad", "nombre_habilidad", "descripcion_breve"
    ])
    _escribir_csv(salida / "requerimiento_laboral.csv", requisitos, [
        "id_req_laboral", "tipo", "id_empresa", "id_ofe_laboral", "id_oferta_laboral",
        "id_puesto", "id_habilidad"
    ])
    _escribir_csv(salida / "catalogo_empleabilidad.csv", [], [
        "id_competencia", "nombre_competencia", "descripcion_breve_competencia", "tipo_competencia"
    ])
    _escribir_csv(salida / "herramientas_empleabilidad.csv", [], [
        "id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"
    ])
    _escribir_csv(salida / "evaluacion_desempenio.csv", [], [
        "id_eva_desempenio", "fecha_evaluacion", "periodo", "puntaje_general", "recomendaciones",
        "fecha_inicio", "fecha_fin", "id_carrera", "id_requerimiento_laboral", "id_empresa"
    ])
    return datos, catalogo_filas


def ejecutar_pipeline_legado(
    ruta_entrada: Path,
    directorio_ejecucion: Path,
    validacion: ResultadoValidacionEntrada,
    nombre_hoja: str,
    limite_prueba: int = 0,
) -> tuple[ResultadoLimpieza, ResultadoNormalizacion, dict[str, object]]:
    """Ejecuta las etapas 1–7 del pipeline correcto y adapta sus salidas."""

    if not disponible():
        raise RuntimeError("No está disponible la carpeta empleabilidad_normalizacion.")
    ruta_entrada = ruta_entrada.resolve()
    directorio_ejecucion = directorio_ejecucion.resolve()
    raiz = ruta_pipeline_legacy()
    trabajo = directorio_ejecucion / "salidas" / "_pipeline_empleabilidad"
    trabajo.mkdir(parents=True, exist_ok=True)
    limite = str(limite_prueba or 0)
    prefijo = str(
        validacion.hojas[0].anios[0]
        if validacion.hojas and validacion.hojas[0].anios
        else "lote"
    )
    limpio = trabajo / f"{prefijo}_limpio.csv"
    carreras = trabajo / f"{prefijo}_limpio_carreras.csv"
    jsonl = trabajo / f"{prefijo}_para_qwen.jsonl"
    json_array = trabajo / f"{prefijo}_para_qwen.json"
    catalogo = trabajo / "catalogo_habilidades_oficial.csv"
    mapa = trabajo / "carrera_competencia_oficial.csv"
    qwen = trabajo / f"{prefijo}_resultado_catalogo_qwen.jsonl"
    errores_qwen = trabajo / f"{prefijo}_resultado_catalogo_qwen.errors.jsonl"
    log_qwen = trabajo / f"{prefijo}_resultado_catalogo_qwen.log"
    cache = trabajo / f"{prefijo}_resultado_catalogo_qwen.cache"
    completo = trabajo / f"{prefijo}_resultado_final_catalogo_completo.csv"
    completo_jsonl = trabajo / f"{prefijo}_resultado_final_catalogo_completo.jsonl"
    filtrado = trabajo / f"{prefijo}_resultado_final_catalogo_filtrado.csv"
    filtrado_jsonl = trabajo / f"{prefijo}_resultado_final_catalogo_filtrado.jsonl"
    scripts = raiz / "steps"

    _ejecutar([
        sys.executable, str(scripts / "01_limpieza" / "limpiar.py"),
        "--input", str(ruta_entrada), "--sheet", nombre_hoja, "--column", "Funciones",
        "--output", str(limpio),
    ], raiz)
    _ejecutar([
        sys.executable, str(scripts / "02_normalizacion_carreras" / "normalizar_carreras.py"),
        "--input", str(limpio), "--output", str(carreras),
    ], raiz)
    _ejecutar([
        sys.executable, str(scripts / "03_generar_json" / "generar_json.py"),
        "--input", str(carreras), "--output", str(jsonl), "--array-output", str(json_array),
    ], raiz)
    _ejecutar([
        sys.executable, str(scripts / "04_generar_catalogo" / "generar_catalogo_oficial.py"),
        "--input", str(raiz / "catalogo_competencias_tecnicas.xlsx"),
        "--output", str(catalogo), "--career-map-output", str(mapa),
    ], raiz)
    _ejecutar([
        sys.executable, str(scripts / "05_procesar_qwen_catalogo" / "procesar_qwen_catalogo.py"),
        "--input", str(jsonl), "--catalog", str(catalogo), "--career-map", str(mapa),
        "--output", str(qwen), "--errors-output", str(errores_qwen), "--log-output", str(log_qwen),
        "--cache-dir", str(cache), "--endpoint", os.getenv("EMPLEABILIDAD_LLM_ENDPOINT", "http://localhost:11434/api/chat"),
        "--model", os.getenv("EMPLEABILIDAD_LLM_MODEL", "qwen3:8b"), "--limit", limite, "--resume",
    ], raiz)
    _ejecutar([
        sys.executable, str(scripts / "06_devolver_catalogo" / "devolver_catalogo.py"),
        "--input-csv", str(carreras), "--qwen-jsonl", str(qwen), "--catalog", str(catalogo),
        "--output-csv", str(completo), "--output-jsonl", str(completo_jsonl), "--limit", limite,
    ], raiz)
    _ejecutar([
        sys.executable, str(scripts / "07_filtrar_sin_vacios" / "filtrar_sin_vacios.py"),
        "--input-csv", str(completo), "--input-jsonl", str(completo_jsonl),
        "--output-csv", str(filtrado), "--output-jsonl", str(filtrado_jsonl),
    ], raiz)

    filas_completas = _filas(completo)
    cuarentena: list[dict[str, object]] = []
    hallazgos: list[Hallazgo] = []
    for indice, fila in enumerate(filas_completas, start=2):
        try:
            cantidad = int(str(fila.get("cantidad_competencias_catalogo") or "0"))
        except ValueError:
            cantidad = 0
        if cantidad:
            continue
        detalle = "La publicación no tiene un ID COMP_TEC respaldado por el catálogo cerrado."
        cuarentena.append(
            {
                "codigo": "OFERTA_SIN_COMPETENCIA_CATALOGO",
                "origen": {"hoja": nombre_hoja, "fila": indice},
                "datos": fila,
                "detalle": detalle,
            }
        )
        hallazgos.append(Hallazgo(
            codigo="OFERTA_SIN_COMPETENCIA_CATALOGO", severidad="error",
            mensaje="No se encontró una competencia técnica del catálogo oficial.",
            hoja=nombre_hoja, fila=indice, detalle=detalle,
        ))

    datos_neo4j, catalogo_filas = _preparar_salidas_neo4j(
        directorio_ejecucion, filtrado, catalogo, raiz / "outputs" / "catalogo_ciiu_rev4.csv"
    )
    reportes = directorio_ejecucion / "salidas" / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    (reportes / "cuarentena.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in cuarentena),
        encoding="utf-8",
    )
    evidencias = []
    for fila in datos_neo4j["requirements"]:
        evidencias.append(
            {
                "id_req_laboral": fila["id_req_laboral"],
                "id_habilidad": fila["id_habilidad"],
                "metodo": "catalogo_cerrado",
            }
        )
    (reportes / "evidencias_chh.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in evidencias),
        encoding="utf-8",
    )
    (reportes / "propuestas_herramienta.jsonl").write_text("", encoding="utf-8")
    resumen = {
        "publicable": not hallazgos,
        "registros_procesados": {"publicaciones": len(filas_completas)},
        "relaciones": len(datos_neo4j["requirements"]),
        "cuarentena": len(cuarentena),
        "catalogo": {"tipo": "Habilidad", "ids": len(catalogo_filas), "prefijo": "COMP_TEC_"},
        "pipeline": "empleabilidad_normalizacion",
        "hallazgos": [item.a_dict() for item in hallazgos],
    }
    (reportes / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    limpieza_outputs = tuple(
        _meta(ruta, "pipeline", len(_filas(ruta)) if ruta.suffix == ".csv" else 0)
        for ruta in (limpio, carreras, jsonl)
    )
    limpieza = ResultadoLimpieza({"publicaciones": len(filas_completas)}, limpieza_outputs, ())
    nombres_salida = [
        "empresa.csv", "oferta_laboral.csv", "puesto.csv", "evaluacion_desempenio.csv",
        "catalogo_empleabilidad.csv", "habilidades_empleabilidad.csv",
        "herramientas_empleabilidad.csv",
        "requerimiento_laboral.csv", "reportes/cuarentena.jsonl", "reportes/evidencias_chh.jsonl",
        "reportes/propuestas_herramienta.jsonl", "reportes/resumen.json",
    ]
    outputs_data: list[dict[str, object]] = []
    for nombre in nombres_salida:
        ruta = directorio_ejecucion / "salidas" / nombre
        if nombre.endswith(".csv"):
            registros = len(_filas(ruta))
            tipo = "csv"
        elif "cuarentena" in nombre:
            registros, tipo = len(cuarentena), "reporte"
        elif "evidencias" in nombre:
            registros, tipo = len(evidencias), "reporte"
        else:
            registros, tipo = 1, "reporte"
        outputs_data.append(_meta(ruta, tipo, registros))
    normalizacion = ResultadoNormalizacion(
        not hallazgos,
        {"publicaciones": len(filas_completas)},
        len(datos_neo4j["requirements"]),
        len(cuarentena),
        tuple(outputs_data),
        tuple(hallazgos),
    )
    catalogo_resumen = {
        "disponible": True,
        "version": hashlib.sha256(catalogo.read_bytes()).hexdigest()[:16],
        "competencias": 0,
        "habilidades": len(catalogo_filas),
        "herramientas": 0,
        "fuentes": [catalogo.name],
    }
    return limpieza, normalizacion, catalogo_resumen
