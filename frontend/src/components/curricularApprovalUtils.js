/**
 * Pure formatting and filtering rules for curricular approval data.
 *
 * Keeping these rules outside the panel makes the rendering seam small while
 * preserving the backend's distinction between source components and explicit
 * canonical relationships.
 */

export const TIPOS = ["competencia_tecnica"];

export const ETIQUETAS = {
  competencia_tecnica: "Competencias técnicas",
  otro: "Otros pendientes",
};

export const DESCRIPCIONES = {
  competencia_tecnica:
    "Competencias técnicas inferidas desde los resultados de aprendizaje.",
  otro: "Propuestas que el backend no pudo clasificar en un tipo técnico.",
};

export const FILTROS = [
  { id: "all", label: "Todas" },
  { id: "competencia_tecnica", label: "Competencias técnicas" },
  { id: "exact", label: "Duplicados exactos" },
  { id: "semantic", label: "Posibles semánticos" },
];

export const FLAG_EXACT = "EXACT_DUPLICATE";
export const FLAG_SEMANTIC = "POSSIBLE_SEMANTIC_DUPLICATE";
export const PENDING_PROPOSAL_LABEL = "Competencia técnica pendiente";

export function texto(valor) {
  return String(valor ?? "").trim();
}

export function claveBusqueda(valor) {
  return texto(valor)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();
}

export const NOMBRE_INTERNO =
  /^(?:COMP|PROP|PROPOSAL|PEN)(?:[_-][A-Za-z0-9:-]+)+$/i;
export const NOMBRE_HASH = /^(?:sha256:)?[0-9a-f]{16,}$/i;

export function nombreLegible(valor, descripciones = []) {
  const candidato = texto(valor);
  if (
    !candidato ||
    NOMBRE_INTERNO.test(candidato) ||
    NOMBRE_HASH.test(candidato)
  )
    return "";
  const normalizado = claveBusqueda(candidato);
  if (
    descripciones.some((descripcion) => {
      const valorDescripcion = claveBusqueda(descripcion);
      return valorDescripcion && valorDescripcion === normalizado;
    })
  )
    return "";
  return candidato;
}

export function nombrePropuesto(fila) {
  const descripciones = [
    fila?.descripcion_fuente,
    fila?.source?.descripcion_fuente,
  ];
  const candidatos = [
    fila?.nombre_catalogo,
    fila?.nombre_canonico,
    fila?.nombre_propuesto,
    fila?.nombre_competencia,
    fila?.propuesta?.nombre,
    fila?.propuesta?.nombre_competencia,
    fila?.nombre_competencia_fuente,
    fila?.nombre_fuente,
  ];
  return (
    candidatos
      .map((candidato) => nombreLegible(candidato, descripciones))
      .find(Boolean) || PENDING_PROPOSAL_LABEL
  );
}

export function descripcionPropuesta(fila) {
  return (
    texto(
      fila?.propuesta?.descripcion ||
        fila?.propuesta?.descripcion_breve_competencia ||
        fila?.descripcion_breve_competencia ||
        fila?.descripcion_fuente,
    ) || "Sin descripción adicional."
  );
}

export function evidenciaDe(fila) {
  if (Array.isArray(fila?.evidencia)) {
    return fila.evidencia.map(texto).filter(Boolean);
  }
  const literal = fila?.evidencia_literal;
  if (Array.isArray(literal)) {
    const valores = literal.map(texto).filter(Boolean);
    if (valores.length) return valores;
  }
  const valor = texto(fila?.evidencia);
  return valor ? [valor] : [];
}

export function flagsDe(fila) {
  const flags = new Set(
    Array.isArray(fila?.flags) ? fila.flags.map(texto) : [],
  );
  if (fila?.duplicado_exacto || fila?.exact_duplicate) flags.add(FLAG_EXACT);
  if (fila?.posible_duplicado_semantico || fila?.semantic_duplicate)
    flags.add(FLAG_SEMANTIC);
  return flags;
}

export function autoDeduplicadaDe(fila) {
  return (
    fila?.auto_deduplicated === true ||
    fila?.auto_deduplication_state === "AUTO_DEDUPLICATED" ||
    fila?.clasificacion?.auto_deduplicated === true
  );
}

export function representanteDe(fila) {
  return texto(
    fila?.exact_duplicate_representative_id ||
      fila?.representative_id ||
      fila?.auto_dedup_representative_id ||
      fila?.clasificacion?.exact_duplicate_representative_id,
  );
}

export function tipoDe(fila) {
  const tipo = texto(fila?.tipo).toLocaleLowerCase();
  if (
    [
      "competencia_tecnica",
      "competencia técnica",
      "tecnica",
      "technical",
    ].includes(tipo)
  ) {
    return "competencia_tecnica";
  }
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
  });
  return conteos;
}

export function coincideFiltro(fila, filtro) {
  if (filtro === "all") return true;
  if (filtro === "competencia_tecnica") {
    return tipoDe(fila) === filtro;
  }
  const flags = flagsDe(fila);
  if (filtro === "exact") return flags.has(FLAG_EXACT);
  if (filtro === "semantic") return flags.has(FLAG_SEMANTIC);
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
    fila?.catalogo_ref,
    ...evidenciaDe(fila),
  ]
    .map(claveBusqueda)
    .join(" ");
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
  return etiquetas;
}

export function camposDeProveniencia(fila) {
  return [
    ["Archivo fuente", fila?.archivo],
    ["Carrera", fila?.carrera || fila?.career],
    ["Periodo", fila?.periodo || fila?.period],
    ["Curso", fila?.nombre_curso],
    ["Logro", fila?.etiqueta_logro],
    ["Descripción fuente", fila?.descripcion_fuente],
  ].filter(([, valor]) => texto(valor));
}

export function plural(cantidad, singular, pluralizado = `${singular}s`) {
  return `${cantidad} ${cantidad === 1 ? singular : pluralizado}`;
}

export function pendientesResumen(resumen, filas) {
  const pendientesDirectos = Number(resumen?.pendientes_por_decidir);
  if (Number.isFinite(pendientesDirectos)) return pendientesDirectos;
  return Array.isArray(filas) ? filas.length : 0;
}

export function decisionLabel(decision) {
  if (decision === "ADD") return "Agregar al catálogo";
  if (decision === "KEEP_PENDING") return "Mantener pendiente";
  return decision ? "Decisión registrada" : "Sin decisión";
}
