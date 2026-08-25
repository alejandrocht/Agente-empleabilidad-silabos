"use client";

import { AlertTriangle, Check, Clock3, LoaderCircle, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  decidirPendientesNormalizador,
  obtenerPendientesNormalizador,
} from "../api/normalizador";

const TIPOS = ["competencia", "habilidad", "herramienta"];

const ETIQUETAS = {
  competencia: "Competencias",
  habilidad: "Habilidades",
  herramienta: "Herramientas",
  otro: "Otros pendientes",
};

const DESCRIPCIONES = {
  competencia: "Capacidades que el LLM considera propias del perfil curricular.",
  habilidad: "Habilidades detectadas en los logros de los sílabos.",
  herramienta: "Herramientas mencionadas en la evidencia curricular.",
  otro: "Propuestas que el backend no pudo clasificar en un tipo conocido.",
};

const FILTROS = [
  { id: "all", label: "Todas" },
  { id: "competencia", label: "Competencias" },
  { id: "habilidad", label: "Habilidades" },
  { id: "herramienta", label: "Herramientas" },
  { id: "exact", label: "Duplicados exactos" },
  { id: "semantic", label: "Posibles semánticos" },
  { id: "suspicious", label: "Herramientas sospechosas" },
];

const FLAG_EXACT = "EXACT_DUPLICATE";
const FLAG_SEMANTIC = "POSSIBLE_SEMANTIC_DUPLICATE";
const FLAG_SUSPICIOUS = "SUSPICIOUS_UNRELATED_TOOL";

function texto(valor) {
  return String(valor ?? "").trim();
}

function claveBusqueda(valor) {
  return texto(valor)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase();
}

function nombrePropuesto(fila) {
  return texto(fila?.propuesta?.nombre || fila?.propuesta?.id || fila?.nombre_propuesta)
    || "Propuesta sin nombre";
}

function descripcionPropuesta(fila) {
  return texto(
    fila?.propuesta?.descripcion
      || fila?.descripcion_fuente,
  ) || "Sin descripción adicional.";
}

function evidenciaDe(fila) {
  if (Array.isArray(fila?.evidencia)) {
    return fila.evidencia.map(texto).filter(Boolean);
  }
  const valor = texto(fila?.evidencia);
  return valor ? [valor] : [];
}

function flagsDe(fila) {
  const flags = new Set(Array.isArray(fila?.flags) ? fila.flags.map(texto) : []);
  if (fila?.duplicado_exacto || fila?.exact_duplicate) flags.add(FLAG_EXACT);
  if (fila?.posible_duplicado_semantico || fila?.semantic_duplicate) flags.add(FLAG_SEMANTIC);
  if (fila?.herramienta_no_relacionada || fila?.suspicious_tool) flags.add(FLAG_SUSPICIOUS);
  return flags;
}

function autoDeduplicadaDe(fila) {
  return fila?.auto_deduplicated === true
    || fila?.auto_deduplication_state === "AUTO_DEDUPLICATED"
    || fila?.clasificacion?.auto_deduplicated === true;
}

function representanteDe(fila) {
  return texto(
    fila?.exact_duplicate_representative_id
      || fila?.representative_id
      || fila?.auto_dedup_representative_id
      || fila?.clasificacion?.exact_duplicate_representative_id,
  );
}

function tipoDe(fila) {
  const tipo = texto(fila?.tipo).toLocaleLowerCase();
  return TIPOS.includes(tipo) ? tipo : "otro";
}

function gruposDe(filas) {
  const orden = [...TIPOS, "otro"];
  return orden
    .map((tipo) => ({
      tipo,
      filas: filas.filter((fila) => tipoDe(fila) === tipo),
    }))
    .filter((grupo) => grupo.filas.length);
}

