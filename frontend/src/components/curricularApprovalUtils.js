/**
 * Pure formatting and filtering rules for curricular approval data.
 *
 * Keeping these rules outside the panel makes the rendering seam small while
 * preserving the backend's distinction between source components and explicit
 * canonical relationships.
 */

export const TIPOS = ["competencia", "habilidad", "herramienta"];

export const ETIQUETAS = {
  competencia: "Competencias",
  habilidad: "Habilidades",
  herramienta: "Herramientas",
  otro: "Otros pendientes",
};

export const DESCRIPCIONES = {
  competencia: "Capacidades que el LLM considera propias del perfil curricular.",
  habilidad: "Habilidades detectadas en los logros de los sílabos.",
  herramienta: "Herramientas mencionadas en la evidencia curricular.",
  otro: "Propuestas que el backend no pudo clasificar en un tipo conocido.",
};

export const FILTROS = [
  { id: "all", label: "Todas" },
  { id: "competencia", label: "Competencias" },
  { id: "habilidad", label: "Habilidades" },
  { id: "herramienta", label: "Herramientas" },
  { id: "exact", label: "Duplicados exactos" },
  { id: "semantic", label: "Posibles semánticos" },
  { id: "suspicious", label: "Herramientas sospechosas" },
];

export const FLAG_EXACT = "EXACT_DUPLICATE";
export const FLAG_SEMANTIC = "POSSIBLE_SEMANTIC_DUPLICATE";
export const FLAG_SUSPICIOUS = "SUSPICIOUS_UNRELATED_TOOL";
export const PACKAGE_PAGE_SIZE = 15;
export const PENDING_SKILL_LABEL = "Pendiente de catalogación";

export function texto(valor) {
  return String(valor ?? "").trim();
}

export function claveBusqueda(valor) {
  return texto(valor)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();
}

export const NOMBRE_TECNICO = /^(?:HAB|COMP|HERR|PROP|PROPOSAL|PEN|PKG)(?:[_-][A-Za-z0-9:-]+)+$/i;
export const NOMBRE_HASH = /^(?:sha256:)?[0-9a-f]{16,}$/i;

export function nombreLegible(valor, descripciones = []) {
  const candidato = texto(valor);
  if (!candidato || NOMBRE_TECNICO.test(candidato) || NOMBRE_HASH.test(candidato)) return "";
  const normalizado = claveBusqueda(candidato);
  if (descripciones.some((descripcion) => {
    const valorDescripcion = claveBusqueda(descripcion);
    return valorDescripcion && valorDescripcion === normalizado;
  })) return "";
  return candidato;
}

export function nombrePropuesto(fila) {
  const descripciones = [fila?.descripcion_fuente, fila?.source?.descripcion_fuente];
  const candidatos = [
    fila?.nombre_catalogo,
    fila?.nombre_canonico,
    fila?.nombre_propuesto,
    fila?.propuesta?.nombre,
    fila?.nombre_competencia_fuente,
    fila?.nombre_habilidad_fuente,
    fila?.nombre_herramienta_fuente,
    fila?.nombre_fuente,
  ];
  return candidatos.map((candidato) => nombreLegible(candidato, descripciones)).find(Boolean)
    || PENDING_SKILL_LABEL;
}

export function descripcionPropuesta(fila) {
  return texto(
    fila?.propuesta?.descripcion
      || fila?.descripcion_fuente,
  ) || "Sin descripción adicional.";
}

export function evidenciaDe(fila) {
  if (Array.isArray(fila?.evidencia)) {
    return fila.evidencia.map(texto).filter(Boolean);
  }
  const valor = texto(fila?.evidencia);
  return valor ? [valor] : [];
}

export function flagsDe(fila) {
  const flags = new Set(Array.isArray(fila?.flags) ? fila.flags.map(texto) : []);
  if (fila?.duplicado_exacto || fila?.exact_duplicate) flags.add(FLAG_EXACT);
  if (fila?.posible_duplicado_semantico || fila?.semantic_duplicate) flags.add(FLAG_SEMANTIC);
  if (fila?.herramienta_no_relacionada || fila?.suspicious_tool) flags.add(FLAG_SUSPICIOUS);
  return flags;
}

export function autoDeduplicadaDe(fila) {
  return fila?.auto_deduplicated === true
    || fila?.auto_deduplication_state === "AUTO_DEDUPLICATED"
    || fila?.clasificacion?.auto_deduplicated === true;
}

export function representanteDe(fila) {
  return texto(
    fila?.exact_duplicate_representative_id
      || fila?.representative_id
      || fila?.auto_dedup_representative_id
      || fila?.clasificacion?.exact_duplicate_representative_id,
  );
}

