"""Extractor CHH laboral con reglas versionadas y propuestas no publicables."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH

REGLAS_VERSION = "empleabilidad-chh-0.1.0"


@dataclass(frozen=True, slots=True)
class ReglaCHH:
    """Regla de alta precisión que produce una cadena Competencia-Habilidad."""

    id: str
    patron: str
    competencia: str
    habilidad: str
    tipo_competencia: str = "dura"


@dataclass(frozen=True, slots=True)
class CadenaCHH:
    """Cadena canónica con evidencia suficiente para auditoría posterior."""

    competencia: ConceptoCHH
    habilidad: ConceptoCHH
    herramienta: ConceptoCHH | None
    tipo: str
    evidencia: str
    confianza: float
    metodo: str
    regla: str

    def a_dict(self) -> dict[str, object]:
        """Serializa una cadena sin incluir texto completo de la fuente."""

        return {
            "competencia": self.competencia.a_dict(),
            "habilidad": self.habilidad.a_dict(),
            "herramienta": self.herramienta.a_dict() if self.herramienta else None,
            "tipo": self.tipo,
            "evidencia": self.evidencia,
            "confianza": self.confianza,
            "metodo": self.metodo,
            "regla": self.regla,
        }


@dataclass(frozen=True, slots=True)
class PropuestaHerramienta:
    """Herramienta inferible que requiere aceptación explícita o revisión LLM."""

    herramienta: ConceptoCHH
    evidencia: str
    confianza: float
    regla: str

    def a_dict(self) -> dict[str, object]:
        return {
            "herramienta": self.herramienta.a_dict(),
            "evidencia": self.evidencia,
            "confianza": self.confianza,
            "regla": self.regla,
        }


@dataclass(frozen=True, slots=True)
class ResultadoExtraccion:
    """Resultado CHH antes de crear relaciones físicas del grafo."""

    cadenas: tuple[CadenaCHH, ...]
    propuestas_herramienta: tuple[PropuestaHerramienta, ...]
    incidencias: tuple[dict[str, str], ...]

    def a_dict(self) -> dict[str, object]:
        return {
            "cadenas": [cadena.a_dict() for cadena in self.cadenas],
            "propuestas_herramienta": [
                propuesta.a_dict() for propuesta in self.propuestas_herramienta
            ],
            "incidencias": list(self.incidencias),
        }


def _regla(
    id_regla: str,
    patron: str,
    competencia: str,
    habilidad: str,
    tipo_competencia: str = "dura",
) -> ReglaCHH:
    return ReglaCHH(id_regla, patron, competencia, habilidad, tipo_competencia)


REGLAS_LABORALES: tuple[ReglaCHH, ...] = (
    _regla(
        "LAB_COM_001",
        r"prospectar|clientes potenciales|generar cartera",
        "Prospección comercial",
        "Prospectar clientes potenciales",
    ),
    _regla(
        "LAB_COM_002",
        r"cerrar ventas|cierre de ventas|concretar ventas",
        "Gestión de ventas",
        "Cerrar ventas",
    ),
    _regla(
        "LAB_COM_003",
        r"cotizar|cotizaciones|propuestas economicas|propuesta comercial",
        "Gestión de ventas",
        "Elaborar propuestas comerciales",
    ),
    _regla(
        "LAB_COM_004",
        (
            r"seguimiento comercial|seguimiento (?:a|de) (?:los )?"
            r"(?:clientes|leads|propuestas|cotizaciones)"
        ),
        "Gestión de ventas",
        "Dar seguimiento a oportunidades comerciales",
    ),
    _regla(
        "LAB_COM_005",
        r"cartera de clientes|cuentas clave|key account|fidelizacion",
        "Gestión de cuentas",
        "Gestionar cuentas y cartera de clientes",
    ),
    _regla(
        "LAB_CLI_001",
        r"atencion (?:a|al|de) clientes|atender (?:a )?(?:los )?clientes|servicio al cliente",
        "Atención al cliente",
        "Atender consultas de clientes",
    ),
    _regla(
        "LAB_CLI_002",
        r"reclamos?|quejas|resolver .*clientes",
        "Gestión de reclamos",
        "Resolver reclamos y solicitudes de clientes",
    ),
    _regla(
        "LAB_MKT_001",
        r"plan(?:ificar|es?) (?:de )?(?:marketing|mercadeo)|estrategia de marketing",
        "Planificación de marketing",
        "Diseñar planes de marketing",
    ),
    _regla(
        "LAB_MKT_002",
        r"campanas? (?:de )?(?:marketing|publicitarias?|digitales?)|media plan|pauta digital",
        "Gestión de campañas",
        "Planificar y ejecutar campañas",
    ),
    _regla(
        "LAB_MKT_003",
        r"redes sociales|social media|community manager|instagram|facebook|tiktok|linkedin",
        "Gestión de redes sociales",
        "Planificar y publicar contenido en redes sociales",
    ),
    _regla(
        "LAB_MKT_004",
        r"redactar|redaccion|copywriting|copys?|notas de prensa|comunicados",
        "Producción de contenidos",
        "Redactar contenidos para canales y audiencias",
    ),
    _regla(
        "LAB_MKT_005",
        r"investigacion de mercados?|estudio de mercado|analisis de mercado|market research",
        "Investigación de mercados",
        "Investigar mercados y necesidades de clientes",
    ),
    _regla(
        "LAB_RRHH_001",
        r"reclutamiento|seleccion de personal|filtrar cv|entrevistas por competencias",
        "Selección de personal",
        "Reclutar y seleccionar candidatos",
    ),
    _regla(
        "LAB_RRHH_002",
        r"onboarding|induccion de personal|incorporacion de (?:nuevos )?colaboradores",
        "Incorporación de personal",
        "Ejecutar procesos de inducción",
    ),
    _regla(
        "LAB_RRHH_003",
        r"capacitacion|formacion de colaboradores|plan de aprendizaje",
        "Capacitación y desarrollo",
        "Diseñar y coordinar capacitaciones",
    ),
    _regla(
        "LAB_RRHH_004",
        r"evaluacion de desempeno|performance|feedback al personal",
        "Gestión del desempeño",
        "Evaluar y retroalimentar el desempeño",
    ),
    _regla(
        "LAB_RRHH_005",
        r"planilla|nomina|remuneraciones|boletas de pago|compensaciones",
        "Administración de compensaciones",
        "Procesar nómina y compensaciones",
    ),
    _regla(
        "LAB_FIN_001",
        r"registro contable|asientos contables|contabilizar|libros contables",
        "Contabilidad financiera",
        "Registrar operaciones contables",
    ),
    _regla(
        "LAB_FIN_002",
        r"conciliacion(?:es)? bancaria|conciliar bancos",
        "Conciliación financiera",
        "Realizar conciliaciones bancarias",
    ),
    _regla(
        "LAB_FIN_003",
        r"facturacion|emitir facturas|comprobantes de pago",
        "Facturación",
        "Emitir y controlar comprobantes de pago",
    ),
    _regla(
        "LAB_FIN_004",
        r"estados financieros|eeff|balance general|estado de resultados",
        "Información financiera",
        "Preparar y analizar estados financieros",
    ),
    _regla(
        "LAB_FIN_005",
        r"impuestos?|tributari|igv|renta|detracciones|retenciones|percepciones|pdt|ple",
        "Gestión tributaria",
        "Calcular, declarar y controlar obligaciones tributarias",
    ),
    _regla(
        "LAB_FIN_006",
        r"tesoreria|flujo de caja|cash flow|posicion de caja|liquidez",
        "Gestión de tesorería",
        "Controlar caja, liquidez, pagos y cobros",
    ),
    _regla(
        "LAB_OPS_001",
        (
            r"mapeo de procesos|diagramas? de flujo|levantamiento de procesos|"
            r"disenar y documentar procesos|documentar procesos|bpmn"
        ),
        "Modelamiento de procesos",
        "Modelar y documentar procesos",
    ),
    _regla(
        "LAB_OPS_002",
        r"mejora de procesos|mejora continua|redisenar procesos|optimizar procesos",
        "Mejora continua",
        "Analizar y mejorar procesos",
    ),
    _regla(
        "LAB_OPS_003",
        r"indicadores?|kpis?|tablero de control|cuadro de mando",
        "Control de gestión",
        "Diseñar y monitorear indicadores",
    ),
    _regla(
        "LAB_OPS_004",
        r"planificar.*proyecto|cronograma del proyecto|seguimiento.*proyecto|control.*proyecto",
        "Gestión de proyectos",
        "Planificar y controlar proyectos",
    ),
    _regla(
        "LAB_OPS_005",
        r"metodologias? agiles?|scrum|kanban|sprint|backlog",
        "Gestión ágil",
        "Gestionar trabajo con métodos ágiles",
    ),
    _regla(
        "LAB_LOG_001",
        r"compras?|ordenes? de compra|requerimientos? de compra",
        "Gestión de compras",
        "Gestionar solicitudes y órdenes de compra",
    ),
    _regla(
        "LAB_LOG_002",
        r"proveedores?|evaluacion de proveedores|negociar.*proveedores",
        "Gestión de proveedores",
        "Evaluar y negociar con proveedores",
    ),
    _regla(
        "LAB_LOG_003",
        r"inventarios?|stock|conteo ciclico|kardex",
        "Gestión de inventarios",
        "Controlar inventarios y niveles de stock",
    ),
    _regla(
        "LAB_LOG_004",
        r"almacen|recepcion de mercaderia|despacho de mercaderia|picking|packing",
        "Gestión de almacenes",
        "Gestionar recepción, almacenamiento y despacho",
    ),
    _regla(
        "LAB_DATA_001",
        r"analizar datos|analisis de datos|data analy|exploracion de datos",
        "Análisis de datos",
        "Analizar datos para obtener hallazgos",
    ),
    _regla(
        "LAB_DATA_002",
        r"dashboards?|tableros? de (?:control|gestion)|visualizacion de datos",
        "Visualización de datos",
        "Construir tableros y visualizaciones",
    ),
    _regla(
        "LAB_DATA_003",
        r"modelos? predictivos?|machine learning|aprendizaje automatico",
        "Ciencia de datos",
        "Desarrollar modelos predictivos",
    ),
    _regla(
        "LAB_DATA_004",
        r"etl|pipelines? de datos|integracion de datos",
        "Ingeniería de datos",
        "Construir procesos de integración de datos",
    ),
    _regla(
        "LAB_DATA_005",
        r"base de datos|bases de datos|modelo de datos",
        "Gestión de bases de datos",
        "Diseñar y administrar bases de datos",
    ),
    _regla(
        "LAB_DATA_006",
        (
            r"programar|desarrollar software|desarrollo de sistemas|"
            r"aplicaciones? (?:web|moviles?|de escritorio)"
        ),
        "Desarrollo de software",
        "Desarrollar aplicaciones de software",
    ),
    _regla(
        "LAB_DATA_007",
        r"arquitectura de software|microservicios|integraciones?|apis?",
        "Arquitectura de software",
        "Diseñar arquitecturas e integraciones de software",
    ),
    _regla(
        "LAB_DATA_008",
        r"pruebas? de software|testing|casos? de prueba|qa\b",
        "Pruebas de software",
        "Diseñar y ejecutar pruebas de software",
    ),
    _regla(
        "LAB_SOFT_001",
        r"trabajo en equipo|colaborar con equipos|colaborativo",
        "Trabajo en equipo",
        "Colaborar con equipos de trabajo",
        "blanda",
    ),
    _regla(
        "LAB_SOFT_002",
        r"adaptabilidad|adaptarse a cambios|dinamismo y energia",
        "Adaptabilidad",
        "Adaptarse a cambios del entorno",
        "blanda",
    ),
)


INFERENCIAS_HERRAMIENTA: tuple[tuple[str, str, str, float], ...] = (
    (
        r"analisis de datos|analizar datos|dashboard|tablero de control|visualizacion de datos",
        "Power BI",
        (
            "La señal describe análisis o visualización; se propone una herramienta BI "
            "frecuente, no se publica automáticamente."
        ),
        0.35,
    ),
    (
        r"analisis de datos|analizar datos|base de datos|consultas? de datos",
        "SQL",
        (
            "La señal describe análisis o consulta de datos; SQL queda como propuesta "
            "contextual revisable."
        ),
        0.35,
    ),
    (
        r"mapeo de procesos|modelamiento de procesos|diagramas? de flujo",
        "Bizagi",
        (
            "La señal describe modelamiento de procesos; Bizagi es una propuesta de "
            "software, no evidencia explícita."
        ),
        0.25,
    ),
)

ALIASES_HERRAMIENTAS: tuple[tuple[str, str], ...] = (
    ("excel", "Microsoft Excel"),
    ("ms excel", "Microsoft Excel"),
    ("powerbi", "Power BI"),
    ("bpmn", "BPMN 2.0"),
)

HERRAMIENTAS_REGLAS_PREFERIDAS: dict[str, frozenset[str]] = {
    "SQL": frozenset({"LAB_DATA_001", "LAB_DATA_004", "LAB_DATA_005"}),
    "Power BI": frozenset({"LAB_DATA_002"}),
    "Microsoft Excel": frozenset({"LAB_LOG_003", "LAB_FIN_003", "LAB_DATA_001"}),
    "Bizagi": frozenset({"LAB_OPS_001", "LAB_OPS_002"}),
    "BPMN 2.0": frozenset({"LAB_OPS_001"}),
}

AREA_DEFAULTS: tuple[tuple[str, str, str], ...] = (
    (r"comercial|ventas", "Gestión comercial", "Gestionar actividades comerciales"),
    (
        r"marketing|publicidad|analisis de mercados?|investigacion de mercados",
        "Gestión de marketing",
        "Planificar actividades de marketing",
    ),
    (
        r"recursos humanos|psicologia organizacional",
        "Gestión de recursos humanos",
        "Gestionar procesos de recursos humanos",
    ),
    (r"contabilidad|costos", "Contabilidad", "Procesar información contable"),
    (
        r"finanzas|tesoreria|banca|inversiones|mercado de capitales",
        "Gestión financiera",
        "Analizar y gestionar información financiera",
    ),
    (
        r"legal|derecho|analisis documentario|certificaciones",
        "Gestión jurídica",
        "Analizar y gestionar asuntos jurídicos",
    ),
    (
        r"operaciones|produccion|estudio de metodos",
        "Gestión de operaciones",
        "Coordinar y controlar operaciones",
    ),
    (
        r"logistica|almacenes|distribucion|transporte|compras|importaciones|exportaciones",
        "Logística",
        "Coordinar operaciones logísticas",
    ),
    (
        (
            r"tecnologias de la informacion|sistemas|inteligencia de negocios|"
            r"innovacion tecnologica|transformacion digital"
        ),
        "Gestión de tecnología",
        "Gestionar soluciones y servicios tecnológicos",
    ),
    (
        r"consultoria|mejora continua",
        "Consultoría y mejora organizacional",
        "Analizar problemas y proponer mejoras",
    ),
    (r"proyectos", "Gestión de proyectos", "Planificar y dar seguimiento a proyectos"),
    (r"atencion al cliente", "Atención al cliente", "Atender y orientar clientes"),
    (
        r"comunicacion|asuntos corporativos|prensa|imagen|eventos",
        "Gestión de la comunicación",
        "Planificar y ejecutar comunicaciones",
    ),
    (r"diseno|audiovisual", "Producción creativa", "Desarrollar piezas y contenidos creativos"),
    (
        r"riesgos|auditoria|control de activos",
        "Gestión de riesgos y control",
        "Evaluar riesgos y controles",
    ),
    (
        r"construccion|arquitectura|habilitacion urbana|planificacion urbana|patrimonio",
        "Gestión del entorno construido",
        "Diseñar y gestionar proyectos del entorno construido",
    ),
    (r"gestion ambiental", "Gestión ambiental", "Gestionar aspectos e impactos ambientales"),
    (r"mantenimiento", "Gestión de mantenimiento", "Coordinar actividades de mantenimiento"),
    (r"psicologia", "Intervención psicológica", "Evaluar y atender necesidades psicológicas"),
    (r"estudios economicos", "Análisis económico", "Analizar información y escenarios económicos"),
    (
        r"planeamiento estrategico|direccion",
        "Gestión estratégica",
        "Analizar y ejecutar iniciativas estratégicas",
    ),
    (r"administracion", "Gestión administrativa", "Coordinar procesos y recursos administrativos"),
    (r"creditos y cobranzas", "Gestión crediticia", "Evaluar y administrar créditos"),
    (r"control de calidad", "Gestión de calidad", "Controlar y asegurar la calidad"),
)


INFORME_CAMPOS: dict[str, tuple[str, str, str]] = {
    "compet_adapta_bilidad": ("Adaptabilidad", "Adaptarse a cambios del entorno", "blanda"),
    "compet_capac_aprender": (
        "Autogestión del aprendizaje",
        "Adquirir y aplicar nuevos conocimientos",
        "blanda",
    ),
    "compet_capac_analisis": (
        "Pensamiento crítico",
        "Analizar información y situaciones",
        "blanda",
    ),
    "compet_nivel_conoci": ("Dominio profesional", "Aplicar conocimientos profesionales", "dura"),
    "compet_aplic_conoci": (
        "Aplicación de conocimientos",
        "Aplicar conocimientos a situaciones laborales",
        "dura",
    ),
    "compet_dinamis_energia": ("Proactividad", "Actuar con dinamismo y energía", "blanda"),
    "compet_iniciativa_autono": (
        "Autonomía",
        "Ejecutar actividades con iniciativa y autonomía",
        "blanda",
    ),
    "compet_creatividad": ("Creatividad", "Proponer ideas y soluciones creativas", "blanda"),
    "compet_toleran_presion": (
        "Gestión del estrés",
        "Mantener el desempeño bajo presión",
        "blanda",
    ),
    "compet_resoluci_problema": (
        "Solución de problemas",
        "Analizar y resolver problemas",
        "blanda",
    ),
    "compet_preocupa_orden": (
        "Organización del trabajo",
        "Organizar el trabajo con orden y precisión",
        "blanda",
    ),
    "compet_vision_futuro": (
        "Pensamiento estratégico",
        "Anticipar escenarios y orientar decisiones futuras",
        "blanda",
    ),
    "compet_orienta_cliente": (
        "Orientación al cliente",
        "Orientar el trabajo a las necesidades del cliente",
        "blanda",
    ),
    "compet_relacion_interpers": (
        "Relaciones interpersonales",
        "Construir relaciones laborales efectivas",
        "blanda",
    ),
    "compet_trabajo_equipo": ("Trabajo en equipo", "Colaborar con equipos de trabajo", "blanda"),
}


def _clave_texto(texto: str) -> str:
    from agente.normalizador.empleabilidad.catalogo import clave_concepto

    return clave_concepto(texto)


def _herramientas_explicitas(
    texto: str,
    catalogo: CatalogoCHH,
) -> tuple[tuple[ConceptoCHH, tuple[int, int]], ...]:
    """Detecta herramientas solo cuando el nombre aparece en la fuente."""

    normalizado = _clave_texto(texto)
    encontrados: list[tuple[ConceptoCHH, tuple[int, int]]] = []
    ocupados: list[tuple[int, int]] = []
    candidatos: list[tuple[ConceptoCHH, str]] = [
        (herramienta, herramienta.nombre) for herramienta in catalogo.herramientas
    ]
    for alias, nombre in ALIASES_HERRAMIENTAS:
        herramienta = catalogo.obtener("herramienta", nombre)
        if herramienta is not None:
            candidatos.append((herramienta, alias))
    candidatos.sort(key=lambda item: len(_clave_texto(item[1])), reverse=True)
    for herramienta, nombre in candidatos:
        clave = _clave_texto(nombre)
        if len(clave) < 2:
            continue
        patron = rf"(?<![a-z0-9]){re.escape(clave)}(?![a-z0-9])"
        coincidencia = re.search(patron, normalizado)
        if coincidencia is None:
            continue
        span = coincidencia.span()
        if any(span[0] < otro[1] and otro[0] < span[1] for otro in ocupados):
            continue
        ocupados.append(span)
        encontrados.append((herramienta, span))
    return tuple(encontrados)


def _propuestas_herramienta(
    texto: str,
    catalogo: CatalogoCHH,
    explicitas: tuple[tuple[ConceptoCHH, tuple[int, int]], ...],
) -> tuple[PropuestaHerramienta, ...]:
    normalizado = _clave_texto(texto)
    ids_explicitos = {herramienta.id for herramienta, _ in explicitas}
    resultado: list[PropuestaHerramienta] = []
    for indice, (patron, nombre, evidencia, confianza) in enumerate(INFERENCIAS_HERRAMIENTA, 1):
        herramienta = catalogo.obtener("herramienta", nombre)
        if herramienta is None or herramienta.id in ids_explicitos:
            continue
        if re.search(patron, normalizado):
            resultado.append(
                PropuestaHerramienta(
                    herramienta,
                    evidencia,
                    confianza,
                    f"{REGLAS_VERSION}:HERR_INF_{indice:03d}",
                )
            )
    return tuple(resultado)


def extraer(
    texto: str,
    catalogo: CatalogoCHH,
    tipo: str = "exige",
    area: str = "",
) -> ResultadoExtraccion:
    """Extrae cadenas laborales deterministas y deja inferencias de herramienta aparte."""

    normalizado = _clave_texto(texto)
    explicitas = _herramientas_explicitas(texto, catalogo)
    coincidencias: list[tuple[ReglaCHH, re.Match[str]]] = []
    incidencias: list[dict[str, str]] = []
    for regla in REGLAS_LABORALES:
        coincidencia = re.search(regla.patron, normalizado)
        if coincidencia:
            coincidencias.append((regla, coincidencia))

    cadenas: list[CadenaCHH] = []
    vistos: set[tuple[str, str, str]] = set()
    for indice_coincidencia, (regla, coincidencia) in enumerate(coincidencias):
        competencia = catalogo.obtener("competencia", regla.competencia)
        habilidad = catalogo.obtener("habilidad", regla.habilidad)
        if competencia is None or habilidad is None:
            incidencias.append(
                {
                    "codigo": "REGLA_SIN_CONCEPTO_CANONICO",
                    "regla": regla.id,
                    "detalle": f"{regla.competencia} -> {regla.habilidad}",
                }
            )
            continue

        herramientas: Sequence[ConceptoCHH | None] = [None]
        if len(coincidencias) == 1:
            herramientas = [herramienta for herramienta, _ in explicitas]
            if not herramientas:
                herramientas = [None]
        else:
            preferidas = [
                herramienta
                for herramienta, _ in explicitas
                if regla.id in HERRAMIENTAS_REGLAS_PREFERIDAS.get(herramienta.nombre, frozenset())
            ]
            if preferidas:
                herramientas_cercanas = preferidas
            else:
                herramientas_cercanas = []
                for herramienta, span in explicitas:
                    distancias = [
                        abs(span[0] - otra_coincidencia.start())
                        for _, otra_coincidencia in coincidencias
                    ]
                    if (
                        distancias[indice_coincidencia] == min(distancias)
                        and distancias[indice_coincidencia] <= 140
                    ):
                        herramientas_cercanas.append(herramienta)
            herramientas = herramientas_cercanas
            if not herramientas:
                herramientas = [None]
        for herramienta_cadena in herramientas:
            clave = (
                competencia.id,
                habilidad.id,
                herramienta_cadena.id if herramienta_cadena else "",
            )
            if clave in vistos:
                continue
            vistos.add(clave)
            cadenas.append(
                CadenaCHH(
                    competencia,
                    habilidad,
                    herramienta_cadena,
                    tipo,
                    f"señal={coincidencia.group(0)}",
                    0.9 if herramienta_cadena is None else 0.95,
                    "regla_determinista",
                    f"{REGLAS_VERSION}:{regla.id}",
                )
            )

    if not cadenas and area:
        area_normalizada = _clave_texto(area)
        for indice, (patron, nombre_competencia, nombre_habilidad) in enumerate(AREA_DEFAULTS, 1):
            coincidencia_area = re.search(patron, area_normalizada)
            if coincidencia_area is None:
                continue
            competencia = catalogo.obtener("competencia", nombre_competencia)
            habilidad = catalogo.obtener("habilidad", nombre_habilidad)
            if competencia is None or habilidad is None:
                incidencias.append(
                    {
                        "codigo": "REGLA_AREA_SIN_CONCEPTO_CANONICO",
                        "regla": f"{REGLAS_VERSION}:AREA_{indice:03d}",
                        "detalle": f"{nombre_competencia} -> {nombre_habilidad}",
                    }
                )
                break
            cadenas.append(
                CadenaCHH(
                    competencia,
                    habilidad,
                    None,
                    tipo,
                    f"area={coincidencia_area.group(0)}",
                    0.72,
                    "regla_area_determinista",
                    f"{REGLAS_VERSION}:AREA_{indice:03d}",
                )
            )
            break

    propuestas = _propuestas_herramienta(texto, catalogo, explicitas)
    return ResultadoExtraccion(tuple(cadenas), propuestas, tuple(incidencias))


def extraer_informe(datos: dict[str, object], catalogo: CatalogoCHH) -> ResultadoExtraccion:
    """Convierte las columnas de evaluación en cadenas ``aplica`` auditables."""

    cadenas: list[CadenaCHH] = []
    incidencias: list[dict[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for campo, (nombre_competencia, nombre_habilidad, _) in INFORME_CAMPOS.items():
        valor = str(datos.get(campo, "") or "").strip().lower()
        if not valor or valor in {"-", "na", "n/a", "nan"}:
            continue
        competencia = catalogo.obtener("competencia", nombre_competencia)
        habilidad = catalogo.obtener("habilidad", nombre_habilidad)
        if competencia is None or habilidad is None:
            incidencias.append(
                {
                    "codigo": "CAMPO_INFORME_SIN_CONCEPTO_CANONICO",
                    "campo": campo,
                    "detalle": f"{nombre_competencia} -> {nombre_habilidad}",
                }
            )
            continue
        clave = (competencia.id, habilidad.id)
        if clave in vistos:
            continue
        vistos.add(clave)
        cadenas.append(
            CadenaCHH(
                competencia,
                habilidad,
                None,
                "aplica",
                f"campo={campo};valor={valor}",
                0.98,
                "campo_evaluacion_determinista",
                f"{REGLAS_VERSION}:INFORME_{campo.upper()}",
            )
        )

    funciones = " ".join(
        str(datos.get(campo, "") or "")
        for campo in (
            "funciones_iniciales",
            "funciones_finales",
            "compet_otros_1",
            "compet_otros_2",
        )
    )
    extraido = extraer(funciones, catalogo, tipo="aplica")
    return ResultadoExtraccion(
        tuple(cadenas) + extraido.cadenas,
        extraido.propuestas_herramienta,
        tuple(incidencias) + extraido.incidencias,
    )
