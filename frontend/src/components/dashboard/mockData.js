const tendenciaBase = [
  { periodo: "Ene", ofertas: 74 },
  { periodo: "Feb", ofertas: 86 },
  { periodo: "Mar", ofertas: 83 },
  { periodo: "Abr", ofertas: 101 },
  { periodo: "May", ofertas: 96 },
  { periodo: "Jun", ofertas: 118 },
  { periodo: "Jul", ofertas: 112 },
  { periodo: "Ago", ofertas: 129 },
  { periodo: "Sep", ofertas: 124 },
  { periodo: "Oct", ofertas: 141 },
  { periodo: "Nov", ofertas: 136 },
  { periodo: "Dic", ofertas: 151 },
];

function crearTendencia(factor) {
  return tendenciaBase.map((fila) => ({
    ...fila,
    ofertas: Math.round(fila.ofertas * factor),
  }));
}

function crearBrechas(items) {
  return items.map(([elemento, demanda, cobertura, ofertas], indice) => ({
    id: "mock-" + indice,
    elemento,
    demanda,
    cobertura,
    ofertas_que_requieren: ofertas,
    total_ofertas: 1200,
    cursos_con_cobertura: Math.round(cobertura * 40),
    total_cursos: 40,
    brecha: demanda - cobertura,
  }));
}

function crearCobertura(items) {
  return items.map(([elemento, , cobertura], indice) => ({
    id: "cobertura-" + indice,
    elemento,
    cursos_con_cobertura: Math.max(1, Math.round(cobertura * 40)),
    total_cursos: 40,
  }));
}

function crearDemanda(items) {
  return items.map(([elemento, , , ofertas], indice) => ({
    id: "demanda-" + indice,
    elemento,
    ofertas,
  }));
}

function modelo({ tendencia, items, radar, matriz, industrias, indice, cursos }) {
  const brechas = crearBrechas(items);
  return {
    tendencia,
    demanda: crearDemanda(items),
    cobertura: crearCobertura(items),
    brechas,
    radar,
    matriz,
    industrias,
    indice,
    ofertas: tendencia.reduce((total, fila) => total + fila.ofertas, 0),
    destinos: destinosPorIndustria,
    carreras: carrerasPorIndustria,
    carrerasMatriz: preparacionPorCarrera,
    cursos,
    vigencia: vigenciaCursos,
    diferenciadores: diferenciadoresEmpresa,
    empresasTop: empresasTop,
    perfilSector: perfilPorSector,
  };
}

const competencias = [
  ["Desarrollo de software", 0.84, 0.59, 286],
  ["Pensamiento analítico", 0.72, 0.68, 244],
  ["Gestión de proyectos", 0.64, 0.43, 201],
  ["Comunicación efectiva", 0.58, 0.61, 178],
  ["Ciberseguridad", 0.51, 0.29, 146],
  ["Arquitectura cloud", 0.46, 0.18, 132],
];

const habilidades = [
  ["SQL", 0.79, 0.55, 272],
  ["Python", 0.76, 0.63, 261],
  ["Visualización de datos", 0.61, 0.34, 206],
  ["Trabajo colaborativo", 0.56, 0.71, 185],
  ["Documentación técnica", 0.49, 0.39, 151],
  ["Presentación ejecutiva", 0.43, 0.26, 124],
];

const herramientas = [
  ["Power BI", 0.71, 0.33, 238],
  ["Git", 0.68, 0.58, 223],
  ["AWS", 0.57, 0.22, 187],
  ["Figma", 0.46, 0.37, 142],
  ["Docker", 0.44, 0.29, 138],
  ["Jira", 0.39, 0.42, 116],
];

const radarCompetencias = [
  { eje: "Técnica", mercado: 82, curriculo: 66 },
  { eje: "Datos", mercado: 76, curriculo: 54 },
  { eje: "Negocio", mercado: 68, curriculo: 61 },
  { eje: "Comunicación", mercado: 58, curriculo: 72 },
  { eje: "Innovación", mercado: 71, curriculo: 47 },
];

const radarHabilidades = [
  { eje: "Programación", mercado: 78, curriculo: 65 },
  { eje: "Análisis", mercado: 74, curriculo: 59 },
  { eje: "Diseño", mercado: 52, curriculo: 43 },
  { eje: "Colaboración", mercado: 64, curriculo: 76 },
  { eje: "Presentación", mercado: 48, curriculo: 38 },
];

