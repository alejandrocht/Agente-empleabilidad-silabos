"use client";

import { AlertTriangle, Check, Clock3, LoaderCircle, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  decidirPendientesNormalizador,
  obtenerPendientesNormalizador,
} from "../api/normalizador";
import {
  DESCRIPCIONES,
  ETIQUETAS,
  FILTROS,
  PACKAGE_PAGE_SIZE,
  autoDeduplicadaDe,
  claveBusqueda,
  coincideFiltro,
  conteosDe,
  evidenciaDe,
  gruposDe,
  pendientesResumen,
  plural,
  texto,
  textoBuscable,
} from "./curricularApprovalUtils";
import {
  DecisionBar,
  DiscardConfirmation,
  PackageCard,
  PackagePagination,
  ProposalCard,
} from "./CurricularApprovalCards";

export default function CurricularApprovalPanel({ idEjecucion, onSummary, onResolved }) {
  const [filas, setFilas] = useState(null);
  const [paquetes, setPaquetes] = useState(null);
  const [resumen, setResumen] = useState(null);
  const [revision, setRevision] = useState(null);
  const [decisiones, setDecisiones] = useState({});
  const [filtro, setFiltro] = useState("all");
  const [busqueda, setBusqueda] = useState("");
  const [packagePage, setPaginaPaquetes] = useState(1);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [resultado, setResultado] = useState(null);
  const [paqueteADescartar, setPaqueteADescartar] = useState("");
  const [motivoDescarte, setMotivoDescarte] = useState("");

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
      setPaquetes(Array.isArray(datos?.paquetes) ? datos.paquetes : null);
      setPaginaPaquetes(1);
      setRevision(texto(datos?.revision) || null);
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
  const modoPaquetes = Array.isArray(paquetes) && paquetes.length > 0;
  const paquetesVisibles = useMemo(() => {
    const query = claveBusqueda(busqueda);
    return (paquetes || []).filter((paquete) => !query || textoBuscable({
      ...paquete,
      propuesta: { nombre: paquete?.id_paquete_chh },
      evidencia: (paquete?.filas || []).flatMap((fila) => evidenciaDe(fila)),
      id_pendiente: paquete?.id_paquete_chh,
    }).includes(query));
  }, [paquetes, busqueda]);
  const totalPackagePages = Math.max(1, Math.ceil(paquetesVisibles.length / PACKAGE_PAGE_SIZE));
  const packagePageSegura = Math.min(packagePage, totalPackagePages);
  const packagePageItems = useMemo(() => {
    const inicio = (packagePageSegura - 1) * PACKAGE_PAGE_SIZE;
    return paquetesVisibles.slice(inicio, inicio + PACKAGE_PAGE_SIZE);
  }, [packagePageSegura, paquetesVisibles]);
  const filasVisibles = useMemo(() => {
    const query = claveBusqueda(busqueda);
    return (filas || []).filter((fila) => coincideFiltro(fila, filtro) && (!query || textoBuscable(fila).includes(query)));
  }, [filas, filtro, busqueda]);
  const grupos = useMemo(() => gruposDe(filasVisibles), [filasVisibles]);
  const decisionesSeleccionadas = useMemo(
    () => modoPaquetes
      ? (paquetes || []).filter((paquete) => decisiones[paquete.id_paquete_chh || paquete.package_id] === "ADD" || decisiones[paquete.id_paquete_chh || paquete.package_id] === "KEEP_PENDING").length
      : (filas || []).filter((fila) => !autoDeduplicadaDe(fila) && (decisiones[fila.id_pendiente] === "ADD" || decisiones[fila.id_pendiente] === "KEEP_PENDING")).length,
    [filas, paquetes, decisiones, modoPaquetes],
  );
  const pendientesVisibles = pendientesResumen(resumen, filas, paquetes);
  const requiereDecision = Boolean(resumen?.requiere_decision || pendientesVisibles);

  useEffect(() => {
    setPaginaPaquetes(1);
  }, [busqueda, filtro, modoPaquetes]);

  const cambiarDecision = (idPendiente, decision) => {
    setDecisiones((actuales) => ({
      ...actuales,
      [idPendiente]: actuales[idPendiente] === decision ? undefined : decision,
    }));
  };

  const guardar = async () => {
    if (guardando) return;
    const solicitud = modoPaquetes
      ? (paquetes || [])
        .filter((paquete) => decisiones[paquete.id_paquete_chh || paquete.package_id] === "ADD" || decisiones[paquete.id_paquete_chh || paquete.package_id] === "KEEP_PENDING")
        .map((paquete) => ({ id_paquete_chh: paquete.id_paquete_chh || paquete.package_id, decision: decisiones[paquete.id_paquete_chh || paquete.package_id] }))
      : (filas || [])
        .filter((fila) => !autoDeduplicadaDe(fila) && (decisiones[fila.id_pendiente] === "ADD" || decisiones[fila.id_pendiente] === "KEEP_PENDING"))
        .map((fila) => ({ id_pendiente: fila.id_pendiente, decision: decisiones[fila.id_pendiente] }));
    if (!solicitud.length) {
      setError("Selecciona una acción antes de guardar. Las propuestas sin decisión permanecerán visibles.");
      return;
    }
    setGuardando(true);
    setError("");
    try {
      const datos = modoPaquetes
        ? await decidirPendientesNormalizador(idEjecucion, solicitud, "ejecutor", revision)
        : await decidirPendientesNormalizador(idEjecucion, solicitud);
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

  const descartarPaquete = async () => {
    if (guardando || !paqueteADescartar || !texto(motivoDescarte)) return;
    setGuardando(true);
    setError("");
    try {
      const datos = await decidirPendientesNormalizador(
        idEjecucion,
        [{ id_paquete_chh: paqueteADescartar, decision: "DISCARD", reason: texto(motivoDescarte) }],
        "ejecutor",
        revision,
      );
      setResultado(datos?.aprobacion || null);
      onSummary?.(datos?.aprobacion || null);
      setPaqueteADescartar("");
      setMotivoDescarte("");
      await cargar();
      await onResolved?.(datos);
    } catch (errorDescarte) {
      setError(errorDescarte.message || "No se pudo descartar el paquete curricular.");
    } finally {
      setGuardando(false);
    }
  };

  if (cargando && !filas) {
    return (
      <section className="mt-5 rounded-2xl border border-line bg-paper p-5 font-body shadow-sm" aria-label="Revisión curricular">
        <div className="flex items-center gap-2 text-sm font-bold text-muted">
          <LoaderCircle className="animate-girar text-ulima" size={17} aria-hidden="true" />
          Revisando propuestas curriculares fuera del catálogo…
        </div>
      </section>
    );
  }

  if (!filas?.length && !paquetes?.length && !resultado && !error && !requiereDecision && !resumen?.remaining_pending) return null;

  return (
    <section className="mt-5 rounded-2xl border border-line border-t-4 border-t-ulima bg-paper p-5 font-body shadow-sm sm:p-6" aria-label="Aprobación de propuestas curriculares">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-ulima">Checkpoint antes de CSV</p>
          <h2 className="mt-2 text-xl font-extrabold tracking-[-0.025em]">Revisión curricular requerida</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
            Las coincidencias exactas se deduplican automáticamente conservando un representante determinista y todas sus filas fuente. Los posibles duplicados semánticos y las herramientas sospechosas siguen requiriendo revisión humana antes de materializar los CSV canónicos.
          </p>
        </div>
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-ulima/20 bg-ulima/5 text-ulima">
          <Clock3 size={20} aria-hidden="true" />
        </span>
      </div>

      <div className="mt-5 grid gap-2 sm:grid-cols-3" aria-label="Resumen de aprobación curricular">
        <div className="rounded-xl border border-ulima/25 bg-ulima/5 px-3.5 py-3">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-ulima">Sin decisión</p>
          <p className="mt-1 text-2xl font-extrabold text-ink">{pendientesVisibles}</p>
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

      {modoPaquetes ? (
        <>
          <div className="mt-5 rounded-xl border border-line bg-fondo p-3.5">
            <label className="block text-xs font-bold text-ink" htmlFor={`buscar-paquetes-${idEjecucion}`}>Buscar en paquetes, evidencia y origen</label>
            <div className="relative mt-2"><Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" size={16} aria-hidden="true" /><input id={`buscar-paquetes-${idEjecucion}`} aria-label="Buscar paquetes curriculares" type="search" value={busqueda} onChange={(event) => setBusqueda(event.target.value)} className="w-full rounded-lg border border-line bg-paper py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20" /></div>
            <p className="mt-2 text-xs leading-5 text-muted" aria-live="polite">Mostrando {paquetesVisibles.length} de {paquetes.length} paquetes fuente. Las filas y alias permanecen dentro del paquete para auditoría.</p>
          </div>
          {paquetesVisibles.length ? <>
            <div className="mt-5 space-y-3 pb-28">{packagePageItems.map((paquete) => <PackageCard key={paquete.id_paquete_chh || paquete.package_id} paquete={paquete} decision={decisiones[paquete.id_paquete_chh || paquete.package_id]} onDecision={cambiarDecision} onDiscard={(packageId) => { setPaqueteADescartar(packageId); setMotivoDescarte(""); }} disabled={guardando} />)}</div>
            <PackagePagination page={packagePageSegura} totalPages={totalPackagePages} total={paquetesVisibles.length} onChange={setPaginaPaquetes} />
          </> : <div className="mt-5 rounded-xl border border-dashed border-line bg-fondo px-3.5 py-4 text-sm leading-6 text-muted" role="status">No hay coincidencias para esta búsqueda.</div>}
          <div className="pb-20">
            <DiscardConfirmation packageId={paqueteADescartar} reason={motivoDescarte} onReasonChange={setMotivoDescarte} onCancel={() => { setPaqueteADescartar(""); setMotivoDescarte(""); }} onConfirm={descartarPaquete} disabled={guardando} />
            <DecisionBar count={decisionesSeleccionadas} onSave={guardar} disabled={guardando} guardando={guardando} mode="packages" />
          </div>
        </>
      ) : filas?.length ? (
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
                  className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-bold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/40 focus-visible:ring-offset-1 ${filtro === opcion.id ? "border-ulima bg-ulima/5 text-ink" : "border-line bg-paper text-muted hover:border-ulima/50 hover:text-ink"}`}
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

          <div className="pb-24">
            <DecisionBar count={decisionesSeleccionadas} onSave={guardar} disabled={guardando} guardando={guardando} mode="legacy" />
          </div>
        </>
      ) : null}

      {resultado ? (
        <div role="status" className="mt-5 flex items-start gap-3 rounded-xl border border-line bg-fondo px-3.5 py-3 text-ink">
          <Check className="mt-0.5 shrink-0 text-ulima" size={18} aria-hidden="true" />
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
