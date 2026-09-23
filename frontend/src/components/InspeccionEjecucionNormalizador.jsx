"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronRight,
  CheckCircle2,
  ExternalLink,
  History,
  LoaderCircle,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  obtenerReporteEjecucionNormalizador,
  obtenerUrlOutputNormalizador,
} from "../api/normalizador";
import CurricularApprovalPanel from "./CurricularApprovalPanel";
import Neo4jImportPanel from "./Neo4jImportPanel";

export const MAX_CSV_PREVIEW_ROWS = 500;
const MAX_PREVIEW_BYTES = 512 * 1024;
const RUTA_SALIDA_SEGURA = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[\w./-]+$/;
const CSV_PREVIEW_NAMES_TECNICOS = new Set([
  "curso.csv",
  "silabo.csv",
  "catalogo_competencias.csv",
  "catalogo_logros.csv",
  "cobertura_curricular.csv",
]);
const INSPECCION_TABS = [
  { id: "progreso", label: "Progreso" },
  { id: "revision", label: "Revisión" },
  { id: "csv", label: "CSV" },
  { id: "neo4j", label: "Neo4j" },
  { id: "auditoria", label: "Auditoría" },
];

const COMPETENCY_FINDING_CODES = [
  "COMPETENCIA_REFERENCIADA_NO_DECLARADA",
  "COMPETENCIA_DECLARADA_SIN_LOGRO",
  "COMPETENCIA_CODIGO_DUPLICADO",
  "LOGRO_SIN_COMPETENCIA",
  "LOGRO_ETIQUETA_DUPLICADA",
];

const COMPETENCY_FINDING_LABELS = {
  COMPETENCIA_REFERENCIADA_NO_DECLARADA:
    "Competencia referenciada no declarada",
  COMPETENCIA_DECLARADA_SIN_LOGRO: "Competencia declarada sin logro",
  COMPETENCIA_CODIGO_DUPLICADO: "Código de competencia duplicado",
  LOGRO_SIN_COMPETENCIA: "Logro sin competencia",
  LOGRO_ETIQUETA_DUPLICADA: "Etiqueta de logro duplicada",
};

const FINDING_GROUP_COPY = {
  logros_codigo: {
    title: "Logros tienen un código inconsistente",
    description:
      "Verifica el código contra el logro del sílabo y conserva el texto fuente para confirmar la correspondencia.",
    action: "Revisar códigos",
  },
  competencias: {
    title: "Inconsistencias en competencias",
    description:
      "Compara lo declarado en el curso con las relaciones de la malla y confirma qué vínculo debe conservarse.",
    action: "Revisar relaciones",
  },
  cactus_sin_silabo: {
    title: "Cursos sin sílabo descargable",
    description:
      "Carga o vincula el documento fuente y vuelve a ejecutar la extracción para completar la cobertura curricular.",
    action: "Revisar cursos afectados",
  },
  otros: {
    title: "Otros avisos registrados",
    description:
      "Hay avisos adicionales de la ejecución. Abre el detalle para revisar su origen y la acción recomendada.",
    action: "Ver detalle",
  },
};

export function parseCsvPreview(texto, limite = MAX_CSV_PREVIEW_ROWS) {
  const filas = [];
  let fila = [];
  let campo = "";
  let entreComillas = false;
  let filasAcotadas = false;

  for (let indice = 0; indice < texto.length; indice += 1) {
    const caracter = texto[indice];
    if (entreComillas) {
      if (caracter === '"') {
        if (texto[indice + 1] === '"') {
          campo += '"';
          indice += 1;
        } else {
          entreComillas = false;
        }
      } else {
        campo += caracter;
      }
      continue;
    }
    if (caracter === '"' && campo === "") {
      entreComillas = true;
    } else if (caracter === ",") {
      fila.push(campo);
      campo = "";
    } else if (caracter === "\n") {
      fila.push(campo.replace(/\r$/, ""));
      filas.push(fila);
      fila = [];
      campo = "";
      if (filas.length >= limite + 1) {
        filasAcotadas = true;
        break;
      }
    } else {
      campo += caracter;
    }
  }

  if (!filasAcotadas && (campo !== "" || fila.length)) {
    fila.push(campo.replace(/\r$/, ""));
    filas.push(fila);
  }

  const encabezados = filas[0] || [];
  return {
    encabezados,
    filas: filas.slice(1, limite + 1),
    totalFilas: Math.max(0, filas.length - 1),
    truncado: filasAcotadas,
  };
}

function rutaSalidaSegura(archivo) {
  return typeof archivo === "string" && RUTA_SALIDA_SEGURA.test(archivo);
}

function nombreArchivo(archivo) {
  return (
    String(archivo || "")
      .split("/")
      .pop() || "Salida sin nombre"
  );
}

function nombresCsvPreview() {
  return CSV_PREVIEW_NAMES_TECNICOS;
}

function textoParametro(valor, fallback) {
  if (typeof valor === "string" && valor.trim()) return valor.trim();
  if (typeof valor === "number" && Number.isFinite(valor)) return String(valor);
  return fallback;
}

function parametrosDe(manifest) {
  return {
    carrera: textoParametro(
      manifest?.parametros?.carrera ??
        manifest?.carrera ??
        manifest?.metadata?.carrera,
      "Carrera no indicada",
    ),
    periodo: textoParametro(
      manifest?.parametros?.periodo ??
        manifest?.periodo ??
        manifest?.metadata?.periodo,
      "Periodo no indicado",
    ),
  };
}

function salidasDe(manifest) {
  const fuentes = [manifest?.outputs, manifest?.limpieza_silabos?.outputs];
  const salidas = [];
  const vistas = new Set();
  for (const fuente of fuentes) {
    if (!Array.isArray(fuente)) continue;
    for (const salida of fuente) {
      if (
        !salida ||
        !rutaSalidaSegura(salida.archivo) ||
        vistas.has(salida.archivo)
      )
        continue;
      vistas.add(salida.archivo);
      salidas.push(salida);
    }
  }
  return salidas;
}

function reportePorNombre(reportes, nombres) {
  const nombresPermitidos = new Set(
    nombres.map((nombre) => nombre.toLowerCase()),
  );
  for (const [archivo, reporte] of Object.entries(reportes || {})) {
    if (nombresPermitidos.has(nombreArchivo(archivo).toLowerCase()))
      return reporte;
  }
  return null;
}

function objetoReporte(reporte) {
  return reporte && typeof reporte === "object" && !Array.isArray(reporte)
    ? reporte
    : null;
}

function aprobacionCurricularDe(manifest) {
  return objetoReporte(manifest?.aprobacion_curricular);
}

function releaseGateDe(manifest, reportes) {
  const directo = objetoReporte(
    manifest?.release_gate || manifest?.limpieza_silabos?.release_gate,
  );
  if (directo) return directo;
  const reporte = objetoReporte(
    reportePorNombre(reportes, ["release_gate.json"]),
  );
  return reporte?.release_gate || reporte?.gate || reporte;
}

