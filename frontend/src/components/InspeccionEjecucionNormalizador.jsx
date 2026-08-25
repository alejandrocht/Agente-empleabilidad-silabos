"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  FileSpreadsheet,
  History,
  LoaderCircle,
  ScrollText,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  obtenerReporteEjecucionNormalizador,
  obtenerUrlOutputNormalizador,
  obtenerUrlReporteEjecucionNormalizador,
} from "../api/normalizador";
import CurricularApprovalPanel from "./CurricularApprovalPanel";
import Neo4jImportPanel from "./Neo4jImportPanel";

export const MAX_PREVIEW_ROWS = 100;
export const MAX_CSV_PREVIEW_ROWS = 500;
export const CSV_PREVIEW_PAGE_SIZE = 20;
const MAX_PREVIEW_BYTES = 512 * 1024;
const RUTA_SALIDA_SEGURA = /^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[\w./-]+$/;
const CSV_PREVIEW_NAMES = new Set([
  "catalogo_competencias.csv",
  "catalogo_habilidades.csv",
  "catalogo_herramientas.csv",
]);

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
  return String(archivo || "").split("/").pop() || "Salida sin nombre";
}

function textoParametro(valor, fallback) {
  if (typeof valor === "string" && valor.trim()) return valor.trim();
  if (typeof valor === "number" && Number.isFinite(valor)) return String(valor);
  return fallback;
}

function parametrosDe(manifest) {
  return {
    carrera: textoParametro(
      manifest?.parametros?.carrera ?? manifest?.carrera ?? manifest?.metadata?.carrera,
      "Carrera no indicada",
    ),
    periodo: textoParametro(
      manifest?.parametros?.periodo ?? manifest?.periodo ?? manifest?.metadata?.periodo,
      "Periodo no indicado",
    ),
  };
}

function salidasDe(manifest) {
  const fuentes = [
    manifest?.outputs,
    manifest?.limpieza_silabos?.outputs,
    manifest?.limpieza?.outputs,
    manifest?.normalizacion?.outputs,
  ];
  const salidas = [];
  const vistas = new Set();
  for (const fuente of fuentes) {
    if (!Array.isArray(fuente)) continue;
    for (const salida of fuente) {
      if (!salida || !rutaSalidaSegura(salida.archivo) || vistas.has(salida.archivo)) continue;
      vistas.add(salida.archivo);
      salidas.push(salida);
    }
  }
  return salidas;
}

function reportePorNombre(reportes, nombres) {
  const nombresPermitidos = new Set(nombres.map((nombre) => nombre.toLowerCase()));
  for (const [archivo, reporte] of Object.entries(reportes || {})) {
    if (nombresPermitidos.has(nombreArchivo(archivo).toLowerCase())) return reporte;
  }
  return null;
}

function objetoReporte(reporte) {
  return reporte && typeof reporte === "object" && !Array.isArray(reporte) ? reporte : null;
}

function aprobacionCurricularDe(manifest, reportes) {
  const directa = objetoReporte(manifest?.aprobacion_curricular);
  if (directa) return directa;
  const reporte = objetoReporte(reportePorNombre(reportes, ["aprobacion_curricular.json", "aprobacion.json"]));
  return reporte?.aprobacion_curricular || reporte?.aprobacion || reporte;
}

function releaseGateDe(manifest, reportes) {
  const directo = objetoReporte(manifest?.release_gate || manifest?.limpieza_silabos?.release_gate);
  if (directo) return directo;
  const reporte = objetoReporte(reportePorNombre(reportes, ["release_gate.json"]));
  return reporte?.release_gate || reporte?.gate || reporte;
}

function filasDePendientes(reportes) {
  const reporte = reportePorNombre(reportes, ["pendientes_curriculares.jsonl", "pendientes_curriculares.json"]);
  if (Array.isArray(reporte)) return reporte.filter((fila) => fila && typeof fila === "object");
  for (const clave of ["filas", "pendientes", "items", "propuestas"]) {
    if (Array.isArray(reporte?.[clave])) return reporte[clave].filter((fila) => fila && typeof fila === "object");
  }
  return [];
}

function numeroNoNegativo(...valores) {
  for (const valor of valores) {
    if (valor === null || valor === undefined || valor === "" || typeof valor === "boolean") continue;
    const numero = Number(valor);
    if (Number.isFinite(numero) && numero >= 0) return Math.floor(numero);
  }
  return null;
}

