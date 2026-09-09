"""Pure curricular normalization orchestration."""

from __future__ import annotations

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH, clave_concepto
from agente.normalizador.modelos import Hallazgo, ResultadoValidacionSilabos
from agente.normalizador.silabos.analista_llm import DecisionCurricular, evidencia_decision
from agente.normalizador.silabos.clasificacion import clasificar_propuestas
from agente.normalizador.silabos.paquetes import preparar_fila_paquete
from agente.normalizador.silabos.politica_curricular import (
    MOTIVO_COMPETENCIA_GENERICA,
    es_competencia_generica,
)
from agente.normalizador.silabos.resolucion_curricular import (
    ESTADO_PENDIENTE_PERFIL,
    ESTADO_REVISION_HUMANA,
    NormalizacionCurricular,
    _archivo_origen,
    _catalogo_curricular,
    _competencias_para_logro,
    _declaraciones,
    _error,
    _estado_resolucion_determinista,
    _evidencias_herramientas,
    _fila_cobertura,
    _filas_curso,
    _hash_id,
    _herramientas_explicitas,
    _herramientas_llm_nuevas,
    _id_carrera,
    _id_competencia_fuente,
    _logros,
    _pendientes_por_relacion_fuente,
    _propuesta_dict,
    _registrar_pendiente,
    _resolver_competencia,
    _resolver_habilidad_canonica,
    _source_ref,
    _texto,
    _tipo_competencia,
    _warning,
)


