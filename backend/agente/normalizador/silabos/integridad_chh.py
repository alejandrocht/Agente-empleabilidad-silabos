"""Validaciones deterministas del grafo curricular Competencia-Habilidad-Herramienta.

El LLM propone conceptos y relaciones; este módulo decide si una salida puede
considerarse una cadena CHH publicable. No intenta inferir equivalencias ni
corregir relaciones: cuando falta un extremo, devuelve un hallazgo accionable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from agente.normalizador.modelos import Hallazgo

RelacionCHH = tuple[str, str, str, str, str]

_COMPETENCIAS = "catalogo_competencias.csv"
_HABILIDADES = "catalogo_habilidades.csv"
_HERRAMIENTAS = "catalogo_herramientas.csv"


def validar_integridad_chh(
    filas_por_archivo: Mapping[str, Sequence[Mapping[str, object]]],
    relaciones_canonicas: Iterable[RelacionCHH],
) -> tuple[Hallazgo, ...]:
    """Valida que cada nodo publicado tenga una cadena CHH verificable.

    Una herramienta puede ser opcional en una relación, pero una herramienta
    que sí aparece en su catálogo debe participar en al menos una relación con
    una competencia y una habilidad. Las habilidades publicadas no pueden
    quedar huérfanas. La competencia-only se valida en el paquete fuente,
    porque el catálogo global no conserva suficiente alcance para decidir si
    otra habilidad pertenece a esa misma fuente.
    """

    ids_competencias = _ids(filas_por_archivo.get(_COMPETENCIAS, ()), "id_competencia")
    ids_habilidades = _ids(filas_por_archivo.get(_HABILIDADES, ()), "id_habilidad")
    ids_herramientas = _ids(filas_por_archivo.get(_HERRAMIENTAS, ()), "id_herramienta")

    hallazgos: list[Hallazgo] = []
    competencias_por_habilidad: dict[str, set[str]] = {
        identificador: set() for identificador in ids_habilidades
    }
    relaciones_por_herramienta: dict[str, set[tuple[str, str]]] = {
        identificador: set() for identificador in ids_herramientas
    }

    for indice, relacion in enumerate(relaciones_canonicas, start=1):
        valores = _relacion(relacion)
        if valores is None:
            hallazgos.append(
                Hallazgo(
                    codigo="RELACION_CHH_INCOMPLETA",
                    severidad="error",
                    mensaje=(
                        "Cada relación curricular debe conservar curso, sílabo, "
                        "competencia y habilidad."
                    ),
                    hoja="cobertura_curricular.csv",
                    fila=indice,
                )
            )
            continue

        id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta = valores
        if not id_curso or not id_silabo or not id_competencia or not id_habilidad:
            hallazgos.append(
                Hallazgo(
                    codigo="RELACION_CHH_INCOMPLETA",
                    severidad="error",
                    mensaje=(
                        "Una relación CHH no puede omitir el origen, la competencia o la habilidad."
                    ),
                    hoja="cobertura_curricular.csv",
                    fila=indice,
                    detalle="|".join(valores),
                )
            )
            continue

        referencias_invalidas = []
        if id_competencia not in ids_competencias:
            referencias_invalidas.append(f"competencia={id_competencia}")
        if id_habilidad not in ids_habilidades:
            referencias_invalidas.append(f"habilidad={id_habilidad}")
        if id_herramienta and id_herramienta not in ids_herramientas:
            referencias_invalidas.append(f"herramienta={id_herramienta}")
        if referencias_invalidas:
            hallazgos.append(
                Hallazgo(
                    codigo="RELACION_CHH_REFERENCIA_INVALIDA",
                    severidad="error",
                    mensaje="Una relación CHH apunta a un nodo que no existe en el catálogo.",
                    hoja="cobertura_curricular.csv",
                    fila=indice,
                    detalle="; ".join(referencias_invalidas),
                )
            )
            continue

        competencias_por_habilidad[id_habilidad].add(id_competencia)
        if id_herramienta:
            relaciones_por_herramienta[id_herramienta].add((id_competencia, id_habilidad))

    # Competencies are mandatory package roots, while skills and tools are
    # optional package members.  Package-local validation owns the rule that a
    # present skill/tool needs a relation; a global catalog cannot infer which
    # source package a competency belongs to and must not block competency-only
    # packages because another package happens to contain a skill.

    for identificador in sorted(ids_habilidades):
        if competencias_por_habilidad[identificador]:
            continue
        hallazgos.append(
            Hallazgo(
                codigo="HABILIDAD_SIN_COMPETENCIA",
                severidad="error",
                mensaje="Toda habilidad publicada debe relacionarse con una competencia.",
                hoja=_HABILIDADES,
                campo="id_habilidad",
                detalle=identificador,
            )
        )

    for identificador in sorted(ids_herramientas):
        if relaciones_por_herramienta[identificador]:
            continue
        hallazgos.append(
            Hallazgo(
                codigo="HERRAMIENTA_SIN_CADENA_CHH",
                severidad="error",
                mensaje=(
                    "Toda herramienta publicada debe relacionarse con una habilidad "
                    "y una competencia."
                ),
                hoja=_HERRAMIENTAS,
                campo="id_herramienta",
                detalle=identificador,
            )
        )

    return tuple(hallazgos)


def _ids(
    filas: Sequence[Mapping[str, object]],
    columna: str,
) -> set[str]:
    return {_texto(fila.get(columna)) for fila in filas if _texto(fila.get(columna))}


def _relacion(valor: object) -> RelacionCHH | None:
    if not isinstance(valor, (tuple, list)) or len(valor) != 5:
        return None
    return tuple(_texto(item) for item in valor)  # type: ignore[return-value]


def _texto(valor: object) -> str:
    return str(valor or "").strip()