function filasDePendientes(reportes) {
  const reporte = reportePorNombre(reportes, ["propuestas_tecnicas.jsonl"]);
  if (Array.isArray(reporte))
    return reporte.filter((fila) => fila && typeof fila === "object");
  for (const clave of ["filas", "pendientes", "items", "propuestas"]) {
    if (Array.isArray(reporte?.[clave]))
      return reporte[clave].filter((fila) => fila && typeof fila === "object");
  }
  return [];
}

function numeroNoNegativo(...valores) {
  for (const valor of valores) {
    if (
      valor === null ||
      valor === undefined ||
      valor === "" ||
      typeof valor === "boolean"
    )
      continue;
    const numero = Number(valor);
    if (Number.isFinite(numero) && numero >= 0) return Math.floor(numero);
  }
  return null;
}

function filaResuelta(fila) {
  if (
    fila?.requiere_decision === false ||
    fila?.pendiente_por_decidir === false
  )
    return true;
  const estado = String(
    fila?.estado ||
      fila?.status ||
      fila?.decision_estado ||
      fila?.decision ||
      "",
  ).toUpperCase();
  return [
    "ADD",
    "KEEP_PENDING",
    "ACEPTADA",
    "APROBADA",
    "APROBADO",
    "RESUELTA",
    "RESUELTO",
    "DECIDIDA",
  ].includes(estado);
}

function pendientesPorDecidirDe(manifest, reportes, aprobacion, gate) {
  const explicitos = numeroNoNegativo(
    aprobacion?.pendientes_por_decidir,
    aprobacion?.pending_decision,
    gate?.checks?.approval?.pending_count,
    gate?.checks?.approval?.pending_decision,
    gate?.checks?.approval?.pendingDecision,
  );
  if (explicitos !== null) return explicitos;
  return (
    filasDePendientes(reportes).filter((fila) => !filaResuelta(fila)).length ||
    (aprobacion?.requiere_decision === true ||
    manifest?.requiere_decision === true
      ? 1
      : 0)
  );
}

function requiereDecisionCurricular(manifest, aprobacion, gate, pendientes) {
  return (
    aprobacion?.requiere_decision === true ||
    manifest?.requiere_decision === true ||
    numeroNoNegativo(gate?.checks?.approval?.pending_count) > 0 ||
    numeroNoNegativo(gate?.checks?.approval?.pending_decision) > 0 ||
    pendientes > 0
  );
}

function salidasCanonicasDe(salidas, nombres) {
  return salidas.filter((salida) =>
    nombres.has(nombreArchivo(salida?.archivo).toLowerCase()),
  );
}

function vistasPreviasCompletas(salidas, previews, nombres) {
  const salidasCanonicas = salidasCanonicasDe(salidas, nombres);
  return [...nombres].every((nombre) => {
    const salida = salidasCanonicas.find(
      (item) => nombreArchivo(item.archivo).toLowerCase() === nombre,
    );
    const preview = salida ? previews?.[salida.archivo] : null;
    return (
      preview &&
      !preview.error &&
      Array.isArray(preview.encabezados) &&
      preview.encabezados.length > 0
    );
  });
}

function tieneFalloAnalisisTecnico(manifest, gate) {
  const blockers = Array.isArray(gate?.blockers) ? gate.blockers : [];
  const estadoAnalisis = String(gate?.checks?.analysis?.state || "").toUpperCase();
  return (
    blockers.includes("TECHNICAL_ANALYSIS_FAILED") ||
    estadoAnalisis === "FALLBACK_DETERMINISTA" ||
    (Array.isArray(manifest?.hallazgos) &&
      manifest.hallazgos.some(
        (hallazgo) =>
          findingCode(hallazgo) === "ANALISTA_TECNICO_NO_DISPONIBLE",
      ))
  );
}

function releaseGatePermiteImportar(gate, salidas, previews) {
  const nombres = CSV_PREVIEW_NAMES_TECNICOS;
  const salidasCanonicas = salidasCanonicasDe(salidas, nombres);
  const nombresDeclarados = new Set(
    salidasCanonicas.map((salida) =>
      nombreArchivo(salida.archivo).toLowerCase(),
    ),
  );
  const contratoCompleto =
    nombresDeclarados.size === nombres.size &&
    [...nombres].every((nombre) => nombresDeclarados.has(nombre));
  return (
    gate?.decision === "ALLOW_IMPORT" &&
    contratoCompleto &&
    vistasPreviasCompletas(salidas, previews, nombres)
  );
}

function findingSearchText(hallazgo) {
  return [
    hallazgo?.codigo,
    hallazgo?.mensaje,
    hallazgo?.detalle,
    hallazgo?.fuente,
    hallazgo?.origen,
    hallazgo?.etapa,
    hallazgo?.proceso,
  ]
    .map((valor) => String(valor || ""))
    .join(" ")
    .toUpperCase();
}

function findingCode(hallazgo) {
  return String(hallazgo?.codigo || "")
    .trim()
    .toUpperCase();
}

function isBlockingFinding(hallazgo) {
  return (
    hallazgo?.bloqueante === true ||
    hallazgo?.blocking === true ||
    hallazgo?.bloquea_publicacion === true ||
    hallazgo?.block_import === true
  );
}

function hallazgosDe(manifest, reportes) {
  const hallazgosManifest = Array.isArray(manifest?.hallazgos)
    ? manifest.hallazgos.filter(
        (hallazgo) => hallazgo && typeof hallazgo === "object",
      )
    : [];
  const reporteExtraccion = objetoReporte(
    reportePorNombre(reportes, ["extraccion_cactus.json"]),
  );
  const erroresCactus = Array.isArray(reporteExtraccion?.errores)
    ? reporteExtraccion.errores
    : [];
  const hallazgosCactus = erroresCactus
    .map((error) => {
      if (typeof error === "string") {
        return {
          codigo: "EXTRACCION_CACTUS_INCOMPLETA",
          mensaje: error,
          severidad: "error",
          fuente: "extraccion_cactus",
          origen: "extraccion_cactus",
        };
      }
      if (!error || typeof error !== "object") return null;
      const codigo = error.codigo || error.code;
      return {
        ...error,
        codigo,
        mensaje: error.mensaje || error.message,
        // A missing syllabus is a coverage condition, not an extraction failure.
        severidad:
          codigo === "CACTUS_SIN_SILABO"
            ? "warning"
            : error.severidad || "error",
        fuente: error.fuente || "extraccion_cactus",
        origen: error.origen || "extraccion_cactus",
      };
    })
    .filter((hallazgo) => hallazgo && (hallazgo.codigo || hallazgo.mensaje));

  const resultado = [...hallazgosManifest];
  const tieneExtraccionIncompleta = hallazgosManifest.some(
    (hallazgo) => findingCode(hallazgo) === "EXTRACCION_CACTUS_INCOMPLETA",
  );
  let agregoExtraccionIncompleta = tieneExtraccionIncompleta;
  hallazgosCactus.forEach((hallazgo) => {
    if (findingCode(hallazgo) === "EXTRACCION_CACTUS_INCOMPLETA") {
      if (agregoExtraccionIncompleta) return;
      agregoExtraccionIncompleta = true;
    }
    resultado.push(hallazgo);
  });
  return resultado;
}