function filaResuelta(fila) {
  if (fila?.requiere_decision === false || fila?.pendiente_por_decidir === false) return true;
  const estado = String(fila?.estado || fila?.status || fila?.decision_estado || fila?.decision || "").toUpperCase();
  return ["ADD", "KEEP_PENDING", "ACEPTADA", "APROBADA", "APROBADO", "RESUELTA", "RESUELTO", "DECIDIDA"].includes(estado);
}

function pendientesPorDecidirDe(manifest, reportes, aprobacion, gate) {
  const explicitos = numeroNoNegativo(
    aprobacion?.pendientes_por_decidir,
    aprobacion?.pending_decision,
    gate?.checks?.approval?.pending_decision,
    gate?.checks?.approval?.pendingDecision,
  );
  if (explicitos !== null) return explicitos;
  return filasDePendientes(reportes).filter((fila) => !filaResuelta(fila)).length || (
    aprobacion?.requiere_decision === true || manifest?.requiere_decision === true ? 1 : 0
  );
}

function requiereDecisionCurricular(manifest, aprobacion, gate, pendientes) {
  return aprobacion?.requiere_decision === true
    || manifest?.requiere_decision === true
    || numeroNoNegativo(gate?.checks?.approval?.pending_decision) > 0
    || pendientes > 0;
}

function esEjecucionCurricular(manifest, reportes, salidas) {
  return manifest?.tipo === "silabos"
    || manifest?.tipo === "curricular"
    || Boolean(manifest?.limpieza_silabos)
    || Boolean(manifest?.aprobacion_curricular)
    || Boolean(manifest?.release_gate?.checks?.approval)
    || Boolean(reportePorNombre(reportes, ["pendientes_curriculares.jsonl", "pendientes_curriculares.json", "release_gate.json"]))
    || salidas.some((salida) => salida?.tipo === "csv_curricular" || String(salida?.tipo || "").includes("curricular"));
}

function salidaCanonica(salida) {
  const nombre = nombreArchivo(salida?.archivo).toLowerCase();
  return CSV_PREVIEW_NAMES.has(nombre) && (salida?.tipo === "csv_curricular" || nombre.startsWith("catalogo_"));
}

function vistasPreviasCompletas(salidas, previews) {
  return salidas
    .filter(salidaCanonica)
    .filter((salida) => CSV_PREVIEW_NAMES.has(nombreArchivo(salida.archivo).toLowerCase()))
    .every((salida) => {
      const preview = previews?.[salida.archivo];
      return preview && !preview.error && Array.isArray(preview.encabezados) && preview.encabezados.length > 0;
    });
}

function releaseGatePermiteImportar(gate, aprobacion, salidas, previews) {
  const catalogosDeclarados = salidas.filter(salidaCanonica).length === CSV_PREVIEW_NAMES.size;
  return gate?.decision === "ALLOW_IMPORT"
    && gate?.checks?.approval?.canonical_materialized === true
    && Number(gate?.checks?.approval?.pending_decision ?? 0) === 0
    && aprobacion?.materializacion?.csv_canonicos_disponibles === true
    && catalogosDeclarados
    && vistasPreviasCompletas(salidas, previews);
}

function bloqueosPublicacion(gate, aprobacion, pendientes, salidas, puedeImportar) {
  if (puedeImportar) return [];
  const bloqueos = [];
  const declarados = gate?.blockers || gate?.bloqueadores || gate?.reasons || gate?.razones;
  if (Array.isArray(declarados)) bloqueos.push(...declarados.filter(Boolean).map(String));
  if (gate?.decision !== "ALLOW_IMPORT") {
    bloqueos.push(`release gate ${gate?.decision || "no declarado"}`);
  }
  if (pendientes > 0) {
    bloqueos.push(`${pendientes} decisión${pendientes === 1 ? "" : "es"} humana${pendientes === 1 ? "" : "s"} pendiente${pendientes === 1 ? "" : "s"}`);
  } else if (aprobacion?.requiere_decision === true) {
    bloqueos.push("el checkpoint curricular requiere una decisión humana");
  }
  if (
    salidas.filter(salidaCanonica).length !== CSV_PREVIEW_NAMES.size
    || aprobacion?.materializacion?.csv_canonicos_disponibles !== true
    || gate?.checks?.approval?.canonical_materialized !== true
    || gate?.decision === "ALLOW_IMPORT"
  ) {
    bloqueos.push("los CSV canónicos no están materializados");
  }
  return [...new Set(bloqueos)];
}

function decisionesDe(reportes) {
  const decisiones = reportes?.["decisiones_llm.jsonl"];
  return Array.isArray(decisiones)
    ? decisiones.filter((decision) => decision && typeof decision === "object")
    : [];
}

