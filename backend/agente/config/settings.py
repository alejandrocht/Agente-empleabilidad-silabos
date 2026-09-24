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

_MODELO_ANALISTA_POR_PROVEEDOR = {
    "ollama": ("NORMALIZADOR_CURRICULAR_OLLAMA_MODEL", "qwen3.8:27b"),
    "openai": ("NORMALIZADOR_CURRICULAR_OPENAI_MODEL", "gpt-5.6-luna"),
}
_URL_OLLAMA_DEFAULT = "http://localhost:11434/v1"


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
    valor = texto(clave, str(default))
    try:
        return int(valor)
    except ValueError as exc:
        raise ValueError(f"{clave} debe ser un entero; se recibió {valor!r}") from exc


def decimal(clave: str, default: float) -> float:
    """Lee un número decimal de configuración."""
    valor = texto(clave, str(default))
    try:
        return float(valor)
    except ValueError as exc:
        raise ValueError(f"{clave} debe ser un número; se recibió {valor!r}") from exc


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
    proveedor_llm: str
    base_url_llm: str
    modelo_analista: str
    esfuerzo_analista: str
    timeout_llm_seconds: float
    max_reintentos_llm: int
    tamano_lote_llm: int
    temperatura_llm: float
    modo_analista: str = "technical"
    ruta_catalogo_tecnico: str = ""

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

    Las selecciones operativas se leen desde ``backend/.env`` (o desde el
    proceso, que tiene precedencia). Ollama y OpenAI conservan modelos separados
    para que cambiar el proveedor no obligue a reconfigurar el modelo contrario.
    El argumento ``proceso`` existe para pruebas aisladas; producción lo omite.
    """
    entorno = _entorno_curricular(proceso)
    ruta_catalogo_tecnico = str(BASE_DIR / "catalogos" / "carrera_competencia_oficial.csv")
    timeout = _decimal_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS")
    reintentos = _entero_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES")
    tamano_lote = _entero_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE")
    temperatura = _decimal_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE")
    if timeout <= 0:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS debe ser mayor que cero")
    if reintentos < 0:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES no puede ser negativo")
    if tamano_lote < 1:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE debe ser mayor que cero")
    if not 0 <= temperatura <= 2:
        raise ValueError("NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE debe estar entre 0 y 2")
    proveedor_llm = entorno.get("NORMALIZADOR_CURRICULAR_LLM_PROVIDER", "ollama").strip().lower()
    if proveedor_llm not in {"ollama", "openai"}:
        raise ValueError(
            "NORMALIZADOR_CURRICULAR_LLM_PROVIDER debe ser ollama u openai; "
            f"se recibió {proveedor_llm!r}"
        )
    variable_modelo, modelo_default = _MODELO_ANALISTA_POR_PROVEEDOR[proveedor_llm]
    modelo_analista = entorno.get(variable_modelo, modelo_default).strip()
    if not modelo_analista:
        raise ValueError(f"{variable_modelo} no puede estar vacío")
    base_url_llm = (
        entorno.get("NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL", _URL_OLLAMA_DEFAULT).strip()
        if proveedor_llm == "ollama"
        else ""
    )
    if proveedor_llm == "ollama" and not base_url_llm:
        raise ValueError("NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL no puede estar vacía")
    return ConfiguracionNormalizadorCurricular(
        usar_llm=_booleano_curricular(entorno, "NORMALIZADOR_CURRICULAR_LLM"),
        modo_analista="technical",
        ruta_catalogo_tecnico=ruta_catalogo_tecnico,
        proveedor_llm=proveedor_llm,
        base_url_llm=base_url_llm,
        modelo_analista=modelo_analista,
        esfuerzo_analista=_esfuerzo_curricular(
            entorno, "NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT"
        ),
        timeout_llm_seconds=timeout,
        max_reintentos_llm=reintentos,
        tamano_lote_llm=tamano_lote,
        temperatura_llm=temperatura,
    )