function isCompetencyFinding(hallazgo) {
  const texto = findingSearchText(hallazgo);
  return COMPETENCY_FINDING_CODES.some((codigo) => texto.includes(codigo));
}

function isOutcomeFinding(hallazgo) {
  const texto = findingSearchText(hallazgo);
  return /\bLOGRO_[A-Z0-9_]+\b/.test(texto) && !isCompetencyFinding(hallazgo);
}

function isCactusSyllabusFinding(hallazgo) {
  return findingCode(hallazgo) === "CACTUS_SIN_SILABO";
}

function hallazgosAccionablesDe(hallazgos) {
  const tieneDetalleCactus = hallazgos.some(isCactusSyllabusFinding);
  return hallazgos.filter((hallazgo) => {
    const codigo = findingCode(hallazgo);
    if (codigo === "EXTRACCION_CACTUS_INCOMPLETA" && tieneDetalleCactus)
      return false;
    return true;
  });
}

function findingLink(hallazgo) {
  const candidatos = [
    hallazgo?.url,
    hallazgo?.enlace,
    hallazgo?.link,
    hallazgo?.href,
    hallazgo?.afectados_url,
    hallazgo?.affected_url,
  ];
  return candidatos.find(
    (valor) => typeof valor === "string" && /^(?:https?:\/\/|\/)/.test(valor),
  );
}

function findingAffectedCount(hallazgo) {
  const afectados =
    hallazgo?.afectados || hallazgo?.affected || hallazgo?.items;
  if (Array.isArray(afectados)) return afectados.length;
  return numeroNoNegativo(
    hallazgo?.cantidad_afectados,
    hallazgo?.affected_count,
    hallazgo?.count,
    hallazgo?.total,
  );
}

function getCompetencySubgroups(hallazgos) {
  return COMPETENCY_FINDING_CODES.map((codigo) => ({
    codigo,
    etiqueta: COMPETENCY_FINDING_LABELS[codigo],
    cantidad: hallazgos.filter((hallazgo) =>
      findingSearchText(hallazgo).includes(codigo),
    ).length,
  })).filter((grupo) => grupo.cantidad > 0);
}

function groupFindings(hallazgos) {
  const gruposBase = [
    {
      id: "logros_codigo",
      coincide: isOutcomeFinding,
    },
    {
      id: "competencias",
      coincide: isCompetencyFinding,
    },
    {
      id: "cactus_sin_silabo",
      coincide: isCactusSyllabusFinding,
    },
  ];
  const asignados = new Set();
  const grupos = gruposBase
    .map((grupo) => {
      const items = hallazgos.filter((hallazgo) => {
        const coincide = grupo.coincide(hallazgo);
        if (coincide) asignados.add(hallazgo);
        return coincide;
      });
      return {
        ...grupo,
        ...FINDING_GROUP_COPY[grupo.id],
        items,
        cantidad: items.length,
        subgrupos:
          grupo.id === "competencias" ? getCompetencySubgroups(items) : [],
      };
    })
    .filter((grupo) => grupo.cantidad > 0);
  const otros = hallazgos.filter((hallazgo) => !asignados.has(hallazgo));
  if (otros.length) {
    grupos.push({
      id: "otros",
      ...FINDING_GROUP_COPY.otros,
      items: otros,
      cantidad: otros.length,
      subgrupos: [],
    });
  }
  return grupos;
}

function conteosDe(manifest) {
  const salidas = salidasDe(manifest);
  const registrosDe = (nombre) => {
    const salida = salidas.find(
      (item) => nombreArchivo(item.archivo).toLowerCase() === nombre,
    );
    return salida?.registros ?? null;
  };
  return [
    { clave: "cursos", etiqueta: "cursos", valor: registrosDe("curso.csv") },
    { clave: "silabos", etiqueta: "sílabos", valor: registrosDe("silabo.csv") },
    {
      clave: "competencias",
      etiqueta: "competencias técnicas",
      valor: registrosDe("catalogo_competencias.csv"),
    },
    {
      clave: "logros",
      etiqueta: "logros",
      valor: registrosDe("catalogo_logros.csv"),
    },
    {
      clave: "relaciones",
      etiqueta: "relaciones de cobertura",
      valor: registrosDe("cobertura_curricular.csv"),
    },
  ];
}

const ESTADOS_ACTIVOS = new Set([
  "recibido",
  "validando",
  "limpiando",
  "normalizando",
]);
const INTERVALO_POLLING_MS = 3000;

function estadoNormalizado(estado) {
  return String(estado || "")
    .trim()
    .toLowerCase();
}

function esEstadoActivo(estado) {
  return ESTADOS_ACTIVOS.has(estadoNormalizado(estado));
}

function estadoLegible(estado, contexto = {}) {
  const clave = estadoNormalizado(estado);
  if (["limpiado", "limpiado_con_advertencias"].includes(clave)) {
    if (contexto.csvCanonicosListos) {
      return clave === "limpiado_con_advertencias"
        ? "CSV técnicos listos con advertencias"
        : "CSV técnicos listos";
    }
    if (contexto.pendientesPorDecidir > 0 || contexto.requiereDecision)
      return "Revisión técnica pendiente";
    return contexto.gateDecision && contexto.gateDecision !== "ALLOW_IMPORT"
      ? "Revisión técnica persistida; publicación bloqueada"
      : "Revisión técnica persistida; CSV técnicos pendientes";
  }
  return (
    {
      recibido: "Ejecución recibida",
      validando: "Validando estructura",
      validado: "Validación completada",
      validado_con_advertencias: "Validación completada con advertencias",
      limpiando: "Limpiando datos",
      limpiado: "Limpieza completada",
      limpiado_con_advertencias: "Limpieza completada con advertencias",
      normalizando: "Procesando resultados técnicos",
      normalizado: "Resultados técnicos completos",
      normalizado_con_advertencias:
        "Resultados técnicos completos con advertencias",
      cancelado: "Procesamiento cancelado",
      error: "Error de ejecución",
      rechazado: "Entrada rechazada",
      no_publicado: "No publicado",
    }[estadoNormalizado(estado)] ||
    estado ||
    "Estado no disponible"
  );
}

