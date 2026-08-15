"""Registro CHH versionado y contexto compacto para decisiones semánticas."""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from agente.config.settings import BASE_DIR, texto


def clave_concepto(valor: object) -> str:
    """Normaliza nombres para comparar conceptos sin perder signos de herramientas."""

    normalizado = unicodedata.normalize("NFKD", str(valor or "")).lower()
    normalizado = "".join(
        caracter for caracter in normalizado if not unicodedata.combining(caracter)
    )
    normalizado = re.sub(r"[^a-z0-9+#.]+", " ", normalizado)
    return re.sub(r"\s+", " ", normalizado).strip()


@dataclass(frozen=True, slots=True)
class ConceptoCHH:
    """Concepto canónico recuperable por el motor o por el contexto del LLM."""

    id: str
    nombre: str
    descripcion: str
    tipo: str = ""

    def a_dict(self) -> dict[str, str]:
        """Representación compacta para respuestas y prompts estructurados."""

        resultado = {"id": self.id, "nombre": self.nombre, "descripcion": self.descripcion}
        if self.tipo:
            resultado["tipo"] = self.tipo
        return resultado


@dataclass(frozen=True, slots=True)
class EjemploCHH:
    """Relación canónica que sirve como ejemplo de una cadena CHH válida."""

    competencia: ConceptoCHH
    habilidad: ConceptoCHH
    herramienta: ConceptoCHH | None
    tipo: str

    def a_dict(self) -> dict[str, object]:
        """Convierte la cadena en un objeto seguro para contexto JSON."""

        return {
            "competencia": self.competencia.a_dict(),
            "habilidad": self.habilidad.a_dict(),
            "herramienta": self.herramienta.a_dict() if self.herramienta else None,
            "tipo": self.tipo,
        }


