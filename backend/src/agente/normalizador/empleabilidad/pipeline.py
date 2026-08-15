"""Construcción auditable de salidas laborales desde el staging JSONL."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH, cargar_catalogo
from agente.normalizador.empleabilidad.extractor import (
    CadenaCHH,
    ResultadoExtraccion,
    extraer,
    extraer_informe,
)
from agente.normalizador.modelos import (
    Hallazgo,
    ResultadoNormalizacion,
    ResultadoValidacionEntrada,
)

EMPRESA_SCHEMA = [
    "id_empresa",
    "nombre",
    "ruc",
    "razon_social",
    "tipo",
    "descripcion_breve",
    "id_industria",
]
OFERTA_SCHEMA = [
    "id_ofe_laboral",
    "fecha_publicacion",
    "fecha_finalizacion",
    "area",
    "area_especifica",
    "cargo",
    "descripcion_breve",
    "id_carrera",
    "id_empresa",
]
PUESTO_SCHEMA = ["id_puesto", "nombre", "ciclo_requerido", "id_ofe_laboral"]
EVALUACION_SCHEMA = [
    "id_eva_desempenio",
    "fecha_evaluacion",
    "periodo",
    "puntaje_general",
    "recomendaciones",
    "fecha_inicio",
    "fecha_fin",
    "id_carrera",
    "id_requerimiento_laboral",
    "id_empresa",
]
COMPETENCIA_SCHEMA = [
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
]
HABILIDAD_SCHEMA = ["id_habilidad", "nombre_habilidad", "descripcion_breve"]
HERRAMIENTA_SCHEMA = [
    "id_herramienta",
    "nombre_herramienta",
    "descripcion_breve_herramienta",
]
REQUERIMIENTO_SCHEMA = [
    "id_req_laboral",
    "id_oferta_laboral",
    "id_puesto",
    "id_empresa",
    "id_competencia",
    "id_habilidad",
    "id_herramienta",
    "tipo",
]


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _digitos(valor: object) -> str:
    return re.sub(r"\D", "", _texto(valor))


def _hash_id(prefijo: str, *partes: str) -> str:
    payload = "|".join(partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _resumen_texto(datos: dict[str, object]) -> str:
    return _texto(datos.get("funciones", ""))


def _primer_valor(datos: dict[str, object], campos: tuple[str, ...]) -> str:
    for campo in campos:
        valor = _texto(datos.get(campo, ""))
        if valor:
            return valor
    return ""


def _resolver_empresa(
    datos: dict[str, object],
    empresas: dict[str, dict[str, str]],
) -> tuple[str, dict[str, str] | None, str | None]:
    """Resuelve por RUC y usa nombre solo como fallback explícito."""

    ruc = _digitos(datos.get("ruc", ""))
    nombre = _texto(datos.get("razon_social", "")) or _texto(datos.get("empresa", ""))
    if nombre.lower().startswith(("convocatoria", "convocatorias")):
        nombre = "Universidad de Lima"
        ruc = "20107798049"
    if not ruc and not nombre:
        return "", None, "No se encontró RUC ni razón social resoluble."
    clave = f"ruc:{ruc}" if ruc else f"nombre:{nombre.lower()}"
    id_empresa = _hash_id("EMP", clave)
    if id_empresa not in empresas:
        empresas[id_empresa] = {
            "id_empresa": id_empresa,
            "nombre": nombre or ruc,
            "ruc": ruc,
            "razon_social": nombre,
            "tipo": "privada" if ruc else "sin_ruc",
            "descripcion_breve": "",
            "id_industria": "",
        }
    return id_empresa, empresas[id_empresa], None


def _registro_jsonl(ruta: Path) -> Iterator[dict[str, Any]]:
    if not ruta.is_file():
        return
    with ruta.open("r", encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, 1):
            if not linea.strip():
                continue
            datos = json.loads(linea)
            if not isinstance(datos, dict):
                continue
            datos["_linea_staging"] = numero
            yield datos


def _escribir_csv(ruta: Path, columnas: list[str], filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(
            {columna: fila.get(columna, "") for columna in columnas} for fila in filas
        )


def _escribir_jsonl(ruta: Path, filas: list[dict[str, object]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")) + "\n")


def _huella(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _output(ruta: Path, tipo: str, registros: int) -> dict[str, object]:
    ejecucion = next(
        (padre for padre in ruta.parents if padre.name.startswith("NOR_")),
        None,
    )
    return {
        "tipo": tipo,
        "archivo": str(ruta.relative_to(ejecucion)) if ejecucion else ruta.name,
        "registros": registros,
        "bytes": ruta.stat().st_size,
        "sha256": _huella(ruta),
    }


def _cadena_a_requerimiento(
    cadena: CadenaCHH,
    id_oferta: str,
    id_puesto: str,
    id_empresa: str,
    tipo: str,
) -> tuple[tuple[str, ...], dict[str, str]]:
    id_herramienta = cadena.herramienta.id if cadena.herramienta else ""
    negocio = (
        id_oferta,
        id_puesto,
        id_empresa,
        cadena.competencia.id,
        cadena.habilidad.id,
        id_herramienta,
        tipo,
    )
    return negocio, {
        "id_req_laboral": _hash_id("REQ_LAB", *negocio),
        "id_oferta_laboral": id_oferta,
        "id_puesto": id_puesto,
        "id_empresa": id_empresa,
        "id_competencia": cadena.competencia.id,
        "id_habilidad": cadena.habilidad.id,
        "id_herramienta": id_herramienta,
        "tipo": tipo,
    }


def _hallazgo_fila(
    codigo: str,
    severidad: str,
    mensaje: str,
    registro: dict[str, Any],
    detalle: str,
) -> Hallazgo:
    origen = registro.get("origen")
    origen_dict = origen if isinstance(origen, dict) else {}
    fila = origen_dict.get("fila")
    return Hallazgo(
        codigo=codigo,
        severidad=severidad,  # type: ignore[arg-type]
        mensaje=mensaje,
        hoja=str(origen_dict.get("hoja")) if origen_dict.get("hoja") else None,
        fila=int(fila) if isinstance(fila, int) else None,
        detalle=detalle,
    )


def _agregar_evidencias(
    evidencias: list[dict[str, object]],
    registro: dict[str, Any],
    resultado: ResultadoExtraccion,
    id_reqs: list[str],
) -> None:
    origen = registro.get("origen")
    for cadena, id_req in zip(resultado.cadenas, id_reqs, strict=False):
        evidencias.append(
            {
                "id_req_laboral": id_req,
                "id_registro": str(registro.get("id_registro", "")),
                "origen": origen,
                "competencia": cadena.competencia.nombre,
                "habilidad": cadena.habilidad.nombre,
                "herramienta": cadena.herramienta.nombre if cadena.herramienta else None,
                "evidencia": cadena.evidencia,
                "confianza": cadena.confianza,
                "metodo": cadena.metodo,
                "regla": cadena.regla,
            }
        )


def normalizar_staging(
    directorio_ejecucion: Path,
    validacion: ResultadoValidacionEntrada,
    catalogo: CatalogoCHH | None = None,
) -> ResultadoNormalizacion:
    """Genera paquete candidato, cuarentena y gate de publicación."""

    catalogo = catalogo or cargar_catalogo()
    salida = directorio_ejecucion / "salidas"
    reportes = salida / "reportes"
    salida.mkdir(parents=True, exist_ok=True)
    reportes.mkdir(parents=True, exist_ok=True)

    hallazgos: list[Hallazgo] = []
    cuarentena: list[dict[str, object]] = []
    evidencias: list[dict[str, object]] = []
    propuestas: list[dict[str, object]] = []
    empresas: dict[str, dict[str, str]] = {}
    ofertas: dict[str, dict[str, str]] = {}
    puestos: dict[str, dict[str, str]] = {}
    evaluaciones: list[dict[str, str]] = []
    relaciones: dict[tuple[str, ...], dict[str, str]] = {}
    conceptos_comp: dict[str, ConceptoCHH] = {}
    conceptos_hab: dict[str, ConceptoCHH] = {}
    conceptos_herr: dict[str, ConceptoCHH] = {}
    procesados: dict[str, int] = {}

    def registrar_cuarentena(
        registro: dict[str, Any],
        codigo: str,
        mensaje: str,
        detalle: str,
        resultado: ResultadoExtraccion | None = None,
    ) -> None:
        propuestas_locales = (
            [propuesta.a_dict() for propuesta in resultado.propuestas_herramienta]
            if resultado
            else []
        )
        cuarentena.append(
            {
                "id_registro": registro.get("id_registro", ""),
                "universo": registro.get("universo", ""),
                "origen": registro.get("origen", {}),
                "codigo": codigo,
                "mensaje": mensaje,
                "detalle": detalle,
                "datos": registro.get("datos", {}),
                "propuestas_herramienta": propuestas_locales,
            }
        )
        severidad = "error" if codigo.startswith(("OFERTA_", "EMPRESA_", "PUESTO_")) else "warning"
        hallazgos.append(_hallazgo_fila(codigo, severidad, mensaje, registro, detalle))

    for universo in ("publicaciones", "informes"):
        ruta = directorio_ejecucion / "limpios" / f"{universo}.jsonl"
        cantidad = 0
        for registro in _registro_jsonl(ruta):
            cantidad += 1
            datos_objeto = registro.get("datos", {})
            datos = datos_objeto if isinstance(datos_objeto, dict) else {}
            id_empresa, _, error_empresa = _resolver_empresa(datos, empresas)
            if error_empresa:
                registrar_cuarentena(
                    registro,
                    "EMPRESA_NO_RESUELTA",
                    "No se pudo resolver la empresa del registro.",
                    error_empresa,
                )
                continue

            if universo == "publicaciones":
                id_oferta = _hash_id("LAB", str(registro.get("id_registro", "")))
                nombre_puesto = _primer_valor(
                    datos,
                    ("posicion_a_publicar", "cargo_especifico", "cargo"),
                )
                if not nombre_puesto:
                    registrar_cuarentena(
                        registro,
                        "PUESTO_NO_RESUELTO",
                        "La publicación no tiene cargo o posición resoluble.",
                        "Se requiere una identidad de puesto para crear la relación laboral.",
                    )
                    continue
                id_puesto = _hash_id("PUE", id_oferta, nombre_puesto)
                texto = " ".join(
                    _texto(datos.get(campo, ""))
                    for campo in (
                        "posicion_a_publicar",
                        "cargo_especifico",
                        "cargo",
                        "area",
                        "area_especifica",
                        "funciones",
                    )
                )
                resultado = extraer(
                    texto,
                    catalogo,
                    tipo="exige",
                    area=_texto(datos.get("area", "")),
                )
                ofertas[id_oferta] = {
                    "id_ofe_laboral": id_oferta,
                    "fecha_publicacion": _texto(datos.get("fecha_de_publicacion", "")),
                    "fecha_finalizacion": _texto(datos.get("fecha_de_finalizacion", "")),
                    "area": _texto(datos.get("area", "")),
                    "area_especifica": _texto(datos.get("area_especifica", "")),
                    "cargo": _texto(datos.get("cargo", "")),
                    "descripcion_breve": _resumen_texto(datos),
                    "id_carrera": "",
                    "id_empresa": id_empresa,
                }
                puestos[id_puesto] = {
                    "id_puesto": id_puesto,
                    "nombre": nombre_puesto,
                    "ciclo_requerido": _texto(datos.get("ciclo", "")),
                    "id_ofe_laboral": id_oferta,
                }
                tipo = "exige"
            else:
                resultado = extraer_informe(datos, catalogo)
                id_oferta = ""
                id_puesto = ""
                tipo = "aplica"

            propuestas.extend(
                {
                    "id_registro": registro.get("id_registro", ""),
                    "universo": universo,
                    "origen": registro.get("origen", {}),
                    **propuesta.a_dict(),
                }
                for propuesta in resultado.propuestas_herramienta
            )
            if not resultado.cadenas:
                codigo = (
                    "OFERTA_SIN_REQUISITO"
                    if universo == "publicaciones"
                    else "INFORME_SIN_REQUISITO"
                )
                registrar_cuarentena(
                    registro,
                    codigo,
                    "No se obtuvo una cadena Competencia-Habilidad con evidencia versionada.",
                    "El registro queda fuera de las relaciones candidatas para revisión residual.",
                    resultado,
                )
                continue

            ids_reqs: list[str] = []
            for cadena in resultado.cadenas:
                conceptos_comp[cadena.competencia.id] = cadena.competencia
                conceptos_hab[cadena.habilidad.id] = cadena.habilidad
                if cadena.herramienta:
                    conceptos_herr[cadena.herramienta.id] = cadena.herramienta
                negocio, fila = _cadena_a_requerimiento(
                    cadena,
                    id_oferta,
                    id_puesto,
                    id_empresa,
                    tipo,
                )
                if negocio in relaciones:
                    hallazgos.append(
                        _hallazgo_fila(
                            "RELACION_DUPLICADA",
                            "error",
                            "La misma relación laboral apareció más de una vez.",
                            registro,
                            "|".join(negocio),
                        )
                    )
                    continue
                relaciones[negocio] = fila
                ids_reqs.append(fila["id_req_laboral"])
            _agregar_evidencias(evidencias, registro, resultado, ids_reqs)

            if universo == "informes":
                evaluaciones.append(
                    {
                        "id_eva_desempenio": _hash_id(
                            "EVA",
                            str(registro.get("id_registro", "")),
                        ),
                        "fecha_evaluacion": _texto(datos.get("fch_prest_inf_fin", "")),
                        "periodo": _texto(datos.get("ciclo", "")),
                        "puntaje_general": _puntaje(datos.get("desempeno_general", "")),
                        "recomendaciones": _texto(datos.get("sugerencias_y_recomendaciones", "")),
                        "fecha_inicio": _texto(datos.get("fecha_inicio_aprobada", "")),
                        "fecha_fin": _texto(datos.get("fecha_fin_aprobada", "")),
                        "id_carrera": "",
                        "id_requerimiento_laboral": ids_reqs[0] if ids_reqs else "",
                        "id_empresa": id_empresa,
                    }
                )
        procesados[universo] = cantidad

    _escribir_csv(salida / "empresa.csv", EMPRESA_SCHEMA, list(empresas.values()))
    _escribir_csv(salida / "oferta_laboral.csv", OFERTA_SCHEMA, list(ofertas.values()))
    _escribir_csv(salida / "puesto.csv", PUESTO_SCHEMA, list(puestos.values()))
    _escribir_csv(salida / "evaluacion_desempenio.csv", EVALUACION_SCHEMA, evaluaciones)
    _escribir_csv(
        salida / "catalogo_empleabilidad.csv",
        COMPETENCIA_SCHEMA,
        [
            {
                "id_competencia": item.id,
                "nombre_competencia": item.nombre,
                "descripcion_breve_competencia": item.descripcion,
                "tipo_competencia": item.tipo,
            }
            for item in sorted(conceptos_comp.values(), key=lambda item: item.nombre.lower())
        ],
    )
    _escribir_csv(
        salida / "habilidades_empleabilidad.csv",
        HABILIDAD_SCHEMA,
        [
            {
                "id_habilidad": item.id,
                "nombre_habilidad": item.nombre,
                "descripcion_breve": item.descripcion,
            }
            for item in sorted(conceptos_hab.values(), key=lambda item: item.nombre.lower())
        ],
    )
    _escribir_csv(
        salida / "herramientas_empleabilidad.csv",
        HERRAMIENTA_SCHEMA,
        [
            {
                "id_herramienta": item.id,
                "nombre_herramienta": item.nombre,
                "descripcion_breve_herramienta": item.descripcion,
            }
            for item in sorted(conceptos_herr.values(), key=lambda item: item.nombre.lower())
        ],
    )
    requerimientos = list(relaciones.values())
    _escribir_csv(salida / "requerimiento_laboral.csv", REQUERIMIENTO_SCHEMA, requerimientos)
    _escribir_jsonl(reportes / "cuarentena.jsonl", cuarentena)
    _escribir_jsonl(reportes / "evidencias_chh.jsonl", evidencias)
    _escribir_jsonl(reportes / "propuestas_herramienta.jsonl", propuestas)

    publicable = not any(hallazgo.severidad == "error" for hallazgo in hallazgos)
    resumen = {
        "publicable": publicable,
        "registros_procesados": procesados,
        "relaciones": len(requerimientos),
        "cuarentena": len(cuarentena),
        "catalogo_chh": catalogo.resumen(),
        "reglas_chh": "empleabilidad-chh-0.1.0",
        "hallazgos": [hallazgo.a_dict() for hallazgo in hallazgos],
    }
    (reportes / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    archivos = [
        (salida / "empresa.csv", "csv", len(empresas)),
        (salida / "oferta_laboral.csv", "csv", len(ofertas)),
        (salida / "puesto.csv", "csv", len(puestos)),
        (salida / "evaluacion_desempenio.csv", "csv", len(evaluaciones)),
        (salida / "catalogo_empleabilidad.csv", "csv", len(conceptos_comp)),
        (salida / "habilidades_empleabilidad.csv", "csv", len(conceptos_hab)),
        (salida / "herramientas_empleabilidad.csv", "csv", len(conceptos_herr)),
        (salida / "requerimiento_laboral.csv", "csv", len(requerimientos)),
        (reportes / "cuarentena.jsonl", "reporte", len(cuarentena)),
        (reportes / "evidencias_chh.jsonl", "reporte", len(evidencias)),
        (reportes / "propuestas_herramienta.jsonl", "reporte", len(propuestas)),
        (reportes / "resumen.json", "reporte", len(hallazgos)),
    ]
    outputs = tuple(_output(ruta, tipo, cantidad) for ruta, tipo, cantidad in archivos)
    return ResultadoNormalizacion(
        publicable,
        procesados,
        len(requerimientos),
        len(cuarentena),
        outputs,
        tuple(hallazgos),
    )


def _puntaje(valor: object) -> str:
    normalizado = _texto(valor).lower()
    return {
        "muy satisfecho": "5",
        "satisfecho": "4",
        "muy bueno": "4",
        "bueno": "3",
        "regular": "3",
        "insatisfecho": "2",
        "muy insatisfecho": "1",
    }.get(normalizado, normalizado)
