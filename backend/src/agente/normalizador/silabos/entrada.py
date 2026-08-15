"""Puerta de entrada segura para ZIP, DOCX y PDF de una carrera."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Literal

from agente.normalizador.empleabilidad.entrada import calcular_sha256, normalizar_etiqueta
from agente.normalizador.modelos import (
    ArchivoSilabo,
    Hallazgo,
    ResultadoValidacionSilabos,
)

FormatoSilabo = Literal["docx", "pdf"]
FORMATOS: dict[str, FormatoSilabo] = {".docx": "docx", ".pdf": "pdf"}
MAX_ARCHIVOS = 500
MAX_BYTES_ARCHIVO = 50 * 1024 * 1024
MAX_BYTES_DESCOMPRIMIDOS = 500 * 1024 * 1024


def normalizar_carrera(valor: object) -> str:
    """Convierte la carrera declarada a una clave de perfil estable."""

    etiqueta = normalizar_etiqueta(valor).replace(" ", "_")
    return etiqueta.upper()


def normalizar_periodo(valor: object) -> str:
    """Acepta periodos variables, pero exige el formato año-secuencia."""

    periodo = re.sub(r"\s+", "", str(valor or ""))
    return periodo


def _hallazgo(
    codigo: str,
    severidad: str,
    mensaje: str,
    detalle: str | None = None,
) -> Hallazgo:
    return Hallazgo(
        codigo=codigo,
        severidad=severidad,  # type: ignore[arg-type]
        mensaje=mensaje,
        detalle=detalle,
    )


def _formato(nombre: str) -> FormatoSilabo | None:
    return FORMATOS.get(Path(nombre).suffix.lower())


def _ruta_zip_segura(nombre: str) -> bool:
    normalizado = nombre.replace("\\", "/")
    ruta = PurePosixPath(normalizado)
    return not ruta.is_absolute() and ".." not in ruta.parts and all(ruta.parts)


def _es_metadato_macos(nombre: str) -> bool:
    """Reconoce archivos auxiliares creados por Finder dentro de un ZIP."""

    ruta = PurePosixPath(nombre)
    return "__MACOSX" in ruta.parts or ruta.name.startswith("._") or ruta.name == ".DS_Store"


def validar_archivo(
    ruta: Path,
    carrera: str,
    periodo: str,
    nombre_archivo: str | None = None,
) -> ResultadoValidacionSilabos:
    """Valida metadatos y contenido de un paquete sin inferir carrera o periodo."""

    archivo = nombre_archivo or ruta.name
    carrera_normalizada = normalizar_carrera(carrera)
    periodo_normalizado = normalizar_periodo(periodo)
    hallazgos: list[Hallazgo] = []
    archivos: list[ArchivoSilabo] = []
    sha256 = calcular_sha256(ruta) if ruta.exists() else ""

    if not ruta.exists():
        hallazgos.append(
            _hallazgo(
                "FUENTE_NO_ENCONTRADA",
                "error",
                "No se encontró la fuente curricular.",
                archivo,
            )
        )
    if not carrera_normalizada:
        hallazgos.append(
            _hallazgo(
                "CARRERA_OBLIGATORIA",
                "error",
                "La carrera debe ser declarada por la persona usuaria.",
            )
        )
    if re.fullmatch(r"\d{4}-\d+", periodo_normalizado) is None:
        hallazgos.append(
            _hallazgo(
                "PERIODO_INVALIDO",
                "error",
                "El periodo debe tener formato año-secuencia, por ejemplo 2026-1.",
                periodo_normalizado or "vacío",
            )
        )
    if not ruta.exists() or ruta.suffix.lower() not in {".zip", ".docx", ".pdf"}:
        if ruta.exists():
            hallazgos.append(
                _hallazgo(
                    "EXTENSION_CURRICULAR_INVALIDA",
                    "error",
                    "La fuente debe ser ZIP, DOCX o PDF.",
                    ruta.suffix or "sin extensión",
                )
            )
        return ResultadoValidacionSilabos(
            archivo,
            carrera_normalizada,
            periodo_normalizado,
            sha256,
            False,
            (),
            tuple(hallazgos),
        )

    if ruta.suffix.lower() in {".docx", ".pdf"}:
        formato = _formato(ruta.name)
        if formato:
            archivos.append(
                ArchivoSilabo(ruta.name, formato, ruta.stat().st_size)
            )
    else:
        try:
            with zipfile.ZipFile(ruta) as paquete:
                nombres: set[str] = set()
                bytes_totales = 0
                for info in paquete.infolist():
                    if info.is_dir():
                        continue
                    nombre = info.filename.replace("\\", "/")
                    if not _ruta_zip_segura(nombre):
                        hallazgos.append(
                            _hallazgo(
                                "RUTA_ZIP_INSEGURA",
                                "error",
                                "El ZIP contiene una ruta no segura.",
                                info.filename,
                            )
                        )
                        continue
                    if _es_metadato_macos(nombre):
                        hallazgos.append(
                            _hallazgo(
                                "METADATO_MACOS_IGNORADO",
                                "warning",
                                "Se ignoró un archivo auxiliar de macOS dentro del ZIP.",
                                nombre,
                            )
                        )
                        continue
                    if len(archivos) >= MAX_ARCHIVOS:
                        hallazgos.append(
                            _hallazgo(
                                "LIMITE_ARCHIVOS_EXCEDIDO",
                                "error",
                                "El paquete supera el máximo de sílabos procesables.",
                                str(MAX_ARCHIVOS),
                            )
                        )
                        break
                    if info.file_size > MAX_BYTES_ARCHIVO:
                        hallazgos.append(
                            _hallazgo(
                                "ARCHIVO_CURRICULAR_DEMASIADO_GRANDE",
                                "error",
                                "Un archivo curricular supera el límite permitido.",
                                f"{nombre}: {info.file_size} bytes",
                            )
                        )
                        continue
                    bytes_totales += info.file_size
                    if bytes_totales > MAX_BYTES_DESCOMPRIMIDOS:
                        hallazgos.append(
                            _hallazgo(
                                "ZIP_DESCOMPRIMIDO_DEMASIADO_GRANDE",
                                "error",
                                "El contenido descomprimido supera el límite permitido.",
                                str(MAX_BYTES_DESCOMPRIMIDOS),
                            )
                        )
                        break
                    formato = _formato(nombre)
                    if formato is None:
                        hallazgos.append(
                            _hallazgo(
                                "ARCHIVO_NO_CURRICULAR",
                                "warning",
                                "El archivo no es DOCX ni PDF y será ignorado.",
                                nombre,
                            )
                        )
                        continue
                    clave = normalizar_etiqueta(nombre)
                    if clave in nombres:
                        hallazgos.append(
                            _hallazgo(
                                "ARCHIVO_DUPLICADO",
                                "error",
                                "El paquete contiene archivos curriculares duplicados.",
                                nombre,
                            )
                        )
                        continue
                    nombres.add(clave)
                    archivos.append(
                        ArchivoSilabo(
                            nombre,
                            formato,
                            info.file_size,
                        )
                    )
        except (OSError, zipfile.BadZipFile) as exc:
            hallazgos.append(
                _hallazgo(
                    "ZIP_ILEGIBLE",
                    "error",
                    "No se pudo abrir el paquete curricular.",
                    f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            )

    if not archivos:
        hallazgos.append(
            _hallazgo(
                "SIN_SILABOS_PROCESABLES",
                "error",
                "La fuente no contiene archivos DOCX o PDF procesables.",
            )
        )
    valida = not any(hallazgo.severidad == "error" for hallazgo in hallazgos)
    return ResultadoValidacionSilabos(
        archivo,
        carrera_normalizada,
        periodo_normalizado,
        sha256,
        valida,
        tuple(archivos),
        tuple(hallazgos),
    )