class CatalogoCHH:
    """Catálogo CHH con búsqueda lexical y ejemplos atómicos limitados.

    La instancia base puede ser global, pero las decisiones curriculares deben
    trabajar con una vista acotada a la carrera o a las declaraciones del
    sílabo. ``con_competencias`` permite construir esa vista sin perder las
    habilidades y herramientas compartidas.
    """

    def __init__(
        self,
        competencias: tuple[ConceptoCHH, ...],
        habilidades: tuple[ConceptoCHH, ...],
        herramientas: tuple[ConceptoCHH, ...],
        ejemplos_por_habilidad: dict[str, tuple[EjemploCHH, ...]],
        origen: tuple[str, ...],
        version: str,
    ) -> None:
        self.competencias = competencias
        self.habilidades = habilidades
        self.herramientas = herramientas
        self._ejemplos_por_habilidad = ejemplos_por_habilidad
        self.origen = origen
        self.version = version
        self._por_tipo = {
            "competencia": _indice_unico(competencias, "competencia"),
            "habilidad": _indice_unico(habilidades, "habilidad"),
            "herramienta": _indice_unico(herramientas, "herramienta"),
        }

    @classmethod
    def desde_directorio(cls, directorio: Path) -> CatalogoCHH:
        """Carga la unión global o, si no existe, los catálogos disponibles."""

        global_dir = directorio / "matches"
        if _tiene_catalogos_directos(directorio):
            fuentes = [
                directorio / "catalogo_competencias.csv",
                directorio / "catalogo_habilidades.csv",
                directorio / "catalogo_herramientas.csv",
            ]
        elif _tiene_catalogos_globales(global_dir):
            fuentes = [
                global_dir / "catalogo_competencias.csv",
                global_dir / "catalogo_habilidades.csv",
                global_dir / "catalogo_herramientas.csv",
            ]
        else:
            fuentes = _fuentes_de_respaldo(directorio)
        if len(fuentes) != 3:
            raise FileNotFoundError(
                "No se encontraron los tres catálogos CHH requeridos en " + str(directorio)
            )

        competencias = _leer_conceptos(fuentes[0], "competencia")
        habilidades = _leer_conceptos(fuentes[1], "habilidad")
        herramientas = _leer_conceptos(fuentes[2], "herramienta")
        por_id: dict[str, tuple[str, ConceptoCHH]] = {}
        for tipo, conceptos in (
            ("competencia", competencias),
            ("habilidad", habilidades),
            ("herramienta", herramientas),
        ):
            for concepto in conceptos:
                anterior = por_id.get(concepto.id)
                if anterior is not None:
                    tipo_anterior, _ = anterior
                    raise ValueError(
                        "ID duplicado entre catálogos: "
                        f"{concepto.id!r} aparece como {tipo} y como "
                        f"{tipo_anterior}."
                    )
                por_id[concepto.id] = (tipo, concepto)
        conceptos_por_id = {
            identificador: concepto
            for identificador, (_, concepto) in por_id.items()
        }
        ejemplos = _leer_ejemplos(directorio, conceptos_por_id)
        version = _version_catalogos(fuentes)
        return cls(
            competencias,
            habilidades,
            herramientas,
            ejemplos,
            tuple(str(fuente) for fuente in fuentes),
            version,
        )

    def buscar(self, consulta: str, limite: int = 12) -> dict[str, tuple[ConceptoCHH, ...]]:
        """Recupera candidatos por coincidencia de nombre/descripcion, no por intuición."""

        tokens = {token for token in clave_concepto(consulta).split() if len(token) > 2}
        resultado: dict[str, tuple[ConceptoCHH, ...]] = {}
        for tipo, items in self._por_tipo.items():
            ordenados: list[tuple[int, ConceptoCHH]] = []
            for clave, item in items.items():
                texto = f"{clave} {clave_concepto(item.descripcion)}"
                coincidencias = sum(token in texto.split() for token in tokens)
                if clave and clave in clave_concepto(consulta):
                    coincidencias += 4
                if coincidencias:
                    ordenados.append((coincidencias, item))
            ordenados.sort(key=lambda par: (-par[0], clave_concepto(par[1].nombre)))
            resultado[tipo] = tuple(item for _, item in ordenados[:limite])
        return resultado

    def obtener(self, tipo: str, nombre: str) -> ConceptoCHH | None:
        """Busca un concepto por nombre canónico normalizado."""

        return self._por_tipo.get(tipo, {}).get(clave_concepto(nombre))

    def ejemplos_habilidad(self, id_habilidad: str) -> tuple[EjemploCHH, ...]:
        """Expone las cadenas existentes asociadas a una habilidad."""

        return self._ejemplos_por_habilidad.get(id_habilidad, ())

    def con_competencias(
        self,
        competencias: tuple[ConceptoCHH, ...],
        *,
        origen: str,
        version: str,
    ) -> CatalogoCHH:
        """Devuelve una vista del catálogo con competencias acotadas.

        Las habilidades y herramientas permanecen disponibles porque son
        vocabularios reutilizables. Los ejemplos se filtran para no volver a
        introducir competencias fuera del alcance seleccionado.
        """

        ids_competencias = {item.id for item in competencias}
        ejemplos = {
            id_habilidad: tuple(
                ejemplo
                for ejemplo in items
                if ejemplo.competencia.id in ids_competencias
            )
            for id_habilidad, items in self._ejemplos_por_habilidad.items()
        }
        return CatalogoCHH(
            competencias,
            self.habilidades,
            self.herramientas,
            ejemplos,
            self.origen + (origen,),
            f"{self.version}:{version}",
        )

    def ejemplos(self, consulta: str, limite: int = 6) -> tuple[EjemploCHH, ...]:
        """Devuelve cadenas existentes asociadas a habilidades candidatas."""

        candidatos = self.buscar(consulta, limite=limite)
        encontrados: list[EjemploCHH] = []
        vistos: set[tuple[str, str, str]] = set()
        for habilidad in candidatos.get("habilidad", ()):
            for ejemplo in self._ejemplos_por_habilidad.get(habilidad.id, ()):
                clave = (
                    ejemplo.competencia.id,
                    ejemplo.habilidad.id,
                    ejemplo.herramienta.id if ejemplo.herramienta else "",
                )
                if clave in vistos:
                    continue
                vistos.add(clave)
                encontrados.append(ejemplo)
                if len(encontrados) >= limite:
                    return tuple(encontrados)
        return tuple(encontrados)

    def contexto_llm(self, consulta: str, limite: int = 8) -> dict[str, object]:
        """Construye un contexto acotado y explícito para el extractor residual."""

        candidatos = self.buscar(consulta, limite=limite)
        return {
            "version_catalogo": self.version,
            "regla": (
                "Usa solo conceptos candidatos con evidencia textual. La cadena debe tener "
                "Competencia y Habilidad; la Herramienta solo se incluye si aparece o es "
                "técnicamente inseparable y defendible."
            ),
            "candidatos": {
                tipo: [item.a_dict() for item in items]
                for tipo, items in candidatos.items()
            },
            "ejemplos": [ejemplo.a_dict() for ejemplo in self.ejemplos(consulta, limite)],
        }

    def resumen(self) -> dict[str, object]:
        """Entrega metadatos del catálogo sin exponer rutas internas del servidor."""

        return {
            "disponible": True,
            "version": self.version,
            "competencias": len(self.competencias),
            "habilidades": len(self.habilidades),
            "herramientas": len(self.herramientas),
            "fuentes": [Path(origen).name for origen in self.origen],
        }


