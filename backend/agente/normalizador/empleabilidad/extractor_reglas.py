"""Reglas declarativas para la extracción CHH laboral."""

from __future__ import annotations

from dataclasses import dataclass

REGLAS_VERSION = "empleabilidad-chh-0.1.0"


@dataclass(frozen=True, slots=True)
class ReglaCHH:
    """Regla de alta precisión que produce una cadena Competencia-Habilidad."""

    id: str
    patron: str
    competencia: str
    habilidad: str
    tipo_competencia: str = "dura"


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