function esAceptada(decision) {
  const estado = String(decision?.estado || "").toUpperCase();
  return estado === "ACEPTADA" || estado === "APROBADA" || estado === "APROBAR";
}

function detalleDecision(decision) {
  const inspeccion = decision?.inspeccion || decision?.inspector;
  const problemas = inspeccion?.problemas || decision?.problemas;
  if (Array.isArray(problemas) && problemas.length) return problemas.join("; ");
  return decision?.justificacion || decision?.sugerencia || decision?.detalle || "Decisión aceptada.";
}

function eventosDe(manifest, reportes) {
  const eventos = Array.isArray(manifest?.progreso_llm?.eventos)
    ? manifest.progreso_llm.eventos
    : [];
  const eventosReporte = Array.isArray(reportes?.eventos_llm?.eventos)
    ? reportes.eventos_llm.eventos
    : [];
  return [...eventos, ...eventosReporte]
    .filter((evento) => evento && typeof evento === "object")
    .slice(-MAX_PREVIEW_ROWS);
}

function conteosDe(manifest) {
  const curricular = manifest?.limpieza_silabos || {};
  const laboral = manifest?.normalizacion || {};
  const registrosLaborales = laboral.registros_procesados;
  const registros = curricular.registros ?? (
    registrosLaborales && typeof registrosLaborales === "object"
      ? Object.values(registrosLaborales).reduce((total, valor) => total + Number(valor || 0), 0)
      : null
  );
  return [
    { clave: "registros", etiqueta: "registros procesados", valor: registros },
    { clave: "competencias", etiqueta: "competencias", valor: curricular.competencias },
    { clave: "habilidades", etiqueta: "habilidades", valor: curricular.habilidades },
    { clave: "herramientas", etiqueta: "herramientas", valor: curricular.herramientas },
    {
      clave: "relaciones",
      etiqueta: "relaciones de cobertura",
      valor: curricular.relaciones ?? laboral.relaciones,
    },
  ];
}

const ESTADOS_ACTIVOS = new Set(["recibido", "validando", "limpiando", "normalizando"]);
const INTERVALO_POLLING_MS = 3000;

function estadoNormalizado(estado) {
  return String(estado || "").trim().toLowerCase();
}

function esEstadoActivo(estado) {
  return ESTADOS_ACTIVOS.has(estadoNormalizado(estado));
}

function estadoLegible(estado, contexto = {}) {
  const clave = estadoNormalizado(estado);
  if (contexto.esCurricular && ["limpiado", "limpiado_con_advertencias"].includes(clave)) {
    if (contexto.csvCanonicosListos) {
      return clave === "limpiado_con_advertencias" ? "CSV curriculares listos con advertencias" : "CSV curriculares listos";
    }
    if (contexto.pendientesPorDecidir > 0 || contexto.requiereDecision) return "Revisión curricular pendiente";
    return contexto.gateDecision && contexto.gateDecision !== "ALLOW_IMPORT"
      ? "Revisión curricular persistida; publicación bloqueada"
      : "Revisión curricular persistida; CSV canónicos pendientes";
  }
  return {
    recibido: "Ejecución recibida",
    validando: "Validando estructura",
    validado: "Validación completada",
    validado_con_advertencias: "Validación completada con advertencias",
    limpiando: "Limpiando datos",
    limpiado: "Limpieza completada",
    limpiado_con_advertencias: "Limpieza completada con advertencias",
    normalizando: "Normalizando relaciones",
    normalizado: "Normalización completa",
    normalizado_con_advertencias: "Normalización completa con advertencias",
    cancelado: "Procesamiento cancelado",
    error: "Error de ejecución",
    rechazado: "Entrada rechazada",
    no_publicado: "No publicado",
  }[estadoNormalizado(estado)] || estado || "Estado no disponible";
}

