"""Pure Cactus file, URL, archive, and checkpoint persistence helpers."""

from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

FORMATS_PROCESABLES = {".pdf", ".docx"}


class CactusExtractorError(RuntimeError):
    """Error accionable de la fuente externa Cactus."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


class _RespuestaDemasiadoGrande(RuntimeError):
    """La fuente externa superó el límite de memoria de una respuesta."""


def strip_accents(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_text(value: object) -> str:
    """Normaliza texto para comparar nodos de la vista Domino."""

    return re.sub(r"\s+", " ", strip_accents(str(value or ""))).upper().strip()


def sanitize_filename(value: object, max_len: int = 120) -> str:
    """Convierte una etiqueta externa en una ruta de archivo segura."""

    text = strip_accents(str(value or "SIN_NOMBRE")).upper().strip()
    text = re.sub(r"[^\w\s\-]", "", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    if not text:
        return "SIN_NOMBRE"
    return text[:max_len] if len(text) > max_len else text


def is_login_page(text: str) -> bool:
    return (
        "_CustomLoginform" in text
        or "names.nsf?Login" in text
        or "Acceso a los sistemas de informaci" in text
    )


def _silabo_url(html: str) -> tuple[str, str] | None:
    match = re.search(
        r'href="([^"]*\$FILE/[^" ]*\.(pdf|docx?)[^" ]*)"',
        html,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2).lower()


def _leer_respuesta_limitada(respuesta: requests.Response, limite: int) -> bytes:
    """Lee una respuesta por chunks y evita materializar cuerpos ilimitados."""

    try:
        content_length = respuesta.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > limite:
                    raise _RespuestaDemasiadoGrande(
                        f"respuesta superior al límite de {limite} bytes"
                    )
            except ValueError:
                pass

        partes: list[bytes] = []
        total = 0
        for parte in respuesta.iter_content(chunk_size=64 * 1024):
            if not parte:
                continue
            total += len(parte)
            if total > limite:
                raise _RespuestaDemasiadoGrande(
                    f"respuesta superior al límite de {limite} bytes"
                )
            partes.append(parte)
        return b"".join(partes)
    finally:
        respuesta.close()


def empaquetar_archivos_cactus(raiz: Path, destino: Path) -> tuple[str, ...]:
    """Crea el ZIP interno que consume el validador curricular existente."""

    raiz_resuelta = raiz.resolve()
    archivos = sorted(
        ruta
        for ruta in raiz.rglob("*")
        if ruta.is_file() and ruta.suffix.lower() in FORMATS_PROCESABLES
    )
    nombres: list[str] = []
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
        for ruta in archivos:
            try:
                nombre = ruta.resolve().relative_to(raiz_resuelta).as_posix()
            except ValueError as exc:
                raise CactusExtractorError(
                    "CACTUS_RUTA_INVALIDA",
                    "La extracción produjo un archivo fuera de su directorio aislado.",
                ) from exc
            if not nombre or ".." in Path(nombre).parts:
                raise CactusExtractorError(
                    "CACTUS_RUTA_INVALIDA",
                    "La extracción produjo una ruta curricular no segura.",
                )
            paquete.write(ruta, nombre)
            nombres.append(nombre)
    return tuple(nombres)


def _url_adjunto_segura(base_url: str, valor: str) -> bool:
    """Restrict attachments to the authenticated Cactus HTTPS origin."""

    base = urlparse(base_url)
    adjunto = urlparse(valor)
    return (
        base.scheme == "https"
        and adjunto.scheme == base.scheme
        and adjunto.hostname == base.hostname
        and adjunto.port == base.port
        and adjunto.username is None
        and adjunto.password is None
    )


def _url_adjunto(base_url: str, valor: str, unid: str) -> str:
    if valor.startswith("/"):
        return urljoin(base_url, valor)
    if valor.startswith("http"):
        return valor
    if "$FILE/" in valor:
        return f"{base_url}/0/{unid}/$FILE/{valor.split('$FILE/')[-1]}"
    return f"{base_url}/{valor}"


def _es_html(body: bytes) -> bool:
    return body[:20].lower().lstrip().startswith((b"<!doctype", b"<html"))


def _clave_checkpoint(info: dict[str, str]) -> str:
    return f"Ciclo_{sanitize_filename(info['nivel'])}/{info['nombre_curso']}"


def _existe_checkpoint(raiz: Path, clave: str) -> bool:
    ruta = raiz / clave
    return any(ruta.with_suffix(extension).is_file() for extension in (".pdf", ".docx"))


def _cargar_checkpoint(raiz: Path) -> set[str]:
    ruta = raiz / ".checkpoint.json"
    if not ruta.is_file():
        return set()
    try:
        valor = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    if not isinstance(valor, list):
        return set()
    return {
        str(item)
        for item in valor
        if isinstance(item, str) and _existe_checkpoint(raiz, item)
    }


def _guardar_checkpoint(raiz: Path, done: set[str]) -> None:
    (raiz / ".checkpoint.json").write_text(
        json.dumps(sorted(done), ensure_ascii=False),
        encoding="utf-8",
    )


def ruta_curso(raiz: Path, info: dict[str, str], extension: str) -> Path:
    """Build the shared Cactus storage path for a downloaded course file."""

    directorio = raiz / f"Ciclo_{sanitize_filename(info['nivel'])}"
    directorio.mkdir(parents=True, exist_ok=True)
    return directorio / f"{info['nombre_curso']}.{extension}"
