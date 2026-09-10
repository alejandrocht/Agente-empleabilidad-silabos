"""Configuración centralizada del backend.

El archivo ``.env`` se lee desde la raíz de ``backend``. ``setdefault`` conserva cualquier
valor que el proceso haya recibido desde el sistema o desde el entorno de despliegue.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

# Desde ``agente/config`` se suben dos niveles hasta la raíz de ``backend``.
BASE_DIR = Path(__file__).resolve().parents[2]


def cargar_entorno() -> None:
    """Carga las variables definidas en ``backend/.env`` cuando el archivo existe."""
    ruta_env = BASE_DIR / ".env"
    if not ruta_env.exists():
        return

    # Se ignoran comentarios, líneas vacías y entradas mal formadas.
    for linea in ruta_env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


# La carga ocurre al importar settings para que LangGraph, la API y la consola compartan fuente.
cargar_entorno()


def texto(clave: str, default: str = "") -> str:
    """Lee texto del entorno ya cargado y elimina espacios externos."""
    return os.getenv(clave, default).strip()


def entero(clave: str, default: int) -> int:
    """Lee un entero de configuración."""
    return int(texto(clave, str(default)))


def decimal(clave: str, default: float) -> float:
    """Lee un número decimal de configuración."""
    return float(texto(clave, str(default)))


def booleano(clave: str, default: bool = False) -> bool:
    """Lee un booleano estricto y rechaza valores ambiguos."""
    valor = texto(clave, str(default)).lower()
    if valor in {"1", "true", "yes", "on", "si", "sí"}:
        return True
    if valor in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"{clave} debe ser uno de true/false, 1/0, yes/no u on/off; se recibió {valor!r}"
    )


@dataclass(frozen=True, slots=True)
class ConfiguracionNormalizadorCurricular:
    """Snapshot inmutable, sin secretos, para una ejecución curricular."""

    usar_llm: bool
    modelo_analista: str
    esfuerzo_analista: str
    timeout_llm_seconds: float
    max_reintentos_llm: int
    tamano_lote_llm: int
    temperatura_llm: float
    embeddings_habilitados: bool
    embedding_carreras: str
    modelo_embedding: str
    umbral_similitud_embedding: float
    limite_embedding_competencia: int
    limite_embedding_habilidad: int
    limite_embedding_herramienta: int
    limite_lexical_competencia: int
    limite_lexical_habilidad: int
    limite_lexical_herramienta: int
    limite_ejemplos_contexto: int

    def a_dict(self) -> dict[str, object]:
        """Expone el snapshot operativo que acompaña a una ejecución."""
        return asdict(self)

    def modelo_para_rol(self, rol: str) -> str:
        """Resuelve los roles LLM propios del flujo curricular."""
        return {
            "analista_curricular": self.modelo_analista,
        }[rol]

    def esfuerzo_para_rol(self, rol: str) -> str:
        """Resuelve el effort explícito para el rol curricular indicado."""
        return {
            "analista_curricular": self.esfuerzo_analista,
        }[rol]

    def limites_embedding(self) -> dict[str, int]:
        """Devuelve los límites efectivos del recuperador semántico."""
        return {
            "competencia": self.limite_embedding_competencia,
            "habilidad": self.limite_embedding_habilidad,
            "herramienta": self.limite_embedding_herramienta,
        }

    def limites_lexicales(self) -> dict[str, int]:
        """Devuelve los límites efectivos del fallback léxico para el prompt."""
        return {
            "competencia": self.limite_lexical_competencia,
            "habilidad": self.limite_lexical_habilidad,
            "herramienta": self.limite_lexical_herramienta,
        }


def _leer_archivo_entorno(ruta: Path) -> dict[str, str]:
    """Lee un .env sin mutar el proceso; el proceso tiene precedencia explícita."""
    if not ruta.exists():
        return {}
    valores: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def _entorno_curricular(proceso: Mapping[str, str] | None = None) -> dict[str, str]:
    """Combina backend/.env y proceso con el proceso como fuente dominante."""
    valores = _leer_archivo_entorno(BASE_DIR / ".env")
    valores.update(proceso if proceso is not None else os.environ)
    return valores


def _requerir_texto(entorno: Mapping[str, str], clave: str, *, permitir_vacio: bool = False) -> str:
    valor = entorno.get(clave, "").strip()
    if valor or permitir_vacio:
        return valor
    raise ValueError(f"{clave} debe definirse en backend/.env o en el entorno del proceso")


def _booleano_curricular(entorno: Mapping[str, str], clave: str) -> bool:
    valor = _requerir_texto(entorno, clave).lower()
    if valor in {"1", "true", "yes", "on", "si", "sí"}:
        return True
    if valor in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"{clave} debe ser uno de true/false, 1/0, yes/no u on/off; se recibió {valor!r}"
    )


def _entero_curricular(entorno: Mapping[str, str], clave: str) -> int:
    valor = _requerir_texto(entorno, clave)
    try:
        return int(valor)
    except ValueError as exc:
        raise ValueError(f"{clave} debe ser un entero; se recibió {valor!r}") from exc


def _decimal_curricular(entorno: Mapping[str, str], clave: str) -> float:
    valor = _requerir_texto(entorno, clave)
    try:
        return float(valor)
    except ValueError as exc:
        raise ValueError(f"{clave} debe ser un número; se recibió {valor!r}") from exc


def _limite_candidatos_curricular(entorno: Mapping[str, str], clave: str) -> int:
    valor = _entero_curricular(entorno, clave)
    if valor < 0:
        raise ValueError(f"{clave} no puede ser negativo")
    return valor


def _esfuerzo_curricular(entorno: Mapping[str, str], clave: str) -> str:
    valor = _requerir_texto(entorno, clave).lower()
    permitidos = {"low", "medium", "high"}
    if valor not in permitidos:
        raise ValueError(f"{clave} debe ser uno de {sorted(permitidos)}; se recibió {valor!r}")
    return valor


def configuracion_normalizador_curricular(
    proceso: Mapping[str, str] | None = None,
) -> ConfiguracionNormalizadorCurricular:
    """Carga una vez las selecciones curriculares de .env y proceso.

    No hay fallbacks operacionales en Python: cada selección debe estar en
    ``backend/.env`` (o en el proceso, que tiene precedencia). El argumento
    ``proceso`` existe para pruebas aisladas; la entrada de producción lo omite.
    """
    entorno = _entorno_curricular(proceso)
    timeout = _decimal_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS")
    reintentos = _entero_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES")
    tamano_lote = _entero_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE")
    temperatura = _decimal_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE")
    umbral_similitud = _decimal_curricular(
        entorno, "NORMALIZADOR_CURRICULAR_EMBEDDING_MIN_SIMILARITY"
    )
    if timeout <= 0:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS debe ser mayor que cero")
    if reintentos < 0:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES no puede ser negativo")
    if tamano_lote < 1:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE debe ser mayor que cero")
    if not 0 <= temperatura <= 2:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE debe estar entre 0 y 2")
    if not 0 <= umbral_similitud < 1:
        raise ValueError(
            "NORMALIZADOR_CURRICULAR_EMBEDDING_MIN_SIMILARITY debe estar entre 0 y menor que 1"
        )
    return ConfiguracionNormalizadorCurricular(
        usar_llm=_booleano_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM"),
        modelo_analista=_requerir_texto(entorno, "NORMALIZADOR_CURRICULAR_ANALYST_MODEL"),
        esfuerzo_analista=_esfuerzo_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT"
        ),
        timeout_llm_seconds=timeout,
        max_reintentos_llm=reintentos,
        tamano_lote_llm=tamano_lote,
        temperatura_llm=temperatura,
        embeddings_habilitados=_booleano_curricular(entorno, "NORMALIZADOR_CURRICULAR_EMBEDDINGS"),
        embedding_carreras=_requerir_texto(
            entorno, "NORMALIZADOR_CURRICULAR_EMBEDDING_CARRERAS", permitir_vacio=True
        ),
        modelo_embedding=_requerir_texto(entorno, "NORMALIZADOR_CURRICULAR_EMBEDDING_MODEL"),
        umbral_similitud_embedding=umbral_similitud,
        limite_embedding_competencia=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_EMBEDDING_COMPETENCIA_CANDIDATES"
        ),
        limite_embedding_habilidad=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_EMBEDDING_HABILIDAD_CANDIDATES"
        ),
        limite_embedding_herramienta=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_EMBEDDING_HERRAMIENTA_CANDIDATES"
        ),
        limite_lexical_competencia=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_LEXICAL_COMPETENCIA_CANDIDATES"
        ),
        limite_lexical_habilidad=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_LEXICAL_HABILIDAD_CANDIDATES"
        ),
        limite_lexical_herramienta=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_LEXICAL_HERRAMIENTA_CANDIDATES"
        ),
        limite_ejemplos_contexto=_limite_candidatos_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_CONTEXT_EXAMPLE_LIMIT"
        ),
    )
