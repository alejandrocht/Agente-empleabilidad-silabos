"""Recuperación semántica local para normalizar requisitos laborales a HAB_TEC."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from agente.config.settings import BASE_DIR, decimal, entero, texto


def _normalize(value: object) -> str:
    """Normaliza carreras sin depender del módulo de identidad legado."""

    texto = unicodedata.normalize("NFKD", str(value or "").replace("_", " "))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return " ".join(texto.casefold().split())


class ErrorHabTecRetriever(RuntimeError):
    """Error operativo al cargar o consultar el índice local HAB_TEC."""


@dataclass(frozen=True, slots=True)
class HabTecMatch:
    id_habilidad: str
    carrera: str
    nombre: str
    descripcion: str
    similitud: float


@dataclass(frozen=True, slots=True)
class _Documento:
    id_habilidad: str
    carrera: str
    nombre: str
    descripcion: str
    vector: tuple[float, ...]


class HabTecRetriever:
    """Carga una vez los vectores y consulta Ollama solo para el texto entrante."""

    def __init__(
        self,
        documentos: tuple[_Documento, ...],
        *,
        endpoint: str,
        modelo: str,
        similitud_minima: float,
        limite: int,
        id_catalogo: str = "",
        sha256_catalogo: str = "",
    ) -> None:
        if not documentos:
            raise ErrorHabTecRetriever("El índice HAB_TEC no contiene documentos.")
        self.documentos = documentos
        self.endpoint = endpoint
        self.modelo = modelo
        self.similitud_minima = similitud_minima
        self.limite = limite
        self.id_catalogo = id_catalogo
        self.sha256_catalogo = sha256_catalogo
        self._por_carrera: dict[str, tuple[_Documento, ...]] = {}
        for documento in documentos:
            clave = _normalize(documento.carrera)
            self._por_carrera.setdefault(clave, ())
            self._por_carrera[clave] += (documento,)

    def buscar(self, texto_consulta: str, carrera: str = "") -> tuple[HabTecMatch, ...]:
        """Devuelve los candidatos por carrera y similitud coseno."""

        consulta = " ".join(
            parte for parte in (f"Carrera: {carrera}" if carrera else "", texto_consulta) if parte
        ).strip()
        if not consulta:
            return ()
        # El catálogo es contextual por carrera. Sin ese contexto no debemos
        # escoger una habilidad de otra carrera por mera cercanía semántica.
        if not carrera:
            return ()
        candidatos = self._candidatos_por_carrera(carrera)
        if not candidatos:
            return ()
        vector = self._embedding(consulta)
        puntuados: list[tuple[float, _Documento]] = []
        for documento in candidatos:
            puntuacion = _coseno(vector, documento.vector)
            if puntuacion >= self.similitud_minima:
                puntuados.append((puntuacion, documento))
        puntuados.sort(key=lambda item: (-item[0], item[1].id_habilidad, item[1].carrera))
        return tuple(
            HabTecMatch(
                id_habilidad=documento.id_habilidad,
                carrera=documento.carrera,
                nombre=documento.nombre,
                descripcion=documento.descripcion,
                similitud=puntuacion,
            )
            for puntuacion, documento in puntuados[: self.limite]
        )

    def _candidatos_por_carrera(self, carrera: str) -> tuple[_Documento, ...]:
        """Admite una fuente que declare más de una carrera en la misma celda."""

        fragmentos = re.split(r"\s*(?:,|;|/|\|)\s*", carrera)
        claves = tuple(
            dict.fromkeys(_normalize(fragmento) for fragmento in fragmentos if fragmento)
        )
        candidatos: list[_Documento] = []
        vistos: set[tuple[str, str, str]] = set()
        for clave in claves:
            for documento in self._por_carrera.get(clave, ()):
                identidad = (documento.id_habilidad, documento.carrera, documento.nombre)
                if identidad not in vistos:
                    vistos.add(identidad)
                    candidatos.append(documento)
        return tuple(candidatos)

    def _embedding(self, texto_consulta: str) -> tuple[float, ...]:
        solicitud = urllib.request.Request(
            self.endpoint,
            data=json.dumps({"model": self.modelo, "input": [texto_consulta]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(solicitud, timeout=120) as respuesta:
                datos = json.loads(respuesta.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise ErrorHabTecRetriever(
                "No se pudo consultar Ollama para normalizar HAB_TEC."
            ) from exc
        vectores = datos.get("embeddings") if isinstance(datos, dict) else None
        if not isinstance(vectores, list) or len(vectores) != 1:
            raise ErrorHabTecRetriever("Ollama devolvió un embedding de consulta inválido.")
        vector = vectores[0]
        if not isinstance(vector, list):
            raise ErrorHabTecRetriever("Ollama devolvió un embedding de consulta inválido.")
        try:
            resultado = tuple(float(valor) for valor in vector)
        except (TypeError, ValueError) as exc:
            raise ErrorHabTecRetriever(
                "Ollama devolvió un embedding de consulta inválido."
            ) from exc
        if not resultado or not all(math.isfinite(valor) for valor in resultado):
            raise ErrorHabTecRetriever("Ollama devolvió un embedding de consulta inválido.")
        return resultado


def cargar_retriever_hab_tec(
    id_catalogo: str = "", *, limite: int | None = None
) -> HabTecRetriever | None:
    """Carga el índice vectorial vigente; devuelve None si aún no existe."""

    base = Path(texto("NORMALIZADOR_HAB_TEC_DIR") or BASE_DIR / ".normalizador" / "hab_tec")
    if id_catalogo and not re.fullmatch(r"HABTEC_[0-9a-f]{16}", id_catalogo):
        raise ErrorHabTecRetriever("Identificador de catálogo HAB_TEC inválido.")
    candidatos: list[tuple[str, Path]] = []
    for ruta in base.glob(id_catalogo or "HABTEC_*"):
        try:
            estado = json.loads((ruta / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(estado, dict) and estado.get("estado") == "vectorizado":
            candidatos.append((str(estado.get("creado_en") or ""), ruta))
    candidatos.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    if not candidatos:
        if id_catalogo:
            raise ErrorHabTecRetriever("El catálogo HAB_TEC de la ejecución no está disponible.")
        return None
    directorio = candidatos[0][1]
    indice = directorio / "indice"
    try:
        manifest = json.loads((indice / "manifest.json").read_text(encoding="utf-8"))
        dimension = int(manifest["dimension"])
        cantidad = int(manifest["registros"])
        modelo = str(manifest["modelo_embedding"])
        if dimension <= 0 or cantidad <= 0 or not modelo:
            raise ErrorHabTecRetriever("El índice HAB_TEC no contiene dimensiones válidas.")
        fuente = (directorio / "catalogo_normalizado.jsonl").read_bytes()
        sha256_catalogo = hashlib.sha256(fuente).hexdigest()
        if sha256_catalogo != manifest["sha256_catalogo"]:
            raise ErrorHabTecRetriever("El índice no corresponde al catálogo HAB_TEC vigente.")
        registros = [
            json.loads(linea) for linea in fuente.decode("utf-8").splitlines() if linea.strip()
        ]
        metadatos = [
            json.loads(linea)
            for linea in (indice / "metadatos.jsonl").read_text(encoding="utf-8").splitlines()
            if linea.strip()
        ]
        datos_vectores = (indice / "vectores.f32").read_bytes()
        esperado = cantidad * dimension * 4
        if (
            len(registros) != cantidad
            or len(metadatos) != cantidad
            or len(datos_vectores) != esperado
        ):
            raise ErrorHabTecRetriever("El índice HAB_TEC está incompleto o inconsistente.")
        documentos: list[_Documento] = []
        asociaciones: set[tuple[str, str]] = set()
        for posicion, metadata in enumerate(metadatos):
            campos = ("id", "carrera", "nombre", "descripcion")
            if any(
                not metadata.get(campo) or metadata.get(campo) != registros[posicion].get(campo)
                for campo in campos
            ):
                raise ErrorHabTecRetriever("Los candidatos difieren del catálogo HAB_TEC.")
            asociacion = (str(metadata["id"]), _normalize(metadata["carrera"]))
            if asociacion in asociaciones:
                raise ErrorHabTecRetriever("El catálogo HAB_TEC contiene asociaciones duplicadas.")
            asociaciones.add(asociacion)
            inicio = posicion * dimension * 4
            vector = struct.unpack(
                f"<{dimension}f", datos_vectores[inicio : inicio + dimension * 4]
            )
            if not all(math.isfinite(valor) for valor in vector) or not any(vector):
                raise ErrorHabTecRetriever("El índice HAB_TEC contiene un vector inválido.")
            documentos.append(
                _Documento(
                    id_habilidad=str(metadata.get("id") or ""),
                    carrera=str(metadata.get("carrera") or ""),
                    nombre=str(metadata.get("nombre") or ""),
                    descripcion=str(metadata.get("descripcion") or ""),
                    vector=vector,
                )
            )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error) as exc:
        raise ErrorHabTecRetriever("No se pudo cargar el índice local HAB_TEC.") from exc
    return HabTecRetriever(
        tuple(documentos),
        endpoint=texto(
            "NORMALIZADOR_HAB_TEC_EMBEDDING_ENDPOINT",
            "http://127.0.0.1:11434/api/embed",
        ),
        modelo=modelo,
        id_catalogo=directorio.name,
        sha256_catalogo=sha256_catalogo,
        similitud_minima=max(
            0.0, min(decimal("NORMALIZADOR_HAB_TEC_RETRIEVAL_MIN_SIMILARITY", 0.35), 0.999)
        ),
        limite=max(
            1,
            min(
                limite if limite is not None else entero("NORMALIZADOR_HAB_TEC_RETRIEVAL_TOP_K", 1),
                20,
            ),
        ),
    )


def _coseno(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b):
        raise ErrorHabTecRetriever(
            "La dimensión del embedding de consulta no coincide con el índice."
        )
    norma_a = math.sqrt(sum(valor * valor for valor in a))
    norma_b = math.sqrt(sum(valor * valor for valor in b))
    if norma_a == 0 or norma_b == 0:
        raise ErrorHabTecRetriever("No se puede calcular similitud con un vector nulo.")
    return sum(izquierda * derecha for izquierda, derecha in zip(a, b, strict=True)) / (
        norma_a * norma_b
    )