const radarHerramientas = [
  { eje: "Código", mercado: 72, curriculo: 60 },
  { eje: "Datos", mercado: 75, curriculo: 41 },
  { eje: "Cloud", mercado: 63, curriculo: 25 },
  { eje: "Producto", mercado: 48, curriculo: 43 },
  { eje: "Gestión", mercado: 51, curriculo: 56 },
];

const matrizCompetencias = [
  { elemento: "Software", valores: [2, 3, 4, 3, 4, 5] },
  { elemento: "Datos", valores: [1, 2, 3, 4, 5, 4] },
  { elemento: "Proyectos", valores: [3, 2, 2, 3, 4, 3] },
  { elemento: "Seguridad", valores: [1, 1, 2, 3, 4, 5] },
];

const matrizHabilidades = [
  { elemento: "SQL", valores: [2, 3, 3, 4, 5, 4] },
  { elemento: "Python", valores: [3, 2, 4, 5, 4, 4] },
  { elemento: "Visualización", valores: [1, 2, 2, 4, 5, 3] },
  { elemento: "Documentación", valores: [2, 2, 3, 2, 3, 4] },
];

const matrizHerramientas = [
  { elemento: "Power BI", valores: [1, 2, 4, 4, 5, 5] },
  { elemento: "Git", valores: [3, 4, 4, 3, 5, 4] },
  { elemento: "AWS", valores: [1, 1, 2, 3, 4, 5] },
  { elemento: "Docker", valores: [1, 2, 2, 3, 4, 4] },
];

const destinosPorIndustria = [
  { elemento: "Servicios digitales", oportunidades: 86 },
  { elemento: "Banca y seguros", oportunidades: 74 },
  { elemento: "Consultoría", oportunidades: 68 },
  { elemento: "Retail", oportunidades: 49 },
  { elemento: "Telecomunicaciones", oportunidades: 42 },
];

const carrerasPorIndustria = [
  { elemento: "Ingeniería de Sistemas", indice: 84 },
  { elemento: "Ingeniería Industrial", indice: 72 },
  { elemento: "Administración", indice: 61 },
  { elemento: "Economía", indice: 56 },
];

const preparacionPorCarrera = [
  { elemento: "Ing. de Sistemas", valores: [5, 4, 5, 4, 3] },
  { elemento: "Ing. Industrial", valores: [4, 4, 3, 4, 3] },
  { elemento: "Administración", valores: [3, 3, 3, 4, 4] },
  { elemento: "Comunicación", valores: [2, 3, 2, 4, 5] },
];

const vigenciaCursos = [
  { elemento: "Analítica aplicada", actualizado: 78, revisar: 22 },
  { elemento: "Arquitectura de software", actualizado: 64, revisar: 36 },
  { elemento: "Gestión de producto", actualizado: 58, revisar: 42 },
  { elemento: "Infraestructura cloud", actualizado: 46, revisar: 54 },
  { elemento: "Seguridad digital", actualizado: 41, revisar: 59 },
];

const diferenciadoresEmpresa = [
  { elemento: "Datos y BI", referencia: 84, comparada: 57 },
  { elemento: "Cloud", referencia: 71, comparada: 44 },
  { elemento: "Producto", referencia: 66, comparada: 62 },
  { elemento: "Automatización", referencia: 58, comparada: 75 },
  { elemento: "Gestión ágil", referencia: 52, comparada: 69 },
];

const empresasTop = [
  { elemento: "Andes Tech", ofertas: 286 },
  { elemento: "Nexo Analytics", ofertas: 244 },
  { elemento: "Origen Digital", ofertas: 219 },
  { elemento: "Grupo Horizonte", ofertas: 187 },
  { elemento: "Conecta Perú", ofertas: 164 },
];

const perfilPorSector = [
  { elemento: "Datos", valores: [5, 4, 4, 3, 3] },
  { elemento: "Tecnología", valores: [5, 3, 4, 3, 4] },
  { elemento: "Negocio", valores: [3, 5, 4, 4, 3] },
  { elemento: "Comunicación", valores: [3, 3, 4, 4, 5] },
];

const cursosCompetencias = [
  { elemento: "Arquitectura de software", mercado: 86, curriculo: 62 },
  { elemento: "Laboratorio de datos", mercado: 79, curriculo: 74 },
  { elemento: "Gestión de proyectos", mercado: 68, curriculo: 57 },
  { elemento: "Ciberseguridad aplicada", mercado: 64, curriculo: 38 },
  { elemento: "Comunicación profesional", mercado: 53, curriculo: 72 },
];