function progresoActivoDe(manifest) {
  const progreso = manifest?.progreso_llm;
  if (!progreso || typeof progreso !== "object") return null;
  const chunksCompletados = Number(progreso.chunks_completados);
  const chunksTotales = Number(progreso.chunks_totales);
  const tieneChunks = Number.isFinite(chunksTotales) && chunksTotales > 0;
  const eventos = Array.isArray(progreso.eventos) ? progreso.eventos : [];
  return {
    chunksCompletados: Number.isFinite(chunksCompletados) ? Math.max(0, chunksCompletados) : 0,
    chunksTotales: tieneChunks ? chunksTotales : 0,
    eventos: eventos.length,
    porcentaje: tieneChunks
      ? Math.min(100, Math.round((Math.max(0, chunksCompletados || 0) / chunksTotales) * 100))
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
      const acotado = bytes.byteLength > restante ? bytes.slice(0, restante) : bytes;
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
  if (!respuesta.ok) throw new Error(`No se pudo leer ${nombreArchivo(salida.archivo)}.`);
  const texto = await leerRespuestaAcotada(respuesta);
  return { ...parseCsvPreview(texto), url };
}

function Check({ children, ok = true }) {
  return (
    <li className={`flex items-start gap-2 rounded-xl border px-3.5 py-3 text-sm ${ok ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
      {ok ? <CheckCircle2 className="mt-0.5 shrink-0" size={17} /> : <AlertTriangle className="mt-0.5 shrink-0" size={17} />}
      <span>{children}</span>
    </li>
  );
}

function CsvPreview({ nombre, preview }) {
  const [pagina, setPagina] = useState(0);
  if (preview?.error) {
    return <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{preview.error}</p>;
  }
  if (!preview?.encabezados?.length) {
    return <p className="mt-3 rounded-lg border border-dashed border-line px-3 py-3 text-xs text-muted">El CSV está vacío o no tiene encabezado legible.</p>;
  }
  const totalPaginas = Math.max(1, Math.ceil(preview.filas.length / CSV_PREVIEW_PAGE_SIZE));
  const paginaSegura = Math.min(pagina, totalPaginas - 1);
  const inicio = paginaSegura * CSV_PREVIEW_PAGE_SIZE;
  const filasPagina = preview.filas.slice(inicio, inicio + CSV_PREVIEW_PAGE_SIZE);
  const fin = Math.min(inicio + filasPagina.length, preview.filas.length);
  return (
    <details className="mt-3 overflow-hidden rounded-xl border border-line bg-paper" open>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3.5 py-3 text-xs font-bold text-ink">
        <span>Vista previa de {nombre}</span>
        <span className="font-mono text-[10px] font-medium text-muted">20 filas por página</span>
      </summary>
      <div className="overflow-x-auto border-t border-line">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-fondo text-[10px] uppercase tracking-[0.06em] text-muted">
            <tr>
              {preview.encabezados.map((encabezado, indice) => <th key={`${encabezado}-${indice}`} className="whitespace-nowrap px-3 py-2 font-bold">{encabezado || `Columna ${indice + 1}`}</th>)}
            </tr>
          </thead>
          <tbody>
            {filasPagina.map((fila, filaIndice) => {
              const indiceAbsoluto = inicio + filaIndice;
              return (
                <tr key={`fila-${indiceAbsoluto}`} className="border-t border-line align-top">
                  {preview.encabezados.map((_encabezado, columnaIndice) => <td key={`celda-${indiceAbsoluto}-${columnaIndice}`} className="max-w-[18rem] px-3 py-2 text-muted">{fila[columnaIndice] || "—"}</td>)}
                </tr>
              );
            })}
            {!filasPagina.length ? (
              <tr className="border-t border-line">
                <td colSpan={preview.encabezados.length} className="px-3 py-4 text-center text-muted">No hay registros para mostrar.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-3.5 py-2 text-[11px] text-muted">
        <p>
          Filas {filasPagina.length ? `${inicio + 1}–${fin}` : "0"} de {preview.totalFilas} · Página {paginaSegura + 1} de {totalPaginas}
          {preview.truncado ? `; se muestran como máximo ${MAX_CSV_PREVIEW_ROWS}.` : "."}
        </p>
        <nav className="flex items-center gap-1.5" aria-label={`Paginación de ${nombre}`}>
          <button
            type="button"
            className="rounded-md border border-line bg-paper px-2 py-1 font-semibold text-ink transition hover:border-ulima hover:text-ulima disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => setPagina((actual) => Math.max(0, actual - 1))}
            disabled={paginaSegura === 0}
            aria-label={`Página anterior de ${nombre}`}
          >
            Anterior
          </button>
          <button
            type="button"
            className="rounded-md border border-line bg-paper px-2 py-1 font-semibold text-ink transition hover:border-ulima hover:text-ulima disabled:cursor-not-allowed disabled:opacity-40"
            onClick={() => setPagina((actual) => Math.min(totalPaginas - 1, actual + 1))}
            disabled={paginaSegura >= totalPaginas - 1}
            aria-label={`Página siguiente de ${nombre}`}
          >
            Siguiente
          </button>
        </nav>
      </div>
    </details>
  );
}

export default function InspeccionEjecucionNormalizador({ idEjecucion }) {
  const [estado, setEstado] = useState({ cargando: true, reporte: null, error: "", previews: {} });
  const [revisionReporte, setRevisionReporte] = useState(0);

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
      if (inicial) setEstado({ cargando: true, reporte: null, error: "", previews: {} });
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
        const csvs = salidas.filter((salida) => salida.archivo.toLowerCase().endsWith(".csv"));
        const csvsParaPreview = csvs.filter((salida) => CSV_PREVIEW_NAMES.has(nombreArchivo(salida.archivo).toLowerCase()));
        const resultados = await Promise.all(
          csvsParaPreview.map(async (salida) => {
            try {
              return [salida.archivo, await cargarPreviewCsv(idEjecucion, salida)];
            } catch (error) {
              return [salida.archivo, { error: error.message || "No se pudo cargar la vista previa." }];
            }
          }),
        );
        if (activo) setEstado({ cargando: false, reporte, error: "", previews: Object.fromEntries(resultados) });
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

  const manifest = estado.reporte?.manifest || {};
  const reportes = estado.reporte?.reportes || {};
  const parametros = parametrosDe(manifest);
  const salidas = useMemo(() => salidasDe(manifest), [manifest]);
  const csvs = salidas.filter((salida) => salida.archivo.toLowerCase().endsWith(".csv"));
  const csvsParaPreview = csvs.filter((salida) => CSV_PREVIEW_NAMES.has(nombreArchivo(salida.archivo).toLowerCase()));
  const aprobacionCurricular = aprobacionCurricularDe(manifest, reportes);
  const releaseGate = releaseGateDe(manifest, reportes);
  const esCurricular = esEjecucionCurricular(manifest, reportes, salidas);
  const pendientesPorDecidir = pendientesPorDecidirDe(manifest, reportes, aprobacionCurricular, releaseGate);
  const requiereDecision = requiereDecisionCurricular(manifest, aprobacionCurricular, releaseGate, pendientesPorDecidir);
  const tieneCatalogosCurriculares = csvsParaPreview.length === CSV_PREVIEW_NAMES.size;
  const csvCanonicosListos = releaseGatePermiteImportar(releaseGate, aprobacionCurricular, salidas, estado.previews);
  const mostrarAprobacionCurricular = !esEstadoActivo(manifest.estado)
    && esCurricular
    && (requiereDecision || filasDePendientes(reportes).some((fila) => !filaResuelta(fila)));
  const bloqueos = bloqueosPublicacion(releaseGate, aprobacionCurricular, pendientesPorDecidir, salidas, csvCanonicosListos);
  const decisionesAceptadas = decisionesDe(reportes).filter(esAceptada);
  const hallazgos = Array.isArray(manifest.hallazgos)
    ? manifest.hallazgos.filter((hallazgo) => hallazgo && typeof hallazgo === "object")
    : [];
  const advertencias = hallazgos.filter((hallazgo) => hallazgo?.severidad === "warning");
  const errores = hallazgos.filter((hallazgo) => hallazgo?.severidad === "error");
  const eventos = eventosDe(manifest, reportes);
  const conteos = conteosDe(manifest);
  const validacion = manifest.validacion_silabos || manifest.validacion;
  const ejecucionActiva = esEstadoActivo(manifest.estado);
  const progresoActivo = progresoActivoDe(manifest);
  const estadoError = ["error", "rechazado", "no_publicado"].includes(estadoNormalizado(manifest.estado));
  const contextoEstado = {
    esCurricular,
    csvCanonicosListos,
    pendientesPorDecidir,
    requiereDecision,
    gateDecision: releaseGate?.decision,
  };

  return (
    <main className="h-[100dvh] min-h-screen overflow-y-auto overscroll-y-contain bg-fondo px-4 pb-24 pt-6 text-ink sm:px-8 sm:pb-32 sm:pt-8">
      <div className="mx-auto max-w-7xl">
        <header className="rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-ulima">Inspección histórica / normalizador</p>
              <h1 className="mt-2 flex items-center gap-2 text-2xl font-extrabold tracking-[-0.03em] sm:text-3xl"><History className="text-ulima" size={26} /> Inspección de ejecución</h1>
              <p className="mt-2 break-all font-mono text-xs text-muted">{idEjecucion}</p>
              {estado.reporte ? <section aria-label="Parámetros de la ejecución" className="mt-4 flex flex-wrap gap-2">
                <dl className="min-w-[10rem] flex-1 rounded-xl border border-line bg-fondo px-3.5 py-2.5">
                  <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">Carrera</dt>
                  <dd className="mt-1 break-words text-sm font-bold text-ink">{parametros.carrera}</dd>
                </dl>
                <dl className="min-w-[10rem] flex-1 rounded-xl border border-line bg-fondo px-3.5 py-2.5">
                  <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">Periodo</dt>
                  <dd className="mt-1 break-words text-sm font-bold text-ink">{parametros.periodo}</dd>
                </dl>
              </section> : null}
            </div>
            {estado.reporte ? <span className={`rounded-full px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.06em] ${estadoError ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-800"}`}>{estadoLegible(manifest.estado, contextoEstado)}</span> : null}
          </div>
          {estado.reporte ? <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted"><span>Estado persistido: <strong className="text-ink">{manifest.estado || "no disponible"}</strong></span><a href={obtenerUrlReporteEjecucionNormalizador(idEjecucion)} download rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-2 font-bold text-ink transition hover:border-ulima hover:text-ulima"><Download size={14} /> Descargar reporte JSON</a></div> : null}
        </header>

        {estado.cargando ? <p className="mt-5 flex items-center gap-2 rounded-xl border border-line bg-paper px-4 py-4 text-sm text-muted"><LoaderCircle className="animate-girar" size={17} /> Cargando reporte, salidas y vistas previas…</p> : null}
        {estado.error ? <div role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-4 text-sm font-semibold text-red-700"><p className="flex items-start gap-2"><XCircle className="mt-0.5 shrink-0" size={18} /> {estado.error}</p><p className="mt-2 text-xs font-normal leading-5">La ejecución puede ser antigua, haber sido eliminada o no tener un reporte legible.</p></div> : null}

        {estado.reporte ? (
          <>
            {ejecucionActiva ? (
              <section className="mt-5 rounded-2xl border border-ulima/20 bg-ulima/5 p-5 shadow-panel sm:p-6" role="status" aria-live="polite" aria-label="Progreso de la ejecución">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5">
                    <LoaderCircle className="mt-0.5 shrink-0 animate-girar text-ulima" size={20} />
                    <div>
                      <h2 className="text-lg font-extrabold">Ejecución en curso</h2>
                      <p className="mt-1 text-sm font-semibold text-ulima">{estadoLegible(manifest.estado, contextoEstado)}</p>
                    </div>
                  </div>
                  {progresoActivo?.chunksTotales ? <span className="font-mono text-xs font-bold text-muted">{progresoActivo.chunksCompletados} / {progresoActivo.chunksTotales} chunks</span> : null}
                </div>
                {progresoActivo?.chunksTotales ? (
                  <div className="mt-4 h-2 overflow-hidden rounded-full bg-ulima/10" role="progressbar" aria-label="Avance de la ejecución" aria-valuemin={0} aria-valuemax={progresoActivo.chunksTotales} aria-valuenow={progresoActivo.chunksCompletados} aria-valuetext={`${progresoActivo.chunksCompletados} de ${progresoActivo.chunksTotales} chunks completados`}>
                    <div className="h-full rounded-full bg-ulima transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${progresoActivo.porcentaje}%` }} />
                  </div>
                ) : null}
                <p className="mt-3 text-sm leading-5 text-muted">
                  {progresoActivo?.chunksTotales
                    ? `${progresoActivo.chunksCompletados} de ${progresoActivo.chunksTotales} chunks completados.`
                    : progresoActivo?.eventos
                      ? `${progresoActivo.eventos} hitos de progreso registrados.`
                      : "El procesamiento continúa y el avance se actualizará automáticamente."} Las salidas CSV se habilitarán al finalizar.
                </p>
              </section>
            ) : null}
            <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-labelledby="resultados-positivos-title">
              <h2 id="resultados-positivos-title" className="flex items-center gap-2 text-lg font-extrabold"><CheckCircle2 className="text-emerald-600" size={20} /> Resultados positivos y estado</h2>
              <ul className="mt-4 grid gap-2 md:grid-cols-2">
                {validacion ? <Check ok={validacion.valida !== false}>{validacion.valida === false ? "La validación de entrada no fue aprobada." : "Validación curricular aprobada"}</Check> : <Check ok={false}>No hay una validación de entrada disponible en este manifest.</Check>}
                {ejecucionActiva ? <Check>Las salidas CSV se habilitarán al finalizar la ejecución.</Check> : esCurricular ? csvCanonicosListos ? <Check>{CSV_PREVIEW_NAMES.size} CSV canónicos materializados y disponibles para inspección.</Check> : <Check ok={false}>{csvs.length ? "Hay archivos CSV declarados, pero todavía no están certificados como CSV canónicos materializados." : "No hay CSV canónicos materializados; los reportes JSON/JSONL son solo evidencia de revisión y proveniencia."}</Check> : csvs.length ? <Check>{csvs.length} salidas CSV declaradas y disponibles para inspección.</Check> : <Check ok={false}>Esta ejecución no declara salidas CSV accesibles.</Check>}
                {ejecucionActiva ? <Check>Estado actual: {estadoLegible(manifest.estado, contextoEstado)}. La inspección se actualizará automáticamente.</Check> : manifest.estado === "cancelado" ? <Check ok={false}>La ejecución fue cancelada; se muestran los artefactos que alcanzaron a persistirse.</Check> : <Check>{manifest.estado ? `Estado final registrado: ${estadoLegible(manifest.estado, contextoEstado)}.` : "El estado final no está disponible."}</Check>}
                {manifest.limpieza_silabos?.publicable === false || manifest.normalizacion?.publicable === false ? <Check ok={false}>El gate marcó la ejecución como no publicable; los artefactos siguen siendo de solo lectura.</Check> : <Check>Los resultados se presentan como evidencia de solo lectura.</Check>}
              </ul>
            </section>

            <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-labelledby="conteos-title">
              <h2 id="conteos-title" className="text-lg font-extrabold">Conteos de la normalización</h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {conteos.map((conteo) => <article key={conteo.clave} className="rounded-xl border border-line bg-fondo px-3.5 py-3"><p className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">{conteo.etiqueta}</p><p className="mt-1 text-xl font-extrabold text-ink">{conteo.valor == null || Number.isNaN(Number(conteo.valor)) ? "—" : Number(conteo.valor).toLocaleString("es-PE")}</p></article>)}
              </div>
            </section>

            <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-labelledby="salidas-title">
              <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="salidas-title" className="flex items-center gap-2 text-lg font-extrabold"><FileSpreadsheet className="text-ulima" size={20} /> Salidas generadas</h2><span className="text-xs text-muted">{ejecucionActiva ? "Se habilitarán al finalizar" : `${salidas.length} archivos declarados`}</span></div>
              {salidas.length ? <ul className="mt-4 grid gap-2 md:grid-cols-2">{salidas.map((salida) => <li key={salida.archivo} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-fondo px-3.5 py-3"><div className="min-w-0"><p className="truncate font-mono text-xs font-bold text-ink">{nombreArchivo(salida.archivo)}</p><p className="mt-1 text-xs text-muted">{salida.registros == null ? "Cantidad no declarada" : `${salida.registros} registros`} · {salida.tipo || "artefacto"}</p></div><a href={obtenerUrlOutputNormalizador(idEjecucion, salida.archivo)} download rel="noopener noreferrer" className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line bg-paper px-2.5 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima"><Download size={14} /> Descargar</a></li>)}</ul> : <p className="mt-4 rounded-xl border border-dashed border-line px-3.5 py-4 text-sm leading-5 text-muted">{ejecucionActiva ? "La ejecución sigue en curso. Las salidas CSV aparecerán cuando el procesamiento termine." : "No hay salidas declaradas. Puede tratarse de una ejecución cancelada, rechazada o de un manifest legado incompleto."}</p>}
              {csvsParaPreview.length ? <div className="mt-5 space-y-3">{csvsParaPreview.map((salida) => <CsvPreview key={salida.archivo} nombre={nombreArchivo(salida.archivo)} preview={estado.previews[salida.archivo]} />)}</div> : null}
            </section>

            {mostrarAprobacionCurricular ? (
              <CurricularApprovalPanel
                idEjecucion={idEjecucion}
                onResolved={() => setRevisionReporte((actual) => actual + 1)}
              />
            ) : null}

            {!ejecucionActiva && esCurricular && !csvCanonicosListos ? (
              <section className="mt-5 rounded-2xl border border-amber-200 bg-amber-50/60 p-5 shadow-panel sm:p-6" aria-label="Estado de publicación curricular" role="status">
                <h2 className="flex items-center gap-2 text-lg font-extrabold text-amber-950"><AlertTriangle className="text-amber-600" size={20} /> Publicación en Neo4j bloqueada</h2>
                <p className="mt-2 text-sm leading-5 text-amber-950/80">La inspección conserva la revisión y la proveniencia, pero no habilita una importación hasta resolver el checkpoint y materializar los CSV canónicos.</p>
                {bloqueos.length ? <ul className="mt-3 space-y-1 text-sm leading-5 text-amber-950">{bloqueos.map((bloqueo) => <li key={bloqueo}>• {bloqueo}</li>)}</ul> : null}
                {!tieneCatalogosCurriculares ? <p className="mt-3 text-xs leading-5 text-amber-950/80">Los archivos JSON/JSONL persistidos son reportes de auditoría/proveniencia y no equivalen a CSV canónicos.</p> : null}
              </section>
            ) : null}

            {!ejecucionActiva && csvCanonicosListos ? <Neo4jImportPanel idEjecucion={idEjecucion} /> : null}

            <section className="mt-5 grid gap-5 lg:grid-cols-2">
              <article className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5 shadow-panel" aria-labelledby="decisiones-aceptadas-title"><h2 id="decisiones-aceptadas-title" className="text-lg font-extrabold text-emerald-950">Decisiones LLM aceptadas</h2>{decisionesAceptadas.length ? <ul className="mt-4 max-h-96 space-y-2 overflow-y-auto">{decisionesAceptadas.slice(0, MAX_PREVIEW_ROWS).map((decision, indice) => <li key={`${decision.id_habilidad_fuente || "decision"}-${indice}`} className="rounded-xl border border-emerald-200 bg-paper px-3.5 py-3 text-sm"><p className="font-mono text-[10px] font-bold uppercase tracking-[0.07em] text-emerald-700">{decision.estado}{decision.id_habilidad_fuente ? ` · ${decision.id_habilidad_fuente}` : ""}</p><p className="mt-1 leading-5 text-emerald-950">{detalleDecision(decision)}</p></li>)}</ul> : <p className="mt-4 rounded-xl border border-dashed border-emerald-200 bg-paper px-3.5 py-3 text-sm leading-5 text-emerald-900">No hay decisiones aceptadas registradas. Esto es normal en ejecuciones canceladas o deterministas.</p>}</article>
              <article className="rounded-2xl border border-line bg-paper p-5 shadow-panel" aria-labelledby="logs-title"><h2 id="logs-title" className="flex items-center gap-2 text-lg font-extrabold"><ScrollText className="text-ulima" size={20} /> Logs y eventos</h2>{eventos.length ? <ul className="mt-4 max-h-96 space-y-2 overflow-y-auto">{eventos.map((evento, indice) => <li key={`${evento.secuencia || "evento"}-${indice}`} className="rounded-xl border border-line bg-fondo px-3.5 py-3 text-xs leading-5"><span className="font-mono text-[10px] font-bold uppercase text-ulima">{evento.fase || "evento"}</span><p className="mt-1 text-muted">{evento.mensaje || evento.detalle || "Evento sin detalle."}</p></li>)}</ul> : <p className="mt-4 rounded-xl border border-dashed border-line px-3.5 py-3 text-sm leading-5 text-muted">No hay eventos de progreso persistidos.</p>}</article>
            </section>

            <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-labelledby="hallazgos-title"><h2 id="hallazgos-title" className="flex items-center gap-2 text-lg font-extrabold"><AlertTriangle className="text-amber-600" size={20} /> Advertencias y errores</h2>{hallazgos.length ? <div className="mt-4 grid gap-3 md:grid-cols-2">{[...errores, ...advertencias].slice(0, MAX_PREVIEW_ROWS).map((hallazgo, indice) => <article key={`${hallazgo.codigo || "hallazgo"}-${indice}`} className={`rounded-xl border px-3.5 py-3 text-sm ${hallazgo.severidad === "error" ? "border-red-200 bg-red-50 text-red-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}><p className="font-mono text-[10px] font-bold uppercase">{hallazgo.severidad || "warning"} · {hallazgo.codigo || "SIN_CODIGO"}</p><p className="mt-1 leading-5">{hallazgo.mensaje || hallazgo.detalle || "Hallazgo sin detalle."}</p>{hallazgo.detalle && hallazgo.detalle !== hallazgo.mensaje ? <p className="mt-1 text-xs opacity-80">{hallazgo.detalle}</p> : null}</article>)}</div> : <p className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm text-emerald-900">No hay advertencias ni errores registrados en esta ejecución.</p>}</section>
          </>
        ) : null}
        <p className="mt-6 flex items-center gap-2 text-xs text-muted"><ExternalLink size={14} /> Esta página es de solo lectura y usa únicamente los outputs declarados por el backend.</p>
      </div>
    </main>
  );
}