def ruta_catalogos() -> Path:
    """Resuelve la ruta configurable de catálogos para desarrollo y despliegue."""

    configurada = texto("NORMALIZADOR_CATALOGOS_DIR")
    if configurada:
        return Path(configurada)
    return BASE_DIR.parent.parent / "Normalizacion CIAR" / "catalogos"


@lru_cache(maxsize=4)
def cargar_catalogo(ruta: str | None = None) -> CatalogoCHH:
    """Carga y cachea el registro; el cache evita leer los CSV en cada fila."""

    directorio = Path(ruta) if ruta else ruta_catalogos()
    return CatalogoCHH.desde_directorio(directorio)


def cargar_catalogo_carrera(
    carrera: str,
    periodo: str,
    ruta: str | None = None,
) -> CatalogoCHH | None:
    """Carga el catálogo específico de una carrera cuando ya fue construido.

    La ausencia de un catálogo específico no es un error: el normalizador
    construye una vista provisional a partir de las competencias declaradas
    por los sílabos de esa ejecución y nunca usa el catálogo global como
    sustituto silencioso.
    """

    directorio_base = Path(ruta) if ruta else ruta_catalogos()
    carrera_key = _clave_catalogo(carrera)
    periodo_key = re.sub(r"[^0-9-]", "", str(periodo or ""))
    if not carrera_key or not periodo_key:
        return None
    directorio = directorio_base / "carreras" / carrera_key / periodo_key
    if not _tiene_catalogos_directos(directorio):
        return None
    return CatalogoCHH.desde_directorio(directorio)


def _clave_catalogo(valor: object) -> str:
    """Convierte una carrera a la clave de directorio de sus catálogos."""

    valor_normalizado = unicodedata.normalize("NFKD", str(valor or ""))
    valor_normalizado = "".join(
        caracter for caracter in valor_normalizado if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^A-Za-z0-9]+", "_", valor_normalizado).strip("_").upper()


def _tiene_catalogos_directos(directorio: Path) -> bool:
    return all(
        (directorio / nombre).is_file()
        for nombre in (
            "catalogo_competencias.csv",
            "catalogo_habilidades.csv",
            "catalogo_herramientas.csv",
        )
    )


def _tiene_catalogos_globales(directorio: Path) -> bool:
    return all(
        (directorio / nombre).is_file()
        for nombre in (
            "catalogo_competencias.csv",
            "catalogo_habilidades.csv",
            "catalogo_herramientas.csv",
        )
    )


def _indice_unico(
    conceptos: tuple[ConceptoCHH, ...],
    tipo: str,
) -> dict[str, ConceptoCHH]:
    """Construye un índice sin permitir IDs ni nombres normalizados ambiguos."""

    por_nombre: dict[str, ConceptoCHH] = {}
    por_id: dict[str, ConceptoCHH] = {}
    for concepto in conceptos:
        if concepto.id:
            anterior_id = por_id.get(concepto.id)
            if anterior_id is not None:
                raise ValueError(
                    f"ID duplicado en catálogo de {tipo}: {concepto.id!r} "
                    f"({anterior_id.nombre!r} y {concepto.nombre!r})."
                )
            por_id[concepto.id] = concepto

        clave = clave_concepto(concepto.nombre)
        if not clave:
            continue
        anterior_nombre = por_nombre.get(clave)
        if anterior_nombre is not None:
            raise ValueError(
                f"Colisión de nombre normalizado en catálogo de {tipo}: "
                f"{concepto.nombre!r} y {anterior_nombre.nombre!r} "
                f"comparten la clave {clave!r}."
            )
        por_nombre[clave] = concepto
    return por_nombre