const cursosHabilidades = [
  { elemento: "Taller de SQL", mercado: 81, curriculo: 63 },
  { elemento: "Programación con Python", mercado: 77, curriculo: 71 },
  { elemento: "Narrativa de datos", mercado: 66, curriculo: 39 },
  { elemento: "Documentación técnica", mercado: 52, curriculo: 45 },
  { elemento: "Presentación ejecutiva", mercado: 46, curriculo: 31 },
];

const cursosHerramientas = [
  { elemento: "Visualización con Power BI", mercado: 76, curriculo: 42 },
  { elemento: "Control de versiones con Git", mercado: 70, curriculo: 64 },
  { elemento: "Servicios cloud", mercado: 63, curriculo: 29 },
  { elemento: "Diseño de producto con Figma", mercado: 51, curriculo: 41 },
  { elemento: "Contenedores con Docker", mercado: 48, curriculo: 35 },
];

export const MOCK_FACULTADES = [
  { id: "ingenieria", nombre: "Facultad de Ingeniería" },
  { id: "negocios", nombre: "Facultad de Ciencias Empresariales" },
  { id: "comunicacion", nombre: "Facultad de Comunicación" },
];

export const MOCK_INDUSTRIAS = [
  { id: "digital", nombre: "Servicios digitales" },
  { id: "banca", nombre: "Banca y seguros" },
  { id: "consultoria", nombre: "Consultoría" },
  { id: "retail", nombre: "Retail" },
];

export const MOCK_EMPRESAS = [
  { id: "andes", nombre: "Andes Tech" },
  { id: "nexo", nombre: "Nexo Analytics" },
  { id: "origen", nombre: "Origen Digital" },
];

export const MOCK_FUNCIONES = [
  { id: "datos", nombre: "Analítica de datos" },
  { id: "producto", nombre: "Producto digital" },
  { id: "tecnologia", nombre: "Tecnología y cloud" },
  { id: "liderazgo", nombre: "Liderazgo de equipos" },
];

export const MOCK_CARRERAS = [
  { id: "sistemas", nombre: "Ingeniería de Sistemas", cursos_conectados: 42, facultad_id: "ingenieria" },
  { id: "industrial", nombre: "Ingeniería Industrial", cursos_conectados: 38, facultad_id: "ingenieria" },
  { id: "administracion", nombre: "Administración", cursos_conectados: 35, facultad_id: "negocios" },
  { id: "comunicacion", nombre: "Comunicación", cursos_conectados: 28, facultad_id: "comunicacion" },
];

export const MOCK_DIMENSIONES = [
  { id: "competencias", nombre: "Competencias" },
  { id: "habilidades", nombre: "Habilidades" },
  { id: "herramientas", nombre: "Herramientas" },
];

export const MOCK_PERIODOS = ["Últimos 12 meses", "Ciclo 2025", "Comparativo semestral"];

export const MOCK_DASHBOARDS = {
  competencias: modelo({
    tendencia: crearTendencia(1),
    items: competencias,
    radar: radarCompetencias,
    matriz: matrizCompetencias,
    industrias: [
      { industria: "Servicios digitales", ofertas: 312 },
      { industria: "Consultoría", ofertas: 267 },
      { industria: "Banca y seguros", ofertas: 224 },
      { industria: "Retail", ofertas: 177 },
      { industria: "Telecomunicaciones", ofertas: 154 },
    ],
    indice: 68,
    cursos: cursosCompetencias,
  }),
  habilidades: modelo({
    tendencia: crearTendencia(0.88),
    items: habilidades,
    radar: radarHabilidades,
    matriz: matrizHabilidades,
    industrias: [
      { industria: "Consultoría", ofertas: 284 },
      { industria: "Servicios digitales", ofertas: 257 },
      { industria: "Educación", ofertas: 192 },
      { industria: "Retail", ofertas: 164 },
      { industria: "Banca y seguros", ofertas: 151 },
    ],
    indice: 72,
    cursos: cursosHabilidades,
  }),
  herramientas: modelo({
    tendencia: crearTendencia(0.75),
    items: herramientas,
    radar: radarHerramientas,
    matriz: matrizHerramientas,
    industrias: [
      { industria: "Servicios digitales", ofertas: 241 },
      { industria: "Banca y seguros", ofertas: 197 },
      { industria: "Consultoría", ofertas: 185 },
      { industria: "Telecomunicaciones", ofertas: 132 },
      { industria: "Retail", ofertas: 108 },
    ],
    indice: 61,
    cursos: cursosHerramientas,
  }),
};