function progresoActivoDe(manifest) {
  const progreso = manifest?.progreso_llm;
  if (!progreso || typeof progreso !== "object") return null;
  const chunksCompletados = Number(progreso.chunks_completados);
  const chunksTotales = Number(progreso.chunks_totales);
  const tieneChunks = Number.isFinite(chunksTotales) && chunksTotales > 0;
  const eventos = Array.isArray(progreso.eventos) ? progreso.eventos : [];
  return {
    chunksCompletados: Number.isFinite(chunksCompletados)
      ? Math.max(0, chunksCompletados)
      : 0,
    chunksTotales: tieneChunks ? chunksTotales : 0,
    eventos: eventos.length,
    porcentaje: tieneChunks
      ? Math.min(
          100,
          Math.round(
            (Math.max(0, chunksCompletados || 0) / chunksTotales) * 100,
          ),
        )
      : 0,
  };
}

async function leerRespuestaAcotada(respuesta) {
  if (!respuesta.body?.getReader) {
    return (await respuesta.text()).slice(0, MAX_PREVIEW_BYTES);
  }
  const lector = respuesta.body.getReader();
  const decodificador = new TextDecoder();
  const partes = [];
  let leidos = 0;
  try {
    while (leidos < MAX_PREVIEW_BYTES) {
      const bloque = await lector.read();
      if (bloque.done) break;
      const bytes = bloque.value || new Uint8Array();
      const restante = MAX_PREVIEW_BYTES - leidos;
      const acotado =
        bytes.byteLength > restante ? bytes.slice(0, restante) : bytes;
      partes.push(decodificador.decode(acotado, { stream: true }));
      leidos += acotado.byteLength;
      if (acotado.byteLength < bytes.byteLength) break;
    }
  } finally {
    try {
      await lector.cancel();
    } catch {
      // La vista sigue siendo útil aunque el navegador ya haya cerrado el stream.
    }
  }
  partes.push(decodificador.decode());
  return partes.join("");
}

async function cargarPreviewCsv(idEjecucion, salida) {
  const url = obtenerUrlOutputNormalizador(idEjecucion, salida.archivo);
  const respuesta = await fetch(url);
  if (!respuesta.ok)
    throw new Error(`No se pudo leer ${nombreArchivo(salida.archivo)}.`);
  const texto = await leerRespuestaAcotada(respuesta);
  return { ...parseCsvPreview(texto), url };
}

function faseAutomaticaDe({
  ejecucionActiva,
  mostrarAprobacion,
  requiereAuditoria,
  csvCanonicosListos,
  cantidadErrores,
}) {
  if (ejecucionActiva) return "progreso";
  if (mostrarAprobacion) return "revision";
  if (requiereAuditoria || (!csvCanonicosListos && cantidadErrores > 0))
    return "auditoria";
  if (csvCanonicosListos) return "csv";
  return "progreso";
}

function mensajeBloqueoNeo4j(ejecucionActiva, mostrarAprobacion) {
  if (ejecucionActiva)
    return "La importación se habilitará cuando la ejecución finalice.";
  if (mostrarAprobacion)
    return "Resolvé las decisiones técnicas pendientes antes de publicar.";
  return "El release gate todavía no certifica los CSV técnicos para importar.";
}

function Check({ children, ok = true }) {
  return (
    <li
      className={`flex items-start gap-2 rounded-xl border px-3.5 py-3 text-sm ${ok ? "border-line bg-fondo text-ink" : "border-ulima/35 bg-ulima/5 text-ink"}`}
    >
      {ok ? (
        <CheckCircle2 className="mt-0.5 shrink-0 text-muted" size={17} />
      ) : (
        <AlertTriangle className="mt-0.5 shrink-0 text-ulima" size={17} />
      )}
      <span>{children}</span>
    </li>
  );
}