def _fuentes_de_respaldo(directorio: Path) -> list[Path]:
    empleo = directorio / "empleabilidad"
    return [
        empleo / "catalogo_empleabilidad.csv",
        empleo / "habilidades_empleabilidad.csv",
        empleo / "herramientas_empleabilidad.csv",
    ] if all(
        (empleo / nombre).is_file()
        for nombre in (
            "catalogo_empleabilidad.csv",
            "habilidades_empleabilidad.csv",
            "herramientas_empleabilidad.csv",
        )
    ) else []


def _leer_conceptos(ruta: Path, tipo: str) -> tuple[ConceptoCHH, ...]:
    """Lee una tabla de catálogo y rechaza identidad o nombres ambiguos."""

    columnas = {
        "competencia": ("id_competencia", "nombre_competencia", "descripcion_breve_competencia"),
        "habilidad": ("id_habilidad", "nombre_habilidad", "descripcion_breve"),
        "herramienta": ("id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"),
    }[tipo]
    resultado: list[ConceptoCHH] = []
    vistos_ids: dict[str, int] = {}
    vistos_nombres: dict[str, tuple[str, int]] = {}
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        for numero_fila, fila in enumerate(lector, start=2):
            identificador = str(fila.get(columnas[0], "") or "").strip()
            nombre = str(fila.get(columnas[1], "") or "").strip()
            if identificador:
                primera_fila = vistos_ids.get(identificador)
                if primera_fila is not None:
                    raise ValueError(
                        f"{ruta.name} fila {numero_fila}: ID duplicado "
                        f"{identificador!r}; ya aparece en la fila {primera_fila}."
                    )
                vistos_ids[identificador] = numero_fila
            if not identificador or not nombre:
                continue
            clave_nombre = clave_concepto(nombre)
            if clave_nombre:
                anterior = vistos_nombres.get(clave_nombre)
                if anterior is not None:
                    anterior_nombre, anterior_fila = anterior
                    raise ValueError(
                        f"{ruta.name} fila {numero_fila}: el nombre {nombre!r} "
                        f"colisiona con {anterior_nombre!r} de la fila {anterior_fila} "
                        f"tras normalización ({clave_nombre!r})."
                    )
                vistos_nombres[clave_nombre] = (nombre, numero_fila)
            resultado.append(
                ConceptoCHH(
                    id=identificador,
                    nombre=nombre,
                    descripcion=str(fila.get(columnas[2], "") or "").strip(),
                    tipo=str(fila.get("tipo_competencia", "") or "").strip(),
                )
            )
    return tuple(resultado)


def _leer_ejemplos(
    directorio: Path,
    por_id: dict[str, ConceptoCHH],
) -> dict[str, tuple[EjemploCHH, ...]]:
    """Indexa pocos ejemplos por habilidad sin cargar todas las relaciones."""

    relaciones = [directorio / "empleabilidad" / "requerimiento_laboral.csv"]
    relaciones.extend(directorio.glob("carreras/*/*/cobertura_curricular.csv"))
    acumulados: dict[str, list[EjemploCHH]] = {}
    for ruta in relaciones:
        if not ruta.is_file():
            continue
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            for fila in lector:
                competencia = por_id.get(str(fila.get("id_competencia", "") or "").strip())
                habilidad = por_id.get(str(fila.get("id_habilidad", "") or "").strip())
                if competencia is None or habilidad is None:
                    continue
                herramienta_id = str(fila.get("id_herramienta", "") or "").strip()
                herramienta = por_id.get(herramienta_id) if herramienta_id else None
                ejemplo = EjemploCHH(
                    competencia,
                    habilidad,
                    herramienta,
                    str(fila.get("tipo", "") or "").strip(),
                )
                items = acumulados.setdefault(habilidad.id, [])
                if len(items) < 3:
                    items.append(ejemplo)
    return {identificador: tuple(items) for identificador, items in acumulados.items()}


def _version_catalogos(fuentes: list[Path]) -> str:
    """Crea una versión corta basada en los bytes de las fuentes canónicas."""

    digest = hashlib.sha256()
    for fuente in fuentes:
        digest.update(fuente.name.encode("utf-8"))
        with fuente.open("rb") as archivo:
            for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
                digest.update(bloque)
    return digest.hexdigest()[:16]