export function tipoDe(fila) {
  const tipo = texto(fila?.tipo).toLocaleLowerCase();
  return TIPOS.includes(tipo) ? tipo : "otro";
}

export function gruposDe(filas) {
  const orden = [...TIPOS, "otro"];
  return orden
    .map((tipo) => ({
      tipo,
      filas: filas.filter((fila) => tipoDe(fila) === tipo),
    }))
    .filter((grupo) => grupo.filas.length);
}

export function conteosDe(filas) {
  const conteos = Object.fromEntries(FILTROS.map(({ id }) => [id, 0]));
  conteos.all = filas.length;
  filas.forEach((fila) => {
    const tipo = tipoDe(fila);
    if (conteos[tipo] !== undefined) conteos[tipo] += 1;
    const flags = flagsDe(fila);
    if (flags.has(FLAG_EXACT)) conteos.exact += 1;
    if (flags.has(FLAG_SEMANTIC)) conteos.semantic += 1;
    if (flags.has(FLAG_SUSPICIOUS)) conteos.suspicious += 1;
  });
  return conteos;
}

export function coincideFiltro(fila, filtro) {
  if (filtro === "all") return true;
  if (["competencia", "habilidad", "herramienta"].includes(filtro)) {
    return tipoDe(fila) === filtro;
  }
  const flags = flagsDe(fila);
  if (filtro === "exact") return flags.has(FLAG_EXACT);
  if (filtro === "semantic") return flags.has(FLAG_SEMANTIC);
  if (filtro === "suspicious") return flags.has(FLAG_SUSPICIOUS);
  return true;
}

export function textoBuscable(fila) {
  return [
    nombrePropuesto(fila),
    descripcionPropuesta(fila),
    fila?.descripcion_fuente,
    fila?.archivo,
    fila?.id_curso,
    fila?.id_silabo,
    fila?.id_pendiente,
    fila?.etiqueta_logro,
    ...evidenciaDe(fila),
  ].map(claveBusqueda).join(" ");
}

export function etiquetasDeSeñal(fila) {
  const flags = flagsDe(fila);
  const etiquetas = [];
  if (flags.has(FLAG_EXACT)) {
    const autoDeduplicada = autoDeduplicadaDe(fila);
    const representante = representanteDe(fila);
    etiquetas.push({
      id: "exact",
      label: "Duplicado exacto",
      className: "border-line bg-fondo text-muted",
      explanation: autoDeduplicada
        ? `Coincide con otra propuesta del mismo tipo y grupo${texto(fila?.grupo_duplicado_exacto || fila?.exact_duplicate_group) ? ` (${fila.grupo_duplicado_exacto || fila.exact_duplicate_group})` : ""}. Se deduplicó automáticamente y esta fila de origen permanece auditable; el representante es ${representante || "la fila determinista del grupo"}. No puede recibir una decisión separada.`
        : `Coincide con otra propuesta del mismo tipo y grupo${texto(fila?.grupo_duplicado_exacto || fila?.exact_duplicate_group) ? ` (${fila.grupo_duplicado_exacto || fila.exact_duplicate_group})` : ""}. Se deduplicó automáticamente; esta fila es el representante ${representante ? `(${representante})` : "determinista"} y requiere revisión humana.`,
    });
  }
  if (flags.has(FLAG_SEMANTIC)) {
    etiquetas.push({
      id: "semantic",
      label: "Posible duplicado semántico",
      className: "border-line bg-fondo text-muted",
      explanation: `Comparte señales de equivalencia con otra propuesta del mismo tipo${texto(fila?.grupo_duplicado_semantico || fila?.semantic_duplicate_group) ? ` (${fila.grupo_duplicado_semantico || fila.semantic_duplicate_group})` : ""}. Requiere revisión humana; no se fusionó automáticamente.`,
    });
  }
  if (flags.has(FLAG_SUSPICIOUS)) {
    etiquetas.push({
      id: "suspicious",
      label: "Herramienta sospechosa / no relacionada",
      className: "border-ulima/35 bg-ulima/5 text-ink",
      explanation: `La evidencia no relaciona claramente la herramienta con el contenido curricular (relevancia: ${texto(fila?.relevancia_herramienta || fila?.tool_relevance) || "SUSPICIOUS_UNRELATED"}). No se eliminó automáticamente.`,
    });
  }
  return etiquetas;
}

export function camposDeProveniencia(fila) {
  return [
    ["Archivo fuente", fila?.archivo],
    ["Curso", fila?.id_curso],
    ["Sílabo", fila?.id_silabo],
    ["Logro", fila?.etiqueta_logro],
    ["Descripción fuente", fila?.descripcion_fuente],
  ].filter(([, valor]) => texto(valor));
}