function conteosDe(filas) {
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

function coincideFiltro(fila, filtro) {
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

function textoBuscable(fila) {
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

function etiquetasDeSeñal(fila) {
  const flags = flagsDe(fila);
  const etiquetas = [];
  if (flags.has(FLAG_EXACT)) {
    const autoDeduplicada = autoDeduplicadaDe(fila);
    const representante = representanteDe(fila);
    etiquetas.push({
      id: "exact",
      label: "Duplicado exacto",
      className: "border-amber-200 bg-amber-50 text-amber-800",
      explanation: autoDeduplicada
        ? `Coincide con otra propuesta del mismo tipo y grupo${texto(fila?.grupo_duplicado_exacto || fila?.exact_duplicate_group) ? ` (${fila.grupo_duplicado_exacto || fila.exact_duplicate_group})` : ""}. Se deduplicó automáticamente y esta fila de origen permanece auditable; el representante es ${representante || "la fila determinista del grupo"}. No puede recibir una decisión separada.`
        : `Coincide con otra propuesta del mismo tipo y grupo${texto(fila?.grupo_duplicado_exacto || fila?.exact_duplicate_group) ? ` (${fila.grupo_duplicado_exacto || fila.exact_duplicate_group})` : ""}. Se deduplicó automáticamente; esta fila es el representante ${representante ? `(${representante})` : "determinista"} y requiere revisión humana.`,
    });
  }
  if (flags.has(FLAG_SEMANTIC)) {
    etiquetas.push({
      id: "semantic",
      label: "Posible duplicado semántico",
      className: "border-sky-200 bg-sky-50 text-sky-800",
      explanation: `Comparte señales de equivalencia con otra propuesta del mismo tipo${texto(fila?.grupo_duplicado_semantico || fila?.semantic_duplicate_group) ? ` (${fila.grupo_duplicado_semantico || fila.semantic_duplicate_group})` : ""}. Requiere revisión humana; no se fusionó automáticamente.`,
    });
  }
  if (flags.has(FLAG_SUSPICIOUS)) {
    etiquetas.push({
      id: "suspicious",
      label: "Herramienta sospechosa / no relacionada",
      className: "border-red-200 bg-red-50 text-red-800",
      explanation: `La evidencia no relaciona claramente la herramienta con el contenido curricular (relevancia: ${texto(fila?.relevancia_herramienta || fila?.tool_relevance) || "SUSPICIOUS_UNRELATED"}). No se eliminó automáticamente.`,
    });
  }
  return etiquetas;
}

function camposDeProveniencia(fila) {
  return [
    ["Archivo fuente", fila?.archivo],
    ["Curso", fila?.id_curso],
    ["Sílabo", fila?.id_silabo],
    ["Logro", fila?.etiqueta_logro],
    ["Descripción fuente", fila?.descripcion_fuente],
  ].filter(([, valor]) => texto(valor));
}

function plural(cantidad, singular, pluralizado = `${singular}s`) {
  return `${cantidad} ${cantidad === 1 ? singular : pluralizado}`;
}

function DecisionButton({ decision, activa, nombre, onClick, disabled }) {
  const esAdd = decision === "ADD";
  return (
    <button
      type="button"
      aria-label={`${decision}: ${esAdd ? "agregar" : "mantener pendiente"} ${nombre}`}
      aria-pressed={activa}
      data-decision={decision}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-3 py-2 text-left text-xs font-extrabold transition focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-60 ${
        activa
          ? esAdd
            ? "border-emerald-500 bg-emerald-50 text-emerald-800"
            : "border-amber-500 bg-amber-50 text-amber-900"
          : "border-line bg-paper text-muted hover:border-ulima/60 hover:text-ink"
      }`}
    >
      <span className="font-mono">{decision}</span>
      <span className="mt-0.5 block font-sans font-bold">{esAdd ? "Agregar al perfil" : "Mantener pendiente"}</span>
    </button>
  );
}

function ProposalCard({ fila, decision, onDecision, disabled }) {
  const nombre = nombrePropuesto(fila);
  const señales = etiquetasDeSeñal(fila);
  const proveniencia = camposDeProveniencia(fila);
  const evidencia = evidenciaDe(fila);
  const autoDeduplicada = autoDeduplicadaDe(fila);
  return (
    <article
      className="rounded-xl border border-line bg-paper p-4 shadow-sm"
      data-testid="curricular-proposal-card"
      data-pending-id={fila.id_pendiente}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start gap-2">
            <div className="min-w-0">
              <p className="text-base font-extrabold text-ink">{nombre}</p>
              <p className="mt-1 text-sm leading-5 text-muted">{descripcionPropuesta(fila)}</p>
            </div>
            <span className="rounded-full border border-line bg-fondo px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">
              {ETIQUETAS[tipoDe(fila)]}
            </span>
          </div>

          {señales.length ? (
            <div className="mt-3 space-y-2" aria-label={`Señales de revisión para ${nombre}`}>
              <div className="flex flex-wrap gap-1.5">
                {señales.map((señal) => (
                  <span key={señal.id} className={`rounded-full border px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-[0.06em] ${señal.className}`}>
                    {señal.label}
                  </span>
                ))}
              </div>
              <ul className="space-y-1 text-xs leading-5 text-muted">
                {señales.map((señal) => (
                  <li key={`${señal.id}-explanation`}><span className="font-bold text-ink">Por qué:</span> {señal.explanation}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="mt-4 rounded-lg border border-sky-200/70 bg-sky-50/60 p-3" aria-label={`Proveniencia y evidencia de ${nombre}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-sky-800">Proveniencia y evidencia de fuente</p>
              <span className="font-mono text-[9px] text-sky-800/75">{fila.id_pendiente}</span>
            </div>
            {proveniencia.length ? (
              <dl className="mt-2 grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
                {proveniencia.map(([etiqueta, valor]) => (
                  <div key={etiqueta} className="min-w-0">
                    <dt className="font-bold text-sky-950/75">{etiqueta}</dt>
                    <dd className="truncate text-sky-950">{texto(valor)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-xs leading-5 text-sky-950/80">El backend no reportó metadatos de ubicación para esta propuesta; la identidad y decisión se conservan.</p>
            )}
            <div className="mt-3 border-t border-sky-200/70 pt-2">
              <p className="text-xs font-bold text-sky-950/80">Evidencia textual</p>
              {evidencia.length ? (
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-sky-950">
                  {evidencia.map((item, indice) => <li key={`${fila.id_pendiente}-evidencia-${indice}`}>{item}</li>)}
                </ul>
              ) : (
                <p className="mt-1 text-xs leading-5 text-sky-950/80">No se adjuntó evidencia textual.</p>
              )}
            </div>
          </div>
        </div>

        {autoDeduplicada ? (
          <div className="shrink-0 rounded-lg border border-emerald-200 bg-emerald-50/70 p-3 lg:w-64" aria-label={`Deduplicación automática para ${nombre}`}>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-emerald-800">Deduplicada automáticamente</p>
            <p className="mt-1 text-xs leading-5 text-emerald-950/80">Esta evidencia queda en los artefactos auditables. Solo el representante {representanteDe(fila) || "determinista"} puede recibir ADD o KEEP_PENDING.</p>
          </div>
        ) : (
          <div className="shrink-0 rounded-lg border border-line bg-fondo p-3 lg:w-64" aria-label={`Decisión para ${nombre}`}>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted">Decisión explícita</p>
            <p className="mt-1 text-xs leading-5 text-muted">Elige ADD o KEEP_PENDING. Las señales semánticas y las herramientas sospechosas siguen requiriendo revisión humana.</p>
            <div className="mt-3 grid gap-2">
              <DecisionButton
                decision="ADD"
                activa={decision === "ADD"}
                nombre={nombre}
                onClick={() => onDecision(fila.id_pendiente, "ADD")}
                disabled={disabled}
              />
              <DecisionButton
                decision="KEEP_PENDING"
                activa={decision === "KEEP_PENDING"}
                nombre={nombre}
                onClick={() => onDecision(fila.id_pendiente, "KEEP_PENDING")}
                disabled={disabled}
              />
            </div>
            <p className="mt-2 text-[11px] leading-4 text-muted" aria-live="polite">
              {decision ? `Seleccionado: ${decision}` : "Sin decisión; seguirá pendiente."}
            </p>
          </div>
        )}
      </div>
    </article>
  );
}

export default function CurricularApprovalPanel({ idEjecucion, onSummary, onResolved }) {
  const [filas, setFilas] = useState(null);
  const [resumen, setResumen] = useState(null);
  const [decisiones, setDecisiones] = useState({});
  const [filtro, setFiltro] = useState("all");
  const [busqueda, setBusqueda] = useState("");
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [resultado, setResultado] = useState(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError("");
    try {
      // The backend intentionally returns only proposals without a decision.
      // Resolved KEEP_PENDING rows remain available in the audit artifacts.
      const datos = await obtenerPendientesNormalizador(idEjecucion, {
        incluirResueltas: false,
        limite: 200,
      });
      const siguientes = Array.isArray(datos?.filas) ? datos.filas : [];
      setFilas(siguientes);
      setResumen(datos?.aprobacion || null);
      onSummary?.(datos?.aprobacion || null);
    } catch (errorCarga) {
      setError(errorCarga.message || "No se pudieron cargar las propuestas curriculares.");
      setFilas([]);
    } finally {
      setCargando(false);
    }
  }, [idEjecucion, onSummary]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const conteos = useMemo(() => conteosDe(filas || []), [filas]);
  const filasVisibles = useMemo(() => {
    const query = claveBusqueda(busqueda);
    return (filas || []).filter((fila) => coincideFiltro(fila, filtro) && (!query || textoBuscable(fila).includes(query)));
  }, [filas, filtro, busqueda]);
  const grupos = useMemo(() => gruposDe(filasVisibles), [filasVisibles]);
  const decisionesSeleccionadas = useMemo(
    () => (filas || []).filter((fila) => !autoDeduplicadaDe(fila) && (decisiones[fila.id_pendiente] === "ADD" || decisiones[fila.id_pendiente] === "KEEP_PENDING")).length,
    [filas, decisiones],
  );
  const requiereDecision = Boolean(resumen?.requiere_decision || resumen?.pendientes_por_decidir);

  const cambiarDecision = (idPendiente, decision) => {
    setDecisiones((actuales) => ({
      ...actuales,
      [idPendiente]: actuales[idPendiente] === decision ? undefined : decision,
    }));
  };

  const guardar = async () => {
    if (guardando) return;
    const solicitud = (filas || [])
      .filter((fila) => !autoDeduplicadaDe(fila) && (decisiones[fila.id_pendiente] === "ADD" || decisiones[fila.id_pendiente] === "KEEP_PENDING"))
      .map((fila) => ({
        id_pendiente: fila.id_pendiente,
        decision: decisiones[fila.id_pendiente],
      }));
    if (!solicitud.length) {
      setError("Selecciona ADD o KEEP_PENDING antes de guardar. Las propuestas sin decisión permanecerán visibles.");
      return;
    }
    setGuardando(true);
    setError("");
    try {
      const datos = await decidirPendientesNormalizador(idEjecucion, solicitud);
      setResultado(datos?.aprobacion || null);
      onSummary?.(datos?.aprobacion || null);
      setDecisiones({});
      await cargar();
      await onResolved?.(datos);
    } catch (errorGuardado) {
      setError(errorGuardado.message || "No se pudieron guardar las decisiones curriculares.");
    } finally {
      setGuardando(false);
    }
  };

  if (cargando && !filas) {
    return (
      <section className="mt-5 rounded-2xl border border-amber-200 bg-paper p-5 shadow-panel" aria-label="Revisión curricular">
        <div className="flex items-center gap-2 text-sm font-bold text-muted">
          <LoaderCircle className="animate-girar text-ulima" size={17} aria-hidden="true" />
          Revisando propuestas curriculares fuera del catálogo…
        </div>
      </section>
    );
  }

  if (!filas?.length && !resultado && !error && !requiereDecision && !resumen?.remaining_pending) return null;

  return (
    <section className="mt-5 rounded-2xl border border-amber-200 bg-paper p-5 shadow-panel sm:p-6" aria-label="Aprobación de propuestas curriculares">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-700">Checkpoint antes de CSV</p>
          <h2 className="mt-2 text-xl font-extrabold tracking-[-0.025em]">Revisión curricular requerida</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
            Las coincidencias exactas se deduplican automáticamente conservando un representante determinista y todas sus filas fuente. Los posibles duplicados semánticos y las herramientas sospechosas siguen requiriendo revisión humana antes de materializar los CSV canónicos.
          </p>
        </div>
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-50 text-amber-700">
          <Clock3 size={20} aria-hidden="true" />
        </span>
      </div>

      <div className="mt-5 grid gap-2 sm:grid-cols-3" aria-label="Resumen de aprobación curricular">
        <div className="rounded-xl border border-amber-200/70 bg-amber-50/70 px-3.5 py-3">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-amber-800">Sin decisión</p>
          <p className="mt-1 text-2xl font-extrabold text-amber-950">{resumen?.pendientes_por_decidir ?? filas?.length ?? 0}</p>
        </div>
        <div className="rounded-xl border border-line bg-fondo px-3.5 py-3">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-muted">Señales exactas / semánticas</p>
          <p className="mt-1 text-2xl font-extrabold text-ink">{conteos.exact} / {conteos.semantic}</p>
        </div>
        <div className="rounded-xl border border-line bg-fondo px-3.5 py-3">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-muted">Herramientas sospechosas</p>
          <p className="mt-1 text-2xl font-extrabold text-ink">{conteos.suspicious}</p>
        </div>
      </div>

      {filas?.length ? (
        <>
          <div className="mt-5 rounded-xl border border-line bg-fondo p-3.5">
            <label className="block text-xs font-bold text-ink" htmlFor={`buscar-propuestas-${idEjecucion}`}>
              Buscar en nombres, evidencia y origen
            </label>
            <div className="relative mt-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={16} aria-hidden="true" />
              <input
                id={`buscar-propuestas-${idEjecucion}`}
                type="search"
                value={busqueda}
                onChange={(event) => setBusqueda(event.target.value)}
                placeholder="Buscar por nombre, evidencia, curso o archivo"
                aria-label="Buscar propuestas curriculares"
                className="w-full rounded-lg border border-line bg-paper py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20"
              />
            </div>
            <div className="mt-3 flex gap-2 overflow-x-auto pb-1" role="group" aria-label="Filtros de propuestas curriculares">
              {FILTROS.map((opcion) => (
                <button
                  key={opcion.id}
                  type="button"
                  aria-pressed={filtro === opcion.id}
                  onClick={() => setFiltro(opcion.id)}
                  className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-bold transition focus:outline-none focus:ring-2 focus:ring-ulima/30 ${filtro === opcion.id ? "border-ulima bg-[#FFF5F1] text-ulima" : "border-line bg-paper text-muted hover:border-ulima/50 hover:text-ink"}`}
                >
                  {opcion.label} <span className="font-mono text-[10px]">{conteos[opcion.id]}</span>
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs leading-5 text-muted" aria-live="polite">
              Mostrando {filasVisibles.length} de {filas.length} {plural(filas.length, "propuesta pendiente", "propuestas pendientes")}. Las deduplicadas automáticamente permanecen auditables y no entran en la cola de decisiones.
            </p>
          </div>

          {grupos.length ? (
            <div className="mt-5 space-y-4">
              {grupos.map((grupo) => (
                <section key={grupo.tipo} className="rounded-xl border border-line bg-fondo p-3.5" aria-label={ETIQUETAS[grupo.tipo]}>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <h3 className="font-bold text-ink">{ETIQUETAS[grupo.tipo]}</h3>
                      <p className="mt-1 text-xs leading-5 text-muted">{DESCRIPCIONES[grupo.tipo]}</p>
                    </div>
                    <span className="font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">{plural(grupo.filas.length, "propuesta", "propuestas")}</span>
                  </div>
                  <div className="mt-3 space-y-3">
                    {grupo.filas.map((fila) => (
                      <ProposalCard
                        key={fila.id_pendiente}
                        fila={fila}
                        decision={decisiones[fila.id_pendiente]}
                        onDecision={cambiarDecision}
                        disabled={guardando}
                      />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-xl border border-dashed border-line bg-fondo px-3.5 py-4 text-sm leading-6 text-muted" role="status">
              No hay coincidencias para este filtro o búsqueda. Las propuestas sin decisión siguen pendientes y no se ocultaron de la cola.
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-amber-200 pt-4">
            <p className="max-w-2xl text-xs leading-5 text-muted">
              {decisionesSeleccionadas
                ? `${decisionesSeleccionadas} decisión${decisionesSeleccionadas === 1 ? "" : "es"} seleccionada${decisionesSeleccionadas === 1 ? "" : "s"}. Las propuestas restantes conservarán su evidencia y seguirán pendientes.`
                : "Selecciona ADD o KEEP_PENDING en cada propuesta que quieras resolver. Las propuestas sin decisión seguirán visibles."}
            </p>
            <button type="button" onClick={guardar} disabled={guardando || !decisionesSeleccionadas} className="inline-flex items-center gap-2 rounded-xl bg-ulima px-4 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:-translate-y-px hover:shadow-[0_8px_20px_rgba(255,81,23,0.24)] focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-60">
              {guardando ? <LoaderCircle className="animate-girar" size={16} /> : <Check size={16} />}
              {guardando ? "Guardando decisiones…" : `Guardar decisiones${decisionesSeleccionadas ? ` (${decisionesSeleccionadas})` : ""}`}
            </button>
          </div>
        </>
      ) : null}

      {resultado ? (
        <div role="status" className="mt-5 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-emerald-800">
          <Check className="mt-0.5 shrink-0 text-emerald-600" size={18} aria-hidden="true" />
          <div>
            <p className="text-sm font-extrabold">Decisiones guardadas</p>
            <p className="mt-1 text-sm leading-5">
              {resultado.accepted_in_request ?? resultado.accepted ?? 0} agregada{(resultado.accepted_in_request ?? resultado.accepted ?? 0) === 1 ? "" : "s"} en esta acción y {resultado.remaining_pending ?? 0} propuesta{(resultado.remaining_pending ?? 0) === 1 ? " permanece" : "s permanecen"} pendiente{(resultado.remaining_pending ?? 0) === 1 ? "" : "s"}.
            </p>
          </div>
        </div>
      ) : null}

      {resumen?.remaining_pending && !filas?.length ? (
        <p className="mt-4 text-xs leading-5 text-muted">Quedan {resumen.remaining_pending} propuestas mantenidas pendientes en los artefactos auditables de esta ejecución.</p>
      ) : null}

      {error ? (
        <div role="alert" className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-red-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={17} aria-hidden="true" />
          <p className="text-sm font-semibold leading-5">{error}</p>
        </div>
      ) : null}
    </section>
  );
}