def normalizar_registros_curriculares(
    registros: list[dict[str, object]],
    validacion: ResultadoValidacionSilabos,
    id_ejecucion: str,
    catalogo: CatalogoCHH,
    catalogo_carrera: CatalogoCHH | None = None,
    propuestas_llm: dict[str, DecisionCurricular] | None = None,
) -> NormalizacionCurricular:
    """Compute candidates without I/O or mutation of inputs."""

    catalogo_curricular = _catalogo_curricular(
        registros,
        catalogo,
        catalogo_carrera,
    )
    propuestas_llm = propuestas_llm or {}
    hallazgos: list[Hallazgo] = []
    cuarentena: list[dict[str, object]] = []
    competencias: dict[str, dict[str, str]] = {}
    competencias_fuente: dict[str, dict[str, object]] = {}
    habilidades: dict[str, dict[str, str]] = {}
    habilidades_fuente: dict[str, dict[str, object]] = {}
    herramientas: dict[str, dict[str, str]] = {}
    herramientas_fuente: dict[str, dict[str, object]] = {}
    pendientes_curriculares: list[dict[str, object]] = []
    relaciones_fuente: set[tuple[str, str, str, str, str]] = set()
    relaciones_canonicas: set[tuple[str, str, str, str, str]] = set()
    cobertura_fuente_lineage: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    cobertura_canonica_lineage: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    carrera_ejecucion = _texto(validacion.carrera).upper()
    periodo_ejecucion = _texto(validacion.periodo)
    id_carrera = _id_carrera(carrera_ejecucion)

    for registro in registros:
        datos_objeto = registro.get("datos")
        datos = datos_objeto if isinstance(datos_objeto, dict) else {}
        id_silabo = _texto(registro.get("id_silabo"))
        id_curso = _texto(registro.get("id_curso"))
        archivo = _archivo_origen(registro)
        curso = _texto(datos.get("curso"))
        outcomes = _logros(datos)
        declaraciones = _declaraciones(datos)

        carrera_registro = _texto(registro.get("carrera")).upper()
        periodo_registro = _texto(registro.get("periodo"))
        if (carrera_registro, periodo_registro) != (
            carrera_ejecucion,
            periodo_ejecucion,
        ):
            _error(
                hallazgos,
                cuarentena,
                "REGISTRO_FUERA_DE_CARRERA",
                "El registro no pertenece a la carrera y periodo declarados para esta ejecución.",
                archivo,
                id_silabo,
                (
                    f"registro={carrera_registro}/{periodo_registro}; "
                    f"ejecucion={carrera_ejecucion}/{periodo_ejecucion}"
                ),
            )
            continue

        if not id_silabo or not id_curso:
            _error(
                hallazgos,
                cuarentena,
                "IDENTIDAD_CURRICULAR_INCOMPLETA",
                "El sílabo no tiene id_silabo o id_curso.",
                archivo,
                id_silabo,
            )
            continue

        if not outcomes:
            _error(
                hallazgos,
                cuarentena,
                "CURSO_SIN_LOGRO",
                "El sílabo no contiene un logro utilizable para construir una habilidad.",
                archivo,
                id_silabo,
            )
            continue
        if not declaraciones:
            hallazgos.append(
                Hallazgo(
                    codigo="CURSO_SIN_COMPETENCIA_DECLARADA",
                    severidad="warning",
                    mensaje=(
                        "El sílabo no contiene competencias declaradas; se intentará "
                        "normalizar cada logro usando su evidencia textual."
                    ),
                    hoja=archivo,
                    detalle=id_silabo,
                )
            )

        competencias_por_declaracion: dict[str, tuple[str, ConceptoCHH]] = {}
        for declaracion in declaraciones:
            competencia_fuente = _id_competencia_fuente(id_silabo, declaracion)
            if es_competencia_generica(declaracion["nombre"]):
                competencias_fuente[competencia_fuente] = {
                    "id_competencia_fuente": competencia_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "archivo": archivo,
                    "orden_competencia": declaracion["orden"],
                    "nombre_competencia_fuente": declaracion["nombre"],
                    "descripcion_fuente": declaracion["descripcion"],
                    "id_competencia_canonica": "",
                    "estado_resolucion": "EXCLUIDA_POLITICA",
                    "motivo": MOTIVO_COMPETENCIA_GENERICA,
                }
                hallazgos.append(
                    Hallazgo(
                        codigo=MOTIVO_COMPETENCIA_GENERICA,
                        severidad="warning",
                        mensaje="La competencia transversal se excluyó del catálogo disciplinar.",
                        hoja=archivo,
                        campo="competencia",
                        detalle=declaracion["nombre"],
                    )
                )
                continue
            resolucion_competencia = _resolver_competencia(catalogo_curricular, declaracion)
            competencia = resolucion_competencia.concepto
            assert competencia is not None
            competencias_por_declaracion[competencia_fuente] = (competencia_fuente, competencia)
            competencias_fuente[competencia_fuente] = {
                "id_competencia_fuente": competencia_fuente,
                "id_curso": id_curso,
                "id_silabo": id_silabo,
                "archivo": archivo,
                "orden_competencia": declaracion["orden"],
                "nombre_competencia_fuente": declaracion["nombre"],
                "descripcion_fuente": declaracion["descripcion"],
                "id_competencia_canonica": competencia.id,
                "estado_resolucion": "DECLARADA",
                "metodo_resolucion": resolucion_competencia.metodo,
                "puntaje_resolucion": resolucion_competencia.puntaje,
                "puntaje_segundo": resolucion_competencia.puntaje_segundo,
            }
            competencias[competencia.id] = {
                "id_competencia": competencia.id,
                "nombre_competencia": competencia.nombre,
                "descripcion_breve_competencia": competencia.descripcion,
                "tipo_competencia": competencia.tipo,
            }

        for indice_logro, logro in enumerate(outcomes, start=1):
            descripcion = _texto(logro.get("descripcion"))
            orden_logro = _texto(logro.get("orden")) or str(indice_logro)
            id_logro = _texto(logro.get("id_logro")) or _hash_id(
                "LOGRO_SRC",
                id_silabo,
                orden_logro,
                descripcion,
            )
            if not descripcion:
                _error(
                    hallazgos,
                    cuarentena,
                    "LOGRO_SIN_HABILIDAD",
                    "El logro específico no tiene descripción observable.",
                    archivo,
                    id_silabo,
                    orden_logro,
                )
                continue

            seleccionadas = _competencias_para_logro(
                logro,
                declaraciones,
                datos,
                descripcion,
                catalogo_curricular,
            )
            competencias_fuente_logro: list[str] = []
            for declaracion in seleccionadas:
                if es_competencia_generica(declaracion["nombre"]):
                    continue
                resolucion_competencia = _resolver_competencia(catalogo_curricular, declaracion)
                competencia = resolucion_competencia.concepto
                assert competencia is not None
                competencia_fuente = _id_competencia_fuente(id_silabo, declaracion)
                fuente_resuelta = competencias_por_declaracion.get(competencia_fuente)
                if fuente_resuelta is None:
                    competencias_fuente[competencia_fuente] = {
                        "id_competencia_fuente": competencia_fuente,
                        "id_curso": id_curso,
                        "id_silabo": id_silabo,
                        "archivo": archivo,
                        "orden_competencia": declaracion["orden"],
                        "nombre_competencia_fuente": declaracion["nombre"],
                        "descripcion_fuente": declaracion["descripcion"],
                        "id_competencia_canonica": competencia.id,
                        "estado_resolucion": "RESUELTA_POR_EVIDENCIA",
                        "metodo_resolucion": _texto(declaracion.get("_metodo_resolucion"))
                        or resolucion_competencia.metodo,
                        "puntaje_resolucion": declaracion.get("_puntaje_resolucion"),
                        "puntaje_segundo": declaracion.get("_puntaje_segundo"),
                    }
                else:
                    competencia_fuente = fuente_resuelta[0]
                fuente = competencias_fuente[competencia_fuente]
                fuente["metodo_vinculacion_logro"] = (
                    _texto(declaracion.get("_metodo_resolucion"))
                    or "COINCIDENCIA_TEXTUAL_DECLARADA"
                )
                fuente["puntaje_vinculacion_logro"] = declaracion.get("_puntaje_resolucion", 1.0)
                fuente["puntaje_segundo_vinculacion"] = declaracion.get("_puntaje_segundo")
                competencias_fuente_logro.append(competencia_fuente)
                competencias[competencia.id] = {
                    "id_competencia": competencia.id,
                    "nombre_competencia": competencia.nombre,
                    "descripcion_breve_competencia": competencia.descripcion,
                    "tipo_competencia": competencia.tipo,
                }

            id_habilidad_fuente = _hash_id(
                "HAB_SRC",
                id_silabo,
                orden_logro,
                descripcion,
            )
            propuesta_llm = propuestas_llm.get(id_habilidad_fuente)
            resolucion_habilidad = _resolver_habilidad_canonica(
                catalogo_curricular,
                descripcion,
            )
            habilidad_canonica = resolucion_habilidad.concepto
            estado_habilidad = _estado_resolucion_determinista(resolucion_habilidad)
            propuesta_habilidad: dict[str, object] | None = None
            habilidad_pendiente_registrada = False
            if propuesta_llm is not None:
                competencia_candidata = catalogo_curricular.obtener(
                    "competencia", propuesta_llm.competencia.nombre
                )
                if competencia_candidata is None:
                    _registrar_pendiente(
                        pendientes_curriculares,
                        tipo="competencia",
                        estado=ESTADO_PENDIENTE_PERFIL,
                        motivo="PROPUESTA_LLM_REQUIERE_DECISION_HUMANA",
                        id_curso=id_curso,
                        id_silabo=id_silabo,
                        archivo=archivo,
                        id_habilidad_fuente=id_habilidad_fuente,
                        descripcion=descripcion,
                        propuesta=_propuesta_dict(
                            propuesta_llm.competencia.nombre,
                            propuesta_llm.competencia.descripcion,
                            _tipo_competencia(propuesta_llm.competencia.tipo or "dura"),
                        ),
                        evidencia=evidencia_decision(propuesta_llm),
                        confianza=propuesta_llm.confianza,
                    )
                propuesta_habilidad = _propuesta_dict(
                    propuesta_llm.habilidad.nombre,
                    propuesta_llm.habilidad.descripcion,
                    "habilidad",
                )
                habilidad_pendiente_registrada = True
                if habilidad_canonica is not None:
                    estado_habilidad = "CANONIZADA_CON_PROPUESTA_PERFIL"
                    motivo_habilidad = "PROPUESTA_LLM_REQUIERE_DECISION_HUMANA"
                else:
                    estado_habilidad = ESTADO_PENDIENTE_PERFIL
                    motivo_habilidad = "PROPUESTA_LLM_REQUIERE_DECISION_HUMANA"
                _registrar_pendiente(
                    pendientes_curriculares,
                    tipo="habilidad",
                    estado=estado_habilidad,
                    motivo=motivo_habilidad,
                    id_curso=id_curso,
                    id_silabo=id_silabo,
                    archivo=archivo,
                    id_habilidad_fuente=id_habilidad_fuente,
                    descripcion=descripcion,
                    propuesta=propuesta_habilidad,
                    evidencia=evidencia_decision(propuesta_llm),
                    confianza=propuesta_llm.confianza,
                )
            elif habilidad_canonica is None:
                habilidad_pendiente_registrada = True
                _registrar_pendiente(
                    pendientes_curriculares,
                    tipo="habilidad",
                    estado=estado_habilidad,
                    motivo=resolucion_habilidad.metodo,
                    id_curso=id_curso,
                    id_silabo=id_silabo,
                    archivo=archivo,
                    id_habilidad_fuente=id_habilidad_fuente,
                    descripcion=descripcion,
                )
            habilidades_fuente[id_habilidad_fuente] = {
                "id_habilidad_fuente": id_habilidad_fuente,
                "id_curso": id_curso,
                "id_silabo": id_silabo,
                "archivo": archivo,
                "orden_logro": orden_logro,
                "descripcion_fuente": descripcion,
                "id_habilidad_canonica": habilidad_canonica.id if habilidad_canonica else "",
                "estado_resolucion": estado_habilidad,
                "metodo_resolucion": resolucion_habilidad.metodo,
                "puntaje_resolucion": resolucion_habilidad.puntaje,
                "puntaje_segundo": resolucion_habilidad.puntaje_segundo,
                "propuesta_perfil": propuesta_habilidad,
            }
            if habilidad_canonica is None:
                hallazgos.append(
                    Hallazgo(
                        codigo="HABILIDAD_PENDIENTE_CANONICALIZACION",
                        severidad="warning",
                        mensaje=(
                            "El logro se conserva como habilidad fuente, pero no "
                            "se encontró una habilidad canónica con evidencia suficiente."
                        ),
                        hoja=archivo,
                        detalle=f"logro {orden_logro}: {descripcion}",
                    )
                )
            elif competencias_fuente_logro and any(
                _texto(competencias_fuente[competencia_fuente].get("id_competencia_canonica"))
                for competencia_fuente in competencias_fuente_logro
            ):
                habilidades[habilidad_canonica.id] = {
                    "id_habilidad": habilidad_canonica.id,
                    "nombre_habilidad": habilidad_canonica.nombre,
                    "descripcion_breve": habilidad_canonica.descripcion,
                }
            elif not habilidad_pendiente_registrada:
                estado_habilidad = ESTADO_REVISION_HUMANA
                _registrar_pendiente(
                    pendientes_curriculares,
                    tipo="habilidad",
                    estado=ESTADO_REVISION_HUMANA,
                    motivo="HABILIDAD_SIN_COMPETENCIA_CANONICA",
                    id_curso=id_curso,
                    id_silabo=id_silabo,
                    archivo=archivo,
                    id_habilidad_fuente=id_habilidad_fuente,
                    descripcion=descripcion,
                    evidencia=[descripcion],
                )

            herramientas_detectadas = _herramientas_explicitas(
                catalogo_curricular,
                _evidencias_herramientas(datos),
            )
            herramientas_nuevas = _herramientas_llm_nuevas(
                propuesta_llm,
                {**datos, "logro_actual": descripcion},
                herramientas_detectadas,
            )
            herramientas_fuente_logro: list[tuple[str, str]] = []
            for herramienta, evidencia in herramientas_nuevas:
                pendiente = _registrar_pendiente(
                    pendientes_curriculares,
                    tipo="herramienta",
                    estado=ESTADO_PENDIENTE_PERFIL,
                    motivo="HERRAMIENTA_LLM_NO_CATALOGADA",
                    id_curso=id_curso,
                    id_silabo=id_silabo,
                    archivo=archivo,
                    id_habilidad_fuente=id_habilidad_fuente,
                    descripcion=descripcion,
                    propuesta={
                        "id": herramienta.id,
                        "nombre": herramienta.nombre,
                        "descripcion": herramienta.descripcion,
                        "tipo": herramienta.tipo,
                    },
                    evidencia=[evidencia["texto"]],
                    evidencia_provenance=evidencia,
                )
                id_herramienta_fuente = _hash_id(
                    "HERR_SRC",
                    id_silabo,
                    id_habilidad_fuente,
                    herramienta.id,
                    evidencia["texto"],
                )
                pendiente["id_herramienta_fuente"] = id_herramienta_fuente
                herramientas_fuente[id_herramienta_fuente] = {
                    "id_herramienta_fuente": id_herramienta_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "id_habilidad_fuente": id_habilidad_fuente,
                    "id_herramienta_canonica": "",
                    "nombre_herramienta": herramienta.nombre,
                    "origen_fuente": evidencia["origen"],
                    "seccion_fuente": evidencia["seccion"],
                    "texto_evidencia": evidencia["texto"],
                    "coincidencia": herramienta.nombre,
                    "estado_resolucion": ESTADO_PENDIENTE_PERFIL,
                }
                herramientas_fuente_logro.append((id_herramienta_fuente, ""))
            for deteccion in herramientas_detectadas:
                herramienta = deteccion.concepto
                id_herramienta_fuente = _hash_id(
                    "HERR_SRC",
                    id_silabo,
                    orden_logro,
                    herramienta.id,
                    deteccion.seccion,
                    deteccion.texto_evidencia,
                )
                herramientas_fuente[id_herramienta_fuente] = {
                    "id_herramienta_fuente": id_herramienta_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "id_habilidad_fuente": id_habilidad_fuente,
                    "id_herramienta_canonica": herramienta.id,
                    "nombre_herramienta": herramienta.nombre,
                    "seccion_fuente": deteccion.seccion,
                    "texto_evidencia": deteccion.texto_evidencia,
                    "coincidencia": deteccion.coincidencia,
                    "estado_resolucion": "EVIDENCIA_ESTRUCTURADA",
                }
                herramientas_fuente_logro.append((id_herramienta_fuente, herramienta.id))
                if habilidad_canonica is not None and any(
                    _texto(competencias_fuente[competencia_fuente].get("id_competencia_canonica"))
                    for competencia_fuente in competencias_fuente_logro
                ):
                    herramientas[herramienta.id] = {
                        "id_herramienta": herramienta.id,
                        "nombre_herramienta": herramienta.nombre,
                        "descripcion_breve_herramienta": herramienta.descripcion,
                    }

            competencias_fuente_logro = list(dict.fromkeys(competencias_fuente_logro))
            herramientas_fuente_logro = list(dict.fromkeys(herramientas_fuente_logro))
            source_ref = _source_ref(archivo, id_silabo)
            for competencia_fuente in competencias_fuente_logro:
                competencia_canonica = _texto(
                    competencias_fuente[competencia_fuente].get("id_competencia_canonica")
                )
                for herramienta_fuente, herramienta_canonica in herramientas_fuente_logro or [
                    ("", "")
                ]:
                    relacion_fuente = (
                        id_curso,
                        id_silabo,
                        competencia_fuente,
                        id_habilidad_fuente,
                        herramienta_fuente,
                    )
                    relaciones_fuente.add(relacion_fuente)
                    cobertura_fuente_lineage[relacion_fuente] = _fila_cobertura(
                        relacion_fuente,
                        "COB_CUR",
                        id_ejecucion=id_ejecucion,
                        id_logro=id_logro,
                        id_competencia_fuente=competencia_fuente,
                        id_habilidad_fuente=id_habilidad_fuente,
                        id_herramienta_fuente=herramienta_fuente,
                        id_competencia_canonica=competencia_canonica,
                        id_habilidad_canonica=(habilidad_canonica.id if habilidad_canonica else ""),
                        id_herramienta_canonica=herramienta_canonica,
                        source_ref=source_ref,
                    )
                    if not competencia_canonica or habilidad_canonica is None:
                        continue
                    if herramienta_fuente and not herramienta_canonica:
                        continue
                    relacion_canonica = (
                        id_curso,
                        id_silabo,
                        competencia_canonica,
                        habilidad_canonica.id,
                        herramienta_canonica,
                    )
                    relaciones_canonicas.add(relacion_canonica)
                    cobertura_canonica_lineage.setdefault(
                        relacion_canonica,
                        _fila_cobertura(
                            relacion_canonica,
                            "COB_CUR",
                            id_ejecucion=id_ejecucion,
                            id_logro=id_logro,
                            id_competencia_fuente=competencia_fuente,
                            id_habilidad_fuente=id_habilidad_fuente,
                            id_herramienta_fuente=herramienta_fuente,
                            id_competencia_canonica=competencia_canonica,
                            id_habilidad_canonica=habilidad_canonica.id,
                            id_herramienta_canonica=herramienta_canonica,
                            source_ref=source_ref,
                        ),
                    )

            if not competencias_fuente_logro:
                _warning(
                    hallazgos,
                    "LOGRO_SIN_COMPETENCIA",
                    (
                        "No se encontró una competencia fuente para el logro; "
                        "se conserva únicamente como evidencia pendiente."
                    ),
                    archivo,
                    id_silabo,
                    orden_logro,
                )
        if not any(
            relacion[0] == id_curso and relacion[1] == id_silabo for relacion in relaciones_fuente
        ):
            _error(
                hallazgos,
                cuarentena,
                "CURSO_SIN_COBERTURA",
                "El curso no produjo ninguna relación curricular publicable.",
                archivo,
                id_silabo,
                curso,
            )
    cobertura_canonica = [
        {
            "id_cob_curricular": _hash_id(
                "COB_CUR",
                id_curso,
                id_silabo,
                id_competencia,
                id_habilidad,
                id_herramienta,
            ),
            "id_curso": id_curso,
            "id_silabo": id_silabo,
            "id_competencia": id_competencia,
            "id_habilidad": id_habilidad,
            "id_herramienta": id_herramienta,
        }
        for id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta in sorted(
            relaciones_canonicas
        )
    ]
    cobertura = cobertura_canonica

    cursos = _filas_curso(registros, carrera_ejecucion, id_carrera, hallazgos, cuarentena)
    filas_por_archivo: dict[str, list[dict[str, str]]] = {
        "curso.csv": cursos,
        "catalogo_competencias.csv": sorted(
            competencias.values(), key=lambda fila: clave_concepto(fila["nombre_competencia"])
        ),
        "catalogo_habilidades.csv": sorted(
            habilidades.values(), key=lambda fila: clave_concepto(fila["nombre_habilidad"])
        ),
        "catalogo_herramientas.csv": sorted(
            herramientas.values(), key=lambda fila: clave_concepto(fila["nombre_herramienta"])
        ),
        "cobertura_curricular.csv": cobertura,
    }
    for fuente in (
        *competencias_fuente.values(),
        *habilidades_fuente.values(),
        *herramientas_fuente.values(),
    ):
        fuente["id_ejecucion"] = id_ejecucion
        fuente["carrera"] = carrera_ejecucion
        fuente["periodo"] = periodo_ejecucion
    pendientes_curriculares = _pendientes_por_relacion_fuente(
        pendientes_curriculares,
        cobertura_fuente_lineage.values(),
    )
    for pendiente in pendientes_curriculares:
        pendiente["carrera"] = carrera_ejecucion
        pendiente["periodo"] = periodo_ejecucion
    pendientes_curriculares = [
        preparar_fila_paquete(
            pendiente,
            id_ejecucion=id_ejecucion,
            carrera=carrera_ejecucion,
            periodo=periodo_ejecucion,
        )
        for pendiente in pendientes_curriculares
    ]
    pendientes_curriculares = clasificar_propuestas(pendientes_curriculares)
    return NormalizacionCurricular(
        filas_por_archivo=filas_por_archivo,
        competencias_fuente=competencias_fuente,
        habilidades_fuente=habilidades_fuente,
        herramientas_fuente=herramientas_fuente,
        cobertura_fuente_lineage=cobertura_fuente_lineage,
        cobertura_canonica_lineage=cobertura_canonica_lineage,
        pendientes_curriculares=pendientes_curriculares,
        hallazgos=tuple(hallazgos),
        cuarentena=tuple(cuarentena),
    )