export function plural(cantidad, singular, pluralizado = `${singular}s`) {
  return `${cantidad} ${cantidad === 1 ? singular : pluralizado}`;
}

export function pendientesResumen(resumen, filas, paquetes) {
  const pendientesDePaquetes = Number(resumen?.paquetes?.pendientes_por_decidir);
  if (Number.isFinite(pendientesDePaquetes) && pendientesDePaquetes > 0) return pendientesDePaquetes;
  const pendientesDirectos = Number(resumen?.pendientes_por_decidir);
  if (Number.isFinite(pendientesDirectos)) return pendientesDirectos;
  if (Array.isArray(paquetes) && paquetes.length) return paquetes.length;
  return Array.isArray(filas) ? filas.length : 0;
}

export function decisionLabel(decision) {
  if (decision === "ADD") return "Agregar al perfil";
  if (decision === "KEEP_PENDING") return "Mantener pendiente";
  return decision ? "Decisión registrada" : "Sin decisión";
}


export function componentesDe(paquete, tipo) {
  const componentes = paquete?.componentes;
  const directos = paquete?.[tipo];
  const valores = Array.isArray(directos) ? directos : componentes?.[tipo];
  return Array.isArray(valores) ? valores : [];
}

export function descripcionesFuente(componente) {
  return [
    componente?.descripcion_fuente,
    componente?.descripcion,
    componente?.description,
    componente?.source?.descripcion_fuente,
    componente?.source?.descripcion,
    componente?.source?.description,
  ];
}

export function nombreComponente(componente, tipo) {
  const esHabilidad = tipo === "habilidades" || texto(componente?.tipo).toLocaleLowerCase() === "habilidad";
  const esHerramienta = tipo === "herramientas" || texto(componente?.tipo).toLocaleLowerCase() === "herramienta";
  const esProyeccionFuenteDeHabilidad = esHabilidad && (
    componente?.source
    || texto(componente?.nombre_habilidad_fuente)
    || texto(componente?.nombre_fuente)
    || (
      texto(componente?.id_fuente)
      && !texto(componente?.id_pendiente)
      && !texto(componente?.nombre_propuesto)
      && !texto(componente?.propuesta?.nombre)
      && !componente?.canonical
    )
  );
  const descripciones = descripcionesFuente(componente);
  const candidatosCanonicos = [
    componente?.nombre_catalogo,
    componente?.catalog_name,
    componente?.nombre_canonico,
    componente?.canonical_name,
    componente?.canonical ? componente?.nombre : "",
  ];
  const candidatosPropuestos = [
    componente?.nombre_propuesto,
    componente?.propuesta?.nombre,
    esProyeccionFuenteDeHabilidad ? "" : componente?.display_name,
    esProyeccionFuenteDeHabilidad || componente?.canonical ? "" : componente?.nombre,
  ];
  const candidatosFuente = esHabilidad ? [] : [
    componente?.nombre_competencia_fuente,
    componente?.nombre_habilidad_fuente,
    componente?.nombre_herramienta_fuente,
    componente?.nombre_fuente,
    !componente?.canonical ? componente?.nombre : "",
  ];
  const nombreConDescripcionDistinta = [...candidatosCanonicos, ...candidatosPropuestos, ...candidatosFuente]
    .map((candidato) => nombreLegible(candidato, descripciones))
    .find(Boolean);
  if (nombreConDescripcionDistinta) return nombreConDescripcionDistinta;

  // Tool names are an explicit package field, not free-form source prose.
  // Keep them visible even when a backend serializes the same short name as
  // its description (for example, { nombre: "Excel", descripcion: "Excel" }).
  const candidatosHerramientaConfiables = esHerramienta ? [
    componente?.nombre_herramienta,
    componente?.source?.nombre_herramienta,
    componente?.nombre,
  ] : [];
  return candidatosHerramientaConfiables
    .map((candidato) => nombreLegible(candidato))
    .find(Boolean) || "";
}

export function descripcionComponente(componente) {
  return texto(
    componente?.descripcion
      || componente?.description
      || componente?.descripcion_fuente
      || componente?.source?.descripcion
      || componente?.source?.description
      || componente?.source?.descripcion_fuente,
  ) || "Sin descripción disponible.";
}

export function componentesLegibles(values, tipo) {
  const nombresVistos = new Set();
  return values.map((value) => {
    const nombre = nombreComponente(value, tipo);
    const clave = claveBusqueda(nombre);
    if (!nombre || nombresVistos.has(clave)) return null;
    nombresVistos.add(clave);
    return { nombre, descripcion: descripcionComponente(value) };
  }).filter(Boolean);
}
