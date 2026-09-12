"""Validación pura de decisiones curriculares de aprobación."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agente.normalizador.silabos.clasificacion import estado_clasificacion
from agente.normalizador.silabos.paquetes import PACKAGE_ID_FIELD, identidad_fuente_chh
from agente.normalizador.silabos.persistencia_aprobaciones import _texto

DECISIONES_VALIDAS = {"ADD", "KEEP_PENDING", "DISCARD"}


class DecisionCurricularInvalida(ValueError):
    """La solicitud no cumple el contrato de decisiones curriculares."""


class AprobacionNoPermitida(RuntimeError):
    """La ejecución no está en un estado seguro para recibir decisiones."""


class RevisionCurricularInvalida(DecisionCurricularInvalida):
    """La UI está intentando decidir sobre una cola que ya cambió."""


def _expandir_decisiones_de_paquete(
    solicitudes: list[dict[str, str]],
    pendientes: list[dict[str, object]],
    paquetes: Sequence[Mapping[str, object]] | None = None,
) -> list[dict[str, str]]:
    """Expand one package decision to all actionable rows in that package.

    Triple-scoped packages expose only their own rows, so a package decision
    promotes exactly the CHH triple it represents.
    """

    by_id = {_texto(row.get("id_pendiente")): row for row in pendientes}
    package_rows: dict[str, list[dict[str, object]]] = {}
    for row in pendientes:
        package_rows.setdefault(_texto(row.get(PACKAGE_ID_FIELD)), []).append(row)
    filas_por_paquete: dict[str, set[str]] = {}
    for paquete in paquetes or ():
        if not isinstance(paquete, Mapping):
            continue
        paquete_id = _texto(paquete.get(PACKAGE_ID_FIELD) or paquete.get("package_id"))
        if not paquete_id:
            continue
        ids = {
            _texto(fila.get("id_pendiente"))
            for fila in (paquete.get("filas") or [])
            if isinstance(fila, Mapping)
        } | {_texto(item) for item in (paquete.get("id_pendientes") or [])}
        ids.discard("")
        if ids:
            filas_por_paquete[paquete_id] = ids
    expanded: list[dict[str, str]] = []
    seen: set[str] = set()
    for solicitud in solicitudes:
        package_id = _texto(solicitud.get(PACKAGE_ID_FIELD))
        if package_id:
            ids_paquete = filas_por_paquete.get(package_id)
            rows = (
                [row for row in pendientes if _texto(row.get("id_pendiente")) in ids_paquete]
                if ids_paquete
                else package_rows.get(package_id)
            )
            if not rows:
                raise DecisionCurricularInvalida(
                    f"No existe el paquete {package_id!r} en esta ejecución."
                )
            for row in rows:
                if (
                    estado_clasificacion(row).auto_deduplicated
                    and solicitud["decision"] != "DISCARD"
                ):
                    continue
                id_pendiente = _texto(row.get("id_pendiente"))
                if id_pendiente and id_pendiente not in seen:
                    item_expandido = {
                        "id_pendiente": id_pendiente,
                        "decision": solicitud["decision"],
                        PACKAGE_ID_FIELD: package_id,
                    }
                    if solicitud["decision"] == "DISCARD":
                        item_expandido["reason"] = _texto(solicitud.get("reason"))
                    expanded.append(item_expandido)
                    seen.add(id_pendiente)
            continue
        id_pendiente = _texto(solicitud.get("id_pendiente"))
        if id_pendiente in by_id and id_pendiente not in seen:
            item_expandido = {"id_pendiente": id_pendiente, "decision": solicitud["decision"]}
            if solicitud["decision"] == "DISCARD":
                item_expandido["reason"] = _texto(solicitud.get("reason"))
            expanded.append(item_expandido)
            seen.add(id_pendiente)
    if not expanded:
        raise DecisionCurricularInvalida("La solicitud no contiene filas o paquetes accionables.")
    return expanded


def _validar_solicitudes(decisiones: list[dict[str, object]]) -> list[dict[str, str]]:
    if not isinstance(decisiones, list) or not decisiones:
        raise DecisionCurricularInvalida("Debe enviar al menos una decisión curricular.")
    resultado: list[dict[str, str]] = []
    ids: set[str] = set()
    for item in decisiones:
        if not isinstance(item, dict):
            raise DecisionCurricularInvalida("Cada decisión debe ser un objeto.")
        id_pendiente = _texto(item.get("id_pendiente"))
        id_paquete = _texto(
            item.get(PACKAGE_ID_FIELD) or item.get("package_id") or item.get("id_paquete")
        )
        decision = _texto(item.get("decision")).upper()
        reason = _texto(item.get("reason"))[:600]
        if (
            (not id_pendiente and not id_paquete)
            or len(id_pendiente) > 200
            or len(id_paquete) > 200
        ):
            raise DecisionCurricularInvalida(
                "Cada decisión necesita id_pendiente o id_paquete_chh válido."
            )
        if decision not in DECISIONES_VALIDAS:
            raise DecisionCurricularInvalida(
                f"Decisión inválida para {id_pendiente!r}; use ADD, KEEP_PENDING o DISCARD."
            )
        if decision == "DISCARD" and (not id_paquete or id_pendiente):
            raise DecisionCurricularInvalida(
                "DISCARD requiere únicamente id_paquete_chh para descartar el paquete completo."
            )
        if decision == "DISCARD" and not reason:
            raise DecisionCurricularInvalida("DISCARD requiere un motivo de descarte.")
        unique_id = id_pendiente or id_paquete
        if unique_id in ids:
            raise DecisionCurricularInvalida("La solicitud contiene ids duplicados.")
        ids.add(unique_id)
        resultado.append(
            {
                "id_pendiente": id_pendiente,
                PACKAGE_ID_FIELD: id_paquete,
                "decision": decision,
                "reason": reason,
            }
        )
    return resultado


def _validar_precondiciones_promocion(
    solicitudes: Sequence[Mapping[str, str]],
    pendientes: Mapping[str, Mapping[str, object]],
    archivos: Mapping[str, Sequence[Mapping[str, object]]],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]],
) -> None:
    """Fail closed before an ADD can mutate a canonical candidate package."""

    candidatos_add: list[tuple[str, dict[str, str]]] = []
    for solicitud in solicitudes:
        if solicitud["decision"] != "ADD":
            continue
        fila = pendientes[solicitud["id_pendiente"]]
        try:
            candidatos_add.append((_texto(fila.get("tipo")).lower(), identidad_fuente_chh(fila)))
        except ValueError as exc:
            raise DecisionCurricularInvalida(str(exc)) from exc

    def misma_fuente(item: Mapping[str, object], identidad: Mapping[str, str]) -> bool:
        return all(
            _texto(item.get(campo)) == identidad[campo]
            for campo in (
                "id_ejecucion",
                "carrera",
                "periodo",
                "id_curso",
                "id_silabo",
                "id_habilidad_fuente",
            )
        )

    def existe_canonico(tipo: str, identidad: Mapping[str, str]) -> bool:
        archivo, columna_fuente, columna_canonica, catalogo, columna_catalogo = {
            "competencia": (
                "competencias_fuente.jsonl",
                "id_competencia_fuente",
                "id_competencia_canonica",
                "catalogo_competencias.csv",
                "id_competencia",
            ),
            "habilidad": (
                "habilidades_fuente.jsonl",
                "id_habilidad_fuente",
                "id_habilidad_canonica",
                "catalogo_logros.csv",
                "id_logro",
            ),
        }[tipo]
        ids_catalogo = {
            _texto(fila.get(columna_catalogo))
            for fila in archivos[catalogo]
            if _texto(fila.get(columna_catalogo))
        }
        id_relacion_fuente = _texto(identidad.get("id_cob_curricular"))
        if id_relacion_fuente:
            columna_relacion = columna_canonica
            if any(
                _texto(relacion.get("id_cob_curricular")) == id_relacion_fuente
                and _texto(relacion.get(columna_relacion)) in ids_catalogo
                for relacion in fuentes.get("cobertura_curricular_fuente.jsonl", ())
            ):
                return True
        if any(
            misma_fuente(fila, identidad)
            and _texto(fila.get(columna_fuente))
            and _texto(fila.get(columna_canonica)) in ids_catalogo
            for fila in fuentes[archivo]
        ):
            return True
        return any(
            candidato_tipo == tipo and candidato_identidad == dict(identidad)
            for candidato_tipo, candidato_identidad in candidatos_add
        )

    for tipo, identidad in candidatos_add:
        if tipo == "habilidad" and not existe_canonico("competencia", identidad):
            raise DecisionCurricularInvalida(
                "No se puede promover una habilidad sin una competencia canónica resoluble "
                "en la misma fuente."
            )
        if tipo == "herramienta" and (
            not existe_canonico("competencia", identidad)
            or not existe_canonico("habilidad", identidad)
        ):
            raise DecisionCurricularInvalida(
                "No se puede promover una herramienta sin competencia y habilidad canónicas "
                "resolubles en el mismo paquete."
            )