function InspectionTabs({ activeTab, onChange }) {
  const tabRefs = useRef([]);

  const moveTab = (indice) => {
    const siguiente =
      INSPECCION_TABS[
        (indice + INSPECCION_TABS.length) % INSPECCION_TABS.length
      ];
    onChange(siguiente.id);
    tabRefs.current[indice]?.focus();
  };

  const handleKeyDown = (event, indice) => {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveTab((indice + 1) % INSPECCION_TABS.length);
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveTab((indice - 1 + INSPECCION_TABS.length) % INSPECCION_TABS.length);
    }
    if (event.key === "Home") {
      event.preventDefault();
      moveTab(0);
    }
    if (event.key === "End") {
      event.preventDefault();
      moveTab(INSPECCION_TABS.length - 1);
    }
  };

  return (
    <nav
      className="mt-5 border-y border-line"
      aria-label="Secciones de la inspección"
    >
      <div
        className="flex gap-0 overflow-x-auto"
        role="tablist"
        aria-label="Secciones de la inspección"
      >
        {INSPECCION_TABS.map((tab, indice) => {
          const activa = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={(elemento) => {
                tabRefs.current[indice] = elemento;
              }}
              id={`tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={activa}
              aria-controls={`panel-${tab.id}`}
              tabIndex={activa ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, indice)}
              className={`relative shrink-0 border-b-2 border-transparent px-4 py-3 text-sm font-bold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/40 focus-visible:ring-offset-2 ${activa ? "bg-ulima/5 font-extrabold text-institucional-negro" : "text-muted hover:bg-fondo hover:text-ink"}`}
            >
              {tab.label}
              {activa ? (
                <span
                  className="absolute inset-x-3 bottom-[-1px] h-0.5 bg-institucional-naranja"
                  aria-hidden="true"
                />
              ) : null}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function getFindingGroupColors(grupo) {
  return grupo.items.some(isBlockingFinding)
    ? {
        wrapper: "border-red-200 bg-red-50/40",
        icon: "border-red-200 bg-red-50 text-red-700",
        title: "text-ink",
        body: "text-muted",
      }
    : {
        wrapper: "border-line bg-paper",
        icon: "border-ulima/30 bg-ulima/5 text-ulima",
        title: "text-ink",
        body: "text-muted",
      };
}

function FindingGroupCard({ grupo, detailed = false, onOpen }) {
  const colores = getFindingGroupColors(grupo);
  const tieneBloqueo = grupo.items.some(isBlockingFinding);
  const hallazgoConEnlace = grupo.items.find((hallazgo) =>
    findingLink(hallazgo),
  );
  const affectedCount = grupo.items
    .map(findingAffectedCount)
    .find((cantidad) => cantidad !== null && cantidad !== undefined);
  return (
    <article className={`rounded-2xl border p-4 sm:p-5 ${colores.wrapper}`}>
      <div className="flex items-start gap-3">
        <span
          className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl border ${colores.icon}`}
          aria-hidden="true"
        >
          {tieneBloqueo ? <XCircle size={18} /> : <AlertTriangle size={18} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className={`text-base font-extrabold ${colores.title}`}>
              {grupo.title}
            </h3>
            <span className={`font-mono text-[11px] font-bold ${colores.body}`}>
              {grupo.cantidad} {grupo.cantidad === 1 ? "aviso" : "avisos"}
            </span>
          </div>
          <p className={`mt-2 max-w-3xl text-sm leading-6 ${colores.body}`}>
            {grupo.description}
          </p>
          {affectedCount !== null && affectedCount !== undefined ? (
            <p className={`mt-2 text-xs font-semibold ${colores.body}`}>
              Afecta a {affectedCount.toLocaleString("es-PE")}{" "}
              {affectedCount === 1 ? "elemento" : "elementos"} reportado
              {affectedCount === 1 ? "" : "s"}.
            </p>
          ) : null}
          {grupo.subgrupos.length ? (
            <ul
              className="mt-3 grid gap-2 sm:grid-cols-2"
              aria-label="Detalle de inconsistencias en competencias"
            >
              {grupo.subgrupos.map((subgrupo) => (
                <li
                  key={subgrupo.codigo}
                  className="rounded-xl border border-line bg-fondo px-3 py-2 text-xs text-ink"
                >
                  <span className="font-bold">{subgrupo.etiqueta}</span>
                  <span className="ml-2 font-mono text-[11px]">
                    {subgrupo.cantidad}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-bold">
            {hallazgoConEnlace ? (
              <a
                href={findingLink(hallazgoConEnlace)}
                target={
                  findingLink(hallazgoConEnlace).startsWith("http")
                    ? "_blank"
                    : undefined
                }
                rel={
                  findingLink(hallazgoConEnlace).startsWith("http")
                    ? "noopener noreferrer"
                    : undefined
                }
                className={`inline-flex items-center gap-1 text-ink underline decoration-current/30 underline-offset-4 transition hover:text-ulima ${colores.title}`}
              >
                Ver afectados <ChevronRight size={14} aria-hidden="true" />
              </a>
            ) : null}
            {onOpen ? (
              <button
                type="button"
                onClick={onOpen}
                className={`inline-flex items-center gap-1 underline decoration-current/30 underline-offset-4 transition hover:text-ulima ${colores.title}`}
              >
                {grupo.action} <ChevronRight size={14} aria-hidden="true" />
              </button>
            ) : null}
          </div>
          {detailed ? (
            <details className="mt-4 rounded-xl border border-line bg-fondo">
              <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-bold text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/40 focus-visible:ring-inset">
                Ver trazabilidad y evidencia
              </summary>
              <div className="border-t border-line px-3 py-3">
                <ul className="space-y-3">
                  {grupo.items.map((hallazgo, indice) => (
                    <li
                      key={`${findingCode(hallazgo) || "hallazgo"}-${indice}`}
                      className="text-xs leading-5 text-muted"
                    >
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-ink">
                        {findingCode(hallazgo) || "SIN_CODIGO"} ·{" "}
                        {hallazgo?.severidad || "warning"}
                      </p>
                      <p className="mt-1">
                        {hallazgo?.mensaje ||
                          hallazgo?.detalle ||
                          "Hallazgo sin detalle."}
                      </p>
                      {hallazgo?.detalle &&
                      hallazgo.detalle !== hallazgo.mensaje ? (
                        <p className="mt-1 text-muted/80">{hallazgo.detalle}</p>
                      ) : null}
                      {findingLink(hallazgo) ? (
                        <a
                          href={findingLink(hallazgo)}
                          className="mt-1 inline-flex font-bold text-ulima underline underline-offset-2"
                        >
                          Abrir afectados
                        </a>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function CsvOutputsPanel({
  idEjecucion,
  csvs,
  previews,
  ejecucionActiva,
  csvCanonicosListos,
}) {
  return (
    <section
      className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6"
      aria-labelledby="csv-outputs-title"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted">
            Salidas publicadas
          </p>
          <h2
            id="csv-outputs-title"
            className="mt-2 text-xl font-extrabold tracking-[-0.025em]"
          >
            Archivos CSV
          </h2>
        </div>
        <span className="font-mono text-xs font-bold text-muted">
          {csvs.length} {csvs.length === 1 ? "archivo" : "archivos"}
        </span>
      </div>

      {ejecucionActiva ? (
        <p className="mt-5 rounded-xl border border-line bg-fondo px-3.5 py-3 text-sm text-muted">
          Las salidas se habilitarán automáticamente cuando finalice la
          ejecución.
        </p>
      ) : csvs.length ? (
        <div className="mt-5 space-y-4">
          {csvCanonicosListos ? null : (
            <p className="rounded-xl border border-ulima/25 bg-ulima/5 px-3.5 py-3 text-sm text-ink">
              Los archivos declarados se muestran para inspección, pero el
              release gate aún no permite publicarlos en Neo4j.
            </p>
          )}
          {csvs.map((salida) => {
            const nombre = nombreArchivo(salida.archivo);
            const preview = previews[salida.archivo];
            const url =
              preview?.url ||
              obtenerUrlOutputNormalizador(idEjecucion, salida.archivo);
            return (
              <article
                key={salida.archivo}
                className="overflow-hidden rounded-2xl border border-line bg-fondo"
              >
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-extrabold text-ink">
                      {nombre}
                    </h3>
                    <p className="mt-1 font-mono text-[10px] text-muted">
                      {Number.isFinite(Number(salida.registros))
                        ? `${Number(salida.registros).toLocaleString("es-PE")} registros`
                        : salida.tipo || "CSV"}
                    </p>
                  </div>
                  <a
                    href={url}
                    download={nombre}
                    aria-label={`Descargar ${nombre}`}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/30"
                  >
                    Descargar <ExternalLink size={13} aria-hidden="true" />
                  </a>
                </div>
                {preview?.error ? (
                  <p className="px-4 py-3 text-xs text-red-700">
                    {preview.error}
                  </p>
                ) : preview?.encabezados?.length ? (
                  <div className="max-h-80 overflow-auto" tabIndex={0}>
                    <table className="min-w-full border-collapse text-left text-xs">
                      <thead className="sticky top-0 bg-paper">
                        <tr>
                          {preview.encabezados.map((encabezado, indice) => (
                            <th
                              key={`${encabezado}-${indice}`}
                              scope="col"
                              className="whitespace-nowrap border-b border-line px-3 py-2 font-bold text-ink"
                            >
                              {encabezado || `Columna ${indice + 1}`}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.filas.map((fila, filaIndice) => (
                          <tr key={filaIndice} className="odd:bg-paper/60">
                            {preview.encabezados.map((_, columnaIndice) => (
                              <td
                                key={columnaIndice}
                                className="max-w-80 border-b border-line/70 px-3 py-2 align-top text-muted"
                              >
                                {fila[columnaIndice] || "—"}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="px-4 py-3 text-xs text-muted">
                    Vista previa no disponible; el archivo puede descargarse.
                  </p>
                )}
                {preview?.truncado ? (
                  <p className="border-t border-line px-4 py-2 text-[11px] text-muted">
                    Vista previa limitada a {MAX_CSV_PREVIEW_ROWS} filas.
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <p className="mt-5 rounded-xl border border-dashed border-line px-3.5 py-4 text-sm text-muted">
          Esta ejecución todavía no declara archivos CSV accesibles.
        </p>
      )}
    </section>
  );
}

function FindingsDetail({ grupos, total, errors, warnings }) {
  return (
    <section
      className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6"
      aria-labelledby="hallazgos-title"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted">
            Detalle agrupado
          </p>
          <h2
            id="hallazgos-title"
            className="mt-2 flex items-center gap-2 text-xl font-extrabold"
          >
            <AlertTriangle className="text-ulima" size={20} /> Advertencias y
            errores
          </h2>
        </div>
        <span className="font-mono text-xs font-bold text-muted">
          {total} {total === 1 ? "hallazgo" : "hallazgos"} · {errors} errores ·{" "}
          {warnings} advertencias
        </span>
      </div>
      {grupos.length ? (
        <div className="mt-5 space-y-3">
          {grupos.map((grupo) => (
            <FindingGroupCard key={grupo.id} grupo={grupo} detailed />
          ))}
        </div>
      ) : (
        <p className="mt-5 rounded-xl border border-line bg-fondo px-3.5 py-3 text-sm text-muted">
          No hay advertencias ni errores registrados en esta ejecución.
        </p>
      )}
    </section>
  );
}

export default function InspeccionEjecucionNormalizador({ idEjecucion }) {
  const [estado, setEstado] = useState({
    cargando: true,
    reporte: null,
    error: "",
    previews: {},
  });
  const [revisionReporte, setRevisionReporte] = useState(0);
  const [activeTab, setActiveTab] = useState("progreso");
  const faseAutomaticaRef = useRef("");

  useEffect(() => {
    let activo = true;
    let temporizador = null;
    let ultimoReporte = null;

    function programarPolling() {
      if (!activo || temporizador !== null) return;
      temporizador = setTimeout(() => {
        temporizador = null;
        cargarReporte();
      }, INTERVALO_POLLING_MS);
    }

    async function cargarReporte(inicial = false) {
      if (!activo) return;
      if (inicial)
        setEstado({ cargando: true, reporte: null, error: "", previews: {} });
      try {
        const reporte = await obtenerReporteEjecucionNormalizador(idEjecucion);
        if (!activo) return;
        ultimoReporte = reporte;
        if (esEstadoActivo(reporte?.manifest?.estado)) {
          setEstado((anterior) => ({
            cargando: false,
            reporte,
            error: "",
            previews: anterior.previews,
          }));
          programarPolling();
          return;
        }
        const salidas = salidasDe(reporte?.manifest);
        const csvs = salidas.filter((salida) =>
          salida.archivo.toLowerCase().endsWith(".csv"),
        );
        const nombresPreview = nombresCsvPreview(reporte?.manifest);
        const csvsParaPreview = csvs.filter((salida) =>
          nombresPreview.has(nombreArchivo(salida.archivo).toLowerCase()),
        );
        const resultados = await Promise.all(
          csvsParaPreview.map(async (salida) => {
            try {
              return [
                salida.archivo,
                await cargarPreviewCsv(idEjecucion, salida),
              ];
            } catch (error) {
              return [
                salida.archivo,
                {
                  error: error.message || "No se pudo cargar la vista previa.",
                },
              ];
            }
          }),
        );
        if (activo)
          setEstado({
            cargando: false,
            reporte,
            error: "",
            previews: Object.fromEntries(resultados),
          });
      } catch (error) {
        if (!activo) return;
        setEstado((anterior) => ({
          cargando: false,
          reporte: anterior.reporte || ultimoReporte,
          error: error.message || "No se pudo cargar la inspección.",
          previews: anterior.previews,
        }));
        if (esEstadoActivo(ultimoReporte?.manifest?.estado)) programarPolling();
      }
    }
    cargarReporte(true);
    return () => {
      activo = false;
      if (temporizador !== null) clearTimeout(temporizador);
    };
  }, [idEjecucion, revisionReporte]);

  useEffect(() => {
    faseAutomaticaRef.current = "";
    setActiveTab("progreso");
  }, [idEjecucion]);

  const manifest = estado.reporte?.manifest || {};
  const reportes = estado.reporte?.reportes || {};
  const parametros = parametrosDe(manifest);
  const salidas = useMemo(() => salidasDe(manifest), [manifest]);
  const csvs = salidas.filter((salida) =>
    salida.archivo.toLowerCase().endsWith(".csv"),
  );
  const aprobacionCurricular = aprobacionCurricularDe(manifest);
  const releaseGate = releaseGateDe(manifest, reportes);
  const pendientesPorDecidir = pendientesPorDecidirDe(
    manifest,
    reportes,
    aprobacionCurricular,
    releaseGate,
  );
  const requiereDecision = requiereDecisionCurricular(
    manifest,
    aprobacionCurricular,
    releaseGate,
    pendientesPorDecidir,
  );
  const csvCanonicosListos = releaseGatePermiteImportar(
    releaseGate,
    salidas,
    estado.previews,
  );
  const analisisTecnicoFallido = tieneFalloAnalisisTecnico(
    manifest,
    releaseGate,
  );
  let mensajePublicacion =
    "Los resultados se presentan como evidencia de solo lectura.";
  let publicacionBloqueada = false;
  if (analisisTecnicoFallido) {
    mensajePublicacion =
      "El análisis técnico no estuvo disponible; la publicación quedó bloqueada por el release gate.";
    publicacionBloqueada = true;
  } else if (manifest.limpieza_silabos?.publicable === false) {
    mensajePublicacion =
      "La ejecución quedó marcada como no publicable; los artefactos siguen disponibles para revisión.";
    publicacionBloqueada = true;
  }
  const mostrarAprobacionCurricular =
    !esEstadoActivo(manifest.estado) &&
    (requiereDecision ||
      (!aprobacionCurricular &&
        filasDePendientes(reportes).some((fila) => !filaResuelta(fila))));
  const hallazgos = useMemo(
    () => hallazgosDe(manifest, reportes),
    [manifest, reportes],
  );
  const hallazgosAccionables = useMemo(
    () => hallazgosAccionablesDe(hallazgos),
    [hallazgos],
  );
  const advertencias = hallazgosAccionables.filter(
    (hallazgo) => hallazgo?.severidad === "warning",
  );
  const errores = hallazgosAccionables.filter(
    (hallazgo) => hallazgo?.severidad === "error",
  );
  const conteos = conteosDe(manifest);
  const validacion = manifest.validacion_silabos || manifest.validacion;
  const ejecucionActiva = esEstadoActivo(manifest.estado);
  const progresoActivo = progresoActivoDe(manifest);
  const estadoActual = estadoNormalizado(manifest.estado);
  const estadoError = ["error", "rechazado"].includes(estadoActual);
  const requiereAuditoria = estadoError || estadoActual === "no_publicado";
  const gruposHallazgos = useMemo(
    () => groupFindings(hallazgosAccionables),
    [hallazgosAccionables],
  );
  const contextoEstado = {
    csvCanonicosListos,
    pendientesPorDecidir,
    requiereDecision,
    gateDecision: releaseGate?.decision,
  };
  const faseAutomatica = faseAutomaticaDe({
    ejecucionActiva,
    mostrarAprobacion: mostrarAprobacionCurricular,
    requiereAuditoria,
    csvCanonicosListos,
    cantidadErrores: errores.length,
  });

  useEffect(() => {
    if (!estado.reporte || faseAutomaticaRef.current === faseAutomatica) return;
    faseAutomaticaRef.current = faseAutomatica;
    setActiveTab(faseAutomatica);
  }, [estado.reporte, faseAutomatica]);

  return (
    <main className="h-[100dvh] min-h-screen overflow-y-auto overscroll-y-contain bg-fondo px-4 pb-24 pt-6 font-body text-ink sm:px-8 sm:pb-32 sm:pt-8">
      <div className="mx-auto max-w-7xl">
        <nav
          aria-label="Navegación de ejecución"
          className="mb-4 rounded-2xl border border-line bg-paper px-3 py-2 shadow-sm sm:px-4"
        >
          <Link
            href="/normalizador"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-bold text-ink transition hover:bg-fondo hover:text-ulima focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/40"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            Volver al normalizador
          </Link>
        </nav>
        <header className="rounded-2xl border border-line border-t-4 border-t-ulima bg-paper p-5 shadow-sm sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div className="min-w-0">
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-ulima">
                Inspección histórica / normalizador
              </p>
              <h1 className="mt-2 flex items-center gap-2 font-editorial text-3xl font-extrabold tracking-[-0.04em] text-institucional-negro sm:text-4xl">
                <History className="shrink-0 text-ulima" size={28} /> Inspección
                técnica curricular
              </h1>
              <p className="mt-2 text-sm font-semibold text-muted">
                <span>Inspección de ejecución</span>
                <span aria-hidden="true"> · </span>
                <span>revisión humana y trazabilidad curricular</span>
              </p>
              <p className="mt-2 break-all font-mono text-xs text-muted">
                {idEjecucion}
              </p>
              {estado.reporte ? (
                <section
                  aria-label="Parámetros de la ejecución"
                  className="mt-5 grid max-w-2xl gap-2 sm:grid-cols-2"
                >
                  <dl className="rounded-xl border border-line bg-fondo px-3.5 py-2.5">
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
                      Carrera
                    </dt>
                    <dd className="mt-1 break-words text-sm font-bold text-ink">
                      {parametros.carrera}
                    </dd>
                  </dl>
                  <dl className="rounded-xl border border-line bg-fondo px-3.5 py-2.5">
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
                      Periodo
                    </dt>
                    <dd className="mt-1 break-words text-sm font-bold text-ink">
                      {parametros.periodo}
                    </dd>
                  </dl>
                </section>
              ) : null}
            </div>
            {estado.reporte ? (
              <span
                className={`shrink-0 rounded-xl border px-3 py-2 font-mono text-[10px] font-bold uppercase tracking-[0.06em] ${estadoError ? "border-red-200 bg-red-50 text-red-900" : manifest.estado === "no_publicado" ? "border-ulima/30 bg-ulima/5 text-ink" : "border-line bg-fondo text-ink"}`}
              >
                {estadoLegible(manifest.estado, contextoEstado)}
              </span>
            ) : null}
          </div>
          {estado.reporte ? (
            <InspectionTabs activeTab={activeTab} onChange={setActiveTab} />
          ) : null}
        </header>

        {estado.cargando ? (
          <p className="mt-5 flex items-center gap-2 rounded-xl border border-line bg-paper px-4 py-4 text-sm text-muted">
            <LoaderCircle className="animate-girar" size={17} /> Cargando
            reporte y artefactos de la ejecución…
          </p>
        ) : null}
        {estado.error ? (
          <div
            role="alert"
            className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm font-semibold text-red-700"
          >
            <p className="flex items-start gap-2">
              <XCircle className="mt-0.5 shrink-0" size={18} /> {estado.error}
            </p>
            <p className="mt-2 text-xs font-normal leading-5">
              La ejecución puede ser antigua, haber sido eliminada o no tener un
              reporte legible.
            </p>
          </div>
        ) : null}

        {estado.reporte ? (
          <>
            <section
              id="panel-progreso"
              role="tabpanel"
              aria-labelledby="tab-progreso"
              tabIndex={0}
              hidden={activeTab !== "progreso"}
              className="mt-5 space-y-5 outline-none focus-visible:ring-2 focus-visible:ring-ulima/30"
            >
              {ejecucionActiva ? (
                <section
                  className="rounded-2xl border border-ulima/20 bg-ulima/5 p-5 shadow-sm sm:p-6"
                  role="status"
                  aria-live="polite"
                  aria-label="Progreso de la ejecución"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-2.5">
                      <LoaderCircle
                        className="mt-0.5 shrink-0 animate-girar text-ulima"
                        size={20}
                      />
                      <div>
                        <h2 className="text-lg font-extrabold">
                          Ejecución en curso
                        </h2>
                        <p className="mt-1 text-sm font-semibold text-ulima">
                          {estadoLegible(manifest.estado, contextoEstado)}
                        </p>
                      </div>
                    </div>
                    {progresoActivo?.chunksTotales ? (
                      <span className="font-mono text-xs font-bold text-muted">
                        {progresoActivo.chunksCompletados} /{" "}
                        {progresoActivo.chunksTotales} chunks
                      </span>
                    ) : null}
                  </div>
                  {progresoActivo?.chunksTotales ? (
                    <div
                      className="mt-4 h-2 overflow-hidden rounded-full bg-ulima/10"
                      role="progressbar"
                      aria-label="Avance de la ejecución"
                      aria-valuemin={0}
                      aria-valuemax={progresoActivo.chunksTotales}
                      aria-valuenow={progresoActivo.chunksCompletados}
                      aria-valuetext={`${progresoActivo.chunksCompletados} de ${progresoActivo.chunksTotales} chunks completados`}
                    >
                      <div
                        className="h-full rounded-full bg-ulima transition-[width] duration-500 motion-reduce:transition-none"
                        style={{ width: `${progresoActivo.porcentaje}%` }}
                      />
                    </div>
                  ) : null}
                  <p className="mt-3 text-sm leading-5 text-muted">
                    {progresoActivo?.chunksTotales
                      ? `${progresoActivo.chunksCompletados} de ${progresoActivo.chunksTotales} chunks completados.`
                      : progresoActivo?.eventos
                        ? `${progresoActivo.eventos} hitos de progreso registrados.`
                        : "El procesamiento continúa y el avance se actualizará automáticamente."}{" "}
                    Las salidas se habilitarán al finalizar.
                  </p>
                </section>
              ) : null}

              <section
                className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6"
                aria-labelledby="resultados-positivos-title"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted">
                      Resumen de la ejecución
                    </p>
                    <h2
                      id="resultados-positivos-title"
                      className="mt-2 flex items-center gap-2 text-xl font-extrabold tracking-[-0.025em]"
                    >
                      <CheckCircle2 className="text-ulima" size={20} />{" "}
                      Resultados positivos y estado
                    </h2>
                  </div>
                  <span className="font-mono text-xs font-bold text-muted">
                    Solo lectura
                  </span>
                </div>
                <ul className="mt-5 grid gap-2 md:grid-cols-2">
                  {validacion ? (
                    <Check ok={validacion.valida !== false}>
                      {validacion.valida === false
                        ? "La validación de entrada no fue aprobada."
                        : "Validación técnica aprobada"}
                    </Check>
                  ) : (
                    <Check ok={false}>
                      No hay una validación de entrada disponible en este
                      manifest.
                    </Check>
                  )}
                  {ejecucionActiva ? (
                    <Check>
                      Las salidas se habilitarán al finalizar la ejecución.
                    </Check>
                  ) : csvCanonicosListos ? (
                    <Check>
                      Los CSV canónicos están materializados y disponibles para
                      inspección.
                    </Check>
                  ) : (
                    <Check ok={false}>
                      {csvs.length
                        ? "Hay CSV técnicos declarados, pero todavía no están certificados para publicar."
                        : "Aún no hay CSV técnicos materializados."}
                    </Check>
                  )}
                  {ejecucionActiva ? (
                    <Check>
                      Estado actual:{" "}
                      {estadoLegible(manifest.estado, contextoEstado)}. La
                      inspección se actualizará automáticamente.
                    </Check>
                  ) : manifest.estado === "cancelado" ? (
                    <Check ok={false}>
                      La ejecución fue cancelada; se muestran los artefactos que
                      alcanzaron a persistirse.
                    </Check>
                  ) : (
                    <Check>
                      {manifest.estado
                        ? `Estado final registrado: ${estadoLegible(manifest.estado, contextoEstado)}.`
                        : "El estado final no está disponible."}
                    </Check>
                  )}
                  <Check ok={!publicacionBloqueada}>{mensajePublicacion}</Check>
                </ul>
              </section>

              <section
                className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6"
                aria-labelledby="conteos-title"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <div>
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted">
                      Huella de la ejecución
                    </p>
                    <h2
                      id="conteos-title"
                      className="mt-2 text-xl font-extrabold tracking-[-0.025em]"
                    >
                      Conteos de la normalización
                    </h2>
                  </div>
                  <span className="text-xs text-muted">
                    Valores reportados por el manifest
                  </span>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  {conteos.map((conteo) => (
                    <article
                      key={conteo.clave}
                      className="rounded-xl border border-line bg-fondo px-3.5 py-3"
                    >
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
                        {conteo.etiqueta}
                      </p>
                      <p className="mt-1 tabular-nums text-2xl font-extrabold text-ink">
                        {conteo.valor == null ||
                        Number.isNaN(Number(conteo.valor))
                          ? "—"
                          : Number(conteo.valor).toLocaleString("es-PE")}
                      </p>
                    </article>
                  ))}
                </div>
              </section>
            </section>

            <section
              id="panel-revision"
              role="tabpanel"
              aria-labelledby="tab-revision"
              tabIndex={0}
              hidden={activeTab !== "revision"}
              className="mt-5 space-y-5 outline-none focus-visible:ring-2 focus-visible:ring-ulima/30"
            >
              {mostrarAprobacionCurricular ? (
                <div id="aprobacion-curricular">
                  <CurricularApprovalPanel
                    idEjecucion={idEjecucion}
                    onResolved={() =>
                      setRevisionReporte((actual) => actual + 1)
                    }
                  />
                </div>
              ) : (
                <section className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6">
                  <h2 className="text-xl font-extrabold">Revisión técnica</h2>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    No hay decisiones humanas pendientes para esta ejecución.
                  </p>
                </section>
              )}
            </section>

            <section
              id="panel-csv"
              role="tabpanel"
              aria-labelledby="tab-csv"
              tabIndex={0}
              hidden={activeTab !== "csv"}
              className="mt-5 space-y-5 outline-none focus-visible:ring-2 focus-visible:ring-ulima/30"
            >
              <CsvOutputsPanel
                idEjecucion={idEjecucion}
                csvs={csvs}
                previews={estado.previews}
                ejecucionActiva={ejecucionActiva}
                csvCanonicosListos={csvCanonicosListos}
              />
            </section>

            <section
              id="panel-neo4j"
              role="tabpanel"
              aria-labelledby="tab-neo4j"
              tabIndex={0}
              hidden={activeTab !== "neo4j"}
              className="mt-5 space-y-5 outline-none focus-visible:ring-2 focus-visible:ring-ulima/30"
            >
              {!ejecucionActiva && csvCanonicosListos ? (
                <Neo4jImportPanel idEjecucion={idEjecucion} modo="technical" />
              ) : (
                <section className="rounded-2xl border border-line bg-paper p-5 shadow-sm sm:p-6">
                  <h2 className="text-xl font-extrabold">
                    Publicación en Neo4j
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-muted">
                    {mensajeBloqueoNeo4j(
                      ejecucionActiva,
                      mostrarAprobacionCurricular,
                    )}
                  </p>
                </section>
              )}
            </section>

            <section
              id="panel-auditoria"
              role="tabpanel"
              aria-labelledby="tab-auditoria"
              tabIndex={0}
              hidden={activeTab !== "auditoria"}
              className="mt-5 space-y-5 outline-none focus-visible:ring-2 focus-visible:ring-ulima/30"
            >
              <FindingsDetail
                grupos={gruposHallazgos}
                total={hallazgosAccionables.length}
                errors={errores.length}
                warnings={advertencias.length}
              />
              <p className="text-xs text-muted">
                La trazabilidad detallada aparece al expandir cada aviso; los
                logs y las salidas técnicas generadas permanecen en el backend.
              </p>
            </section>
          </>
        ) : null}
        <p className="mt-6 flex items-center gap-2 text-xs text-muted">
          <ExternalLink size={14} /> Esta página es de solo lectura y usa
          únicamente los outputs declarados por el backend.
        </p>
      </div>
    </main>
  );
}
