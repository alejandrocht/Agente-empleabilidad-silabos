"use client";

import { Check, ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react";
import {
  ETIQUETAS,
  PACKAGE_PAGE_SIZE,
  PENDING_SKILL_LABEL,
  autoDeduplicadaDe,
  camposDeProveniencia,
  componentesDe,
  componentesLegibles,
  decisionLabel,
  descripcionPropuesta,
  evidenciaDe,
  etiquetasDeSeñal,
  nombreLegible,
  nombrePropuesto,
  representanteDe,
  texto,
  tipoDe,
} from "./curricularApprovalUtils";

function DecisionButton({ decision, activa, nombre, onClick, disabled }) {
  const esAdd = decision === "ADD";
  return (
    <button
      type="button"
      aria-label={`${decisionLabel(decision)} para ${nombre}`}
      aria-pressed={activa}
      data-decision={decision}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-3 py-2 text-left text-xs font-extrabold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${
        activa
          ? esAdd
            ? "border-ulima bg-ulima/5 text-ink"
            : "border-institucional-negro bg-ash text-ink"
          : "border-line bg-paper text-muted hover:border-ulima/60 hover:text-ink"
      }`}
    >
      <span className="mt-0.5 block font-body font-bold">{esAdd ? "Agregar al perfil" : "Mantener pendiente"}</span>
    </button>
  );
}

function ComponentDetails({ niveles, packageId }) {
  const secciones = niveles
    .map(([label, tipo, values]) => ({ label, tipo, componentes: componentesLegibles(values, tipo) }))
    .filter(({ componentes }) => componentes.length);
  if (!secciones.length) return null;
  return (
    <section aria-label={`Detalles de componentes del paquete ${packageId}`}>
      <h4 className="text-sm font-extrabold text-ink">Detalle de componentes</h4>
      <div className="mt-3 grid gap-4 lg:grid-cols-3">
        {secciones.map(({ label, tipo, componentes }) => (
          <section key={tipo} aria-label={`${label} del paquete ${packageId}`}>
            <h5 className="text-xs font-extrabold uppercase tracking-[0.08em] text-muted">{label}</h5>
            <dl className="mt-2 space-y-3 text-xs leading-5">
              {componentes.map(({ nombre, descripcion }, indice) => (
                <div key={`${tipo}-${indice}-${nombre}`}>
                  <dt className="break-words font-bold text-ink">{nombre}</dt>
                  <dd className="mt-0.5 break-words text-muted">{descripcion}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </section>
  );
}

function CanonicalTripleRows({ relaciones }) {
  if (!Array.isArray(relaciones) || !relaciones.length) {
    return <p className="mt-1 text-xs leading-5 text-muted">No hay una triple canónica publicada para este paquete.</p>;
  }
  return (
    <ul className="mt-2 space-y-2" aria-label="Triples canónicas del paquete">
      {relaciones.map((relacion, indice) => {
        const nombres = ["competencia", "habilidad", "herramienta"]
          .map((tipo) => nombreLegible(relacion?.[tipo]?.nombre) || "Sin nombre catalogado")
          .filter((nombre, posicion) => posicion < 2 || nombre !== "Sin nombre catalogado");
        return <li key={`triple-${indice}`} className="rounded-lg border border-line bg-paper px-3 py-2 text-xs leading-5 text-ink [overflow-wrap:anywhere]">{nombres.join(" → ")}</li>;
      })}
    </ul>
  );
}

function PendingPackageProposals({ propuestas }) {
  if (!Array.isArray(propuestas) || !propuestas.length) return null;
  return (
    <section aria-label="Propuestas pendientes del paquete">
      <h4 className="text-sm font-extrabold text-ink">Propuestas pendientes</h4>
      <ul className="mt-2 space-y-2 text-xs leading-5 text-muted">
        {propuestas.map((propuesta, indice) => <li key={`${propuesta?.id_pendiente || "proposal"}-${indice}`} className="rounded-lg border border-line bg-paper p-3"><p className="break-words font-bold text-ink">{nombreLegible(propuesta?.nombre) || PENDING_SKILL_LABEL}</p><p className="mt-1 break-words">{texto(propuesta?.descripcion) || "Sin descripción adicional."}</p></li>)}
      </ul>
    </section>
  );
}

function PackageComponentsSummary({ niveles, packageId }) {
  const secciones = niveles.map(([label, tipo, values]) => ({
    label,
    tipo,
    componentes: componentesLegibles(values, tipo),
  }));

  return (
    <section className="mt-5" aria-label={`Componentes curriculares del paquete ${packageId}`}>
      <h4 className="text-sm font-extrabold text-ink">Componentes del paquete</h4>
      <p className="mt-1 text-xs leading-5 text-muted">Entidades recibidas desde la fuente curricular, separadas de las triples canónicas.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {secciones.map(({ label, tipo, componentes }) => (
          <div key={tipo} className="min-w-0 rounded-lg border border-line bg-fondo px-3 py-2">
            <p className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">{label}</p>
            {componentes.length ? (
              <ul className="mt-1 space-y-1 text-sm font-bold text-ink">
                {componentes.map(({ nombre }, indice) => (
                  <li key={`${tipo}-${indice}-${nombre}`} className="break-words [overflow-wrap:anywhere]">{nombre}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm font-semibold text-muted">No presente</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function PackageCard({ paquete, decision, onDecision, onDiscard, disabled }) {
  const competencias = componentesDe(paquete, "competencias");
  const habilidades = componentesDe(paquete, "habilidades");
  const herramientas = componentesDe(paquete, "herramientas");
  const filas = Array.isArray(paquete?.filas) ? paquete.filas : [];
  const identidad = paquete?.source_identity || {};
  const evidenciaFuente = paquete?.source_evidence || {};
  const filasFuente = Array.isArray(evidenciaFuente?.rows) ? evidenciaFuente.rows : filas;
  const evidencia = filasFuente.flatMap((fila) => evidenciaDe(fila));
  const packageId = texto(paquete?.id_paquete_chh || paquete?.package_id);
  const señales = [...new Map(
    filas
      .flatMap((fila) => etiquetasDeSeñal(fila))
      .map((señal) => [señal.id, señal]),
  ).values()];
  const niveles = [
    ["Competencia", "competencias", competencias],
    ["Habilidad", "habilidades", habilidades],
    ["Herramienta", "herramientas", herramientas],
  ];
  return (
    <article className="rounded-2xl border border-line bg-paper shadow-sm transition-colors hover:border-ulima/40" data-testid="curricular-package-card" data-package-id={packageId}>
      <div className="p-4 sm:p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-ulima">Paquete CHH</p>
              <span className={`rounded-lg border px-2 py-1 font-mono text-[9px] font-bold ${decision === "ADD" ? "border-ulima/40 bg-ulima/5 text-ink" : decision === "KEEP_PENDING" ? "border-institucional-negro/40 bg-ash text-ink" : "border-line bg-fondo text-muted"}`}>{decisionLabel(decision)}</span>
            </div>
            <h3 className="mt-2 text-base font-extrabold text-ink">Componentes curriculares</h3>
            <p className="mt-2 text-xs leading-5 text-muted">{texto(identidad.carrera || paquete?.career) || "Carrera no reportada"} · {texto(identidad.periodo || paquete?.period) || "Periodo no reportado"} · curso {texto(identidad.id_curso || paquete?.id_curso) || "no reportado"}</p>
            <PackageComponentsSummary niveles={niveles} packageId={packageId} />
            <section className="mt-5" aria-label={`Relaciones canónicas del paquete ${packageId}`}>
              <h4 className="text-sm font-extrabold text-ink">Triples canónicas</h4>
              <p className="mt-1 text-xs leading-5 text-muted">Cada fila representa una relación explícita; no se combinan las listas de componentes.</p>
              <CanonicalTripleRows relaciones={paquete?.relaciones_canonicas} />
            </section>
            <div className="mt-5">
              <PendingPackageProposals propuestas={paquete?.propuestas_pendientes} />
            </div>
          </div>
          <div className="shrink-0 border-t border-line pt-4 xl:w-64 xl:border-l xl:border-t-0 xl:pl-5 xl:pt-0" aria-label={`Decisión para paquete ${packageId}`}>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted">Decisión visible</p>
            <p className="mt-1 text-xs leading-5 text-muted">Se aplica atómicamente a todas las relaciones del paquete.</p>
            <div className="mt-3 grid gap-2">
              <DecisionButton decision="ADD" activa={decision === "ADD"} nombre={`paquete ${packageId}`} onClick={() => onDecision(packageId, "ADD")} disabled={disabled} />
              <DecisionButton decision="KEEP_PENDING" activa={decision === "KEEP_PENDING"} nombre={`paquete ${packageId}`} onClick={() => onDecision(packageId, "KEEP_PENDING")} disabled={disabled} />
              <button type="button" onClick={() => onDiscard(packageId)} disabled={disabled} className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-left text-xs font-extrabold text-red-800 transition hover:border-red-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 disabled:cursor-not-allowed disabled:opacity-60">Descartar paquete</button>
            </div>
            <p className="mt-2 text-[11px] leading-4 text-muted" aria-live="polite">{decision ? `Seleccionado: ${decisionLabel(decision)}` : "Sin decisión; seguirá pendiente."}</p>
          </div>
        </div>
      </div>
      <details className="border-t border-line">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-bold text-ink transition hover:bg-fondo focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/40 focus-visible:ring-inset sm:px-5">
          <span>Ver evidencia, proveniencia y relaciones</span>
          <span className="font-mono text-[10px] font-medium text-muted">{filas.length} {filas.length === 1 ? "fila fuente" : "filas fuente"}</span>
        </summary>
        <div className="space-y-5 border-t border-line bg-fondo px-4 py-4 sm:px-5">
          <section aria-label={`Proveniencia y evidencia del paquete ${packageId}`}>
            <h4 className="text-sm font-extrabold text-ink">Proveniencia y evidencia de fuente</h4>
            <p className="mt-1 text-xs leading-5 text-muted">Fuentes, extractos y evidencias que sustentan las entidades del paquete.</p>
            <dl className="mt-3 grid gap-x-5 gap-y-2 text-xs sm:grid-cols-2">
              <div><dt className="font-bold text-muted">Carrera</dt><dd className="mt-0.5 break-words text-ink">{texto(identidad.carrera || paquete?.career) || "Carrera no reportada"}</dd></div>
              <div><dt className="font-bold text-muted">Periodo</dt><dd className="mt-0.5 break-words text-ink">{texto(identidad.periodo || paquete?.period) || "Periodo no reportado"}</dd></div>
              <div><dt className="font-bold text-muted">Curso</dt><dd className="mt-0.5 break-words text-ink">{texto(identidad.id_curso || paquete?.id_curso) || "Curso no reportado"}</dd></div>
              <div><dt className="font-bold text-muted">Sílabo</dt><dd className="mt-0.5 break-words text-ink">{texto(identidad.id_silabo || paquete?.id_silabo) || "Sílabo no reportado"}</dd></div>
            </dl>
            <div className="mt-3 border-t border-line pt-3">
              <p className="text-xs font-bold text-ink">Evidencia textual</p>
              {evidencia.length ? <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-muted">{evidencia.map((item, index) => <li key={`${packageId}-evidence-${index}`}>{item}</li>)}</ul> : <p className="mt-1 text-xs leading-5 text-muted">No se adjuntó evidencia textual.</p>}
            </div>
          </section>

          <ComponentDetails niveles={niveles} packageId={packageId} />

          {señales.length ? <section aria-label={`Señales del paquete ${packageId}`}>
            <h4 className="text-sm font-extrabold text-ink">Señales de revisión</h4>
            <ul className="mt-2 space-y-2 text-xs leading-5 text-muted">{señales.map((señal) => <li key={señal.id}><span className="font-bold text-ink">{señal.label}.</span> {señal.explanation}</li>)}</ul>
          </section> : null}

          <section aria-label={`Relaciones fuente auditables del paquete ${packageId}`}>
            <h4 className="text-sm font-extrabold text-ink">Relaciones fuente auditables</h4>
            {Array.isArray(evidenciaFuente?.relationships) && evidenciaFuente.relationships.length ? <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs leading-5 text-muted">{evidenciaFuente.relationships.map((relacion, indice) => <li key={`${packageId}-source-relation-${indice}`} className="font-mono">{JSON.stringify(relacion)}</li>)}</ul> : Array.isArray(paquete?.relaciones) && paquete.relaciones.length ? <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs leading-5 text-muted">{paquete.relaciones.map((relacion, indice) => <li key={`${packageId}-legacy-relation-${indice}`} className="font-mono">{JSON.stringify(relacion)}</li>)}</ul> : <p className="mt-1 text-xs leading-5 text-muted">No se reportaron relaciones fuente adicionales.</p>}
          </section>

          <section aria-label={`Datos técnicos del paquete ${packageId}`}>
            <h4 className="text-sm font-extrabold text-ink">Datos técnicos (IDs y metadatos)</h4>
            <dl className="mt-2 grid gap-x-5 gap-y-2 text-xs sm:grid-cols-2">
              <div><dt className="font-bold text-muted">ID del paquete</dt><dd className="mt-0.5 break-all font-mono text-ink">{packageId || "No reportado"}</dd></div>
              <div><dt className="font-bold text-muted">Alias auditables</dt><dd className="mt-0.5 font-mono text-ink">{Array.isArray(paquete?.aliases) ? paquete.aliases.length : 0}</dd></div>
              <div><dt className="font-bold text-muted">Filas fuente</dt><dd className="mt-0.5 font-mono text-ink">{filas.length}</dd></div>
              <div><dt className="font-bold text-muted">Estado de decisión</dt><dd className="mt-0.5 text-ink">{decisionLabel(decision === undefined ? "KEEP_PENDING" : decision)}</dd></div>
            </dl>
          </section>
        </div>
      </details>
    </article>
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
            <span className="rounded-lg border border-line bg-fondo px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">
              {ETIQUETAS[tipoDe(fila)]}
            </span>
          </div>

          {señales.length ? (
            <div className="mt-3 space-y-2" aria-label={`Señales de revisión para ${nombre}`}>
              <div className="flex flex-wrap gap-1.5">
                {señales.map((señal) => (
                  <span key={señal.id} className={`rounded-lg border px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-[0.06em] ${señal.className}`}>
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

          <div className="mt-4 rounded-lg border border-line bg-fondo p-3" aria-label={`Proveniencia y evidencia de ${nombre}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-muted">Proveniencia y evidencia de fuente</p>
              <span className="font-mono text-[9px] text-muted">{fila.id_pendiente}</span>
            </div>
            {proveniencia.length ? (
              <dl className="mt-2 grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
                {proveniencia.map(([etiqueta, valor]) => (
                  <div key={etiqueta} className="min-w-0">
                    <dt className="font-bold text-muted">{etiqueta}</dt>
                    <dd className="break-words text-ink [overflow-wrap:anywhere]">{texto(valor)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-xs leading-5 text-muted">El backend no reportó metadatos de ubicación para esta propuesta; la identidad y decisión se conservan.</p>
            )}
            <div className="mt-3 border-t border-line pt-2">
              <p className="text-xs font-bold text-ink">Evidencia textual</p>
              {evidencia.length ? (
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-ink">
                  {evidencia.map((item, indice) => <li key={`${fila.id_pendiente}-evidencia-${indice}`}>{item}</li>)}
                </ul>
              ) : (
                <p className="mt-1 text-xs leading-5 text-muted">No se adjuntó evidencia textual.</p>
              )}
            </div>
          </div>
        </div>

        {autoDeduplicada ? (
          <div className="shrink-0 rounded-lg border border-line bg-fondo p-3 lg:w-64" aria-label={`Deduplicación automática para ${nombre}`}>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-ink">Deduplicada automáticamente</p>
            <p className="mt-1 text-xs leading-5 text-muted">Esta evidencia queda en los artefactos auditables. Solo el representante {representanteDe(fila) || "determinista"} puede recibir una decisión.</p>
          </div>
        ) : (
          <div className="shrink-0 rounded-lg border border-line bg-fondo p-3 lg:w-64" aria-label={`Decisión para ${nombre}`}>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted">Decisión explícita</p>
            <p className="mt-1 text-xs leading-5 text-muted">Elige una acción para esta propuesta. Las señales semánticas y las herramientas sospechosas siguen requiriendo revisión humana.</p>
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
              {decision ? `Seleccionado: ${decisionLabel(decision)}` : "Sin decisión; seguirá pendiente."}
            </p>
          </div>
        )}
      </div>
    </article>
  );
}

function PackagePagination({ page, totalPages, total, onChange }) {
  const start = total ? ((page - 1) * PACKAGE_PAGE_SIZE) + 1 : 0;
  const end = total ? Math.min(page * PACKAGE_PAGE_SIZE, total) : 0;
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-xs font-semibold text-muted" aria-live="polite">Paquetes {start}–{end} de {total} · Página {page} de {totalPages}</p>
      <nav className="flex items-center gap-2" aria-label="Paginación de paquetes curriculares">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          aria-label="Página anterior de paquetes"
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft size={14} aria-hidden="true" /> Anterior
        </button>
        <span className="min-w-16 text-center font-mono text-xs font-bold text-ink" aria-current="page">{page} / {totalPages}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          aria-label="Página siguiente de paquetes"
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Siguiente <ChevronRight size={14} aria-hidden="true" />
        </button>
      </nav>
    </div>
  );
}

function DecisionBar({ count, onSave, disabled, guardando, mode }) {
  const selectedLabel = mode === "packages"
    ? `${count} ${count === 1 ? "paquete seleccionado" : "paquetes seleccionados"}`
    : `${count} ${count === 1 ? "decisión seleccionada" : "decisiones seleccionadas"}`;
  return (
    <div className="sticky bottom-3 z-20 -mx-5 mt-7 rounded-xl border border-line bg-paper px-5 py-4 shadow-[0_-4px_12px_rgba(0,0,0,0.06)] sm:-mx-6 sm:px-6" data-testid="curricular-decision-bar">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-extrabold text-ink">{count ? selectedLabel : "No hay decisiones seleccionadas"}</p>
          <p className="mt-1 text-xs leading-5 text-muted">{count ? "Las decisiones restantes conservarán su evidencia y seguirán pendientes." : "Selecciona una acción para resolver elementos."}</p>
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={disabled || !count}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-institucional-naranja px-4 py-2.5 text-sm font-extrabold text-institucional-negro shadow-sm transition-colors hover:bg-institucional-naranja/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/50 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {guardando ? <LoaderCircle className="animate-girar" size={16} /> : <Check size={16} />}
          {guardando ? "Guardando decisiones…" : `Guardar decisiones${count ? ` (${count})` : ""}`}
        </button>
      </div>
    </div>
  );
}

function DiscardConfirmation({ packageId, reason, onReasonChange, onCancel, onConfirm, disabled }) {
  if (!packageId) return null;
  return (
    <section className="mt-5 rounded-xl border border-red-300 bg-red-50 p-4" role="dialog" aria-modal="false" aria-labelledby="discard-package-title">
      <h3 id="discard-package-title" className="text-sm font-extrabold text-red-900">Descartar paquete</h3>
      <p className="mt-1 text-xs leading-5 text-red-800">Esta acción retira el paquete de la cola y de la publicación canónica de esta ejecución. La evidencia y el motivo permanecen auditables.</p>
      <label className="mt-3 block text-xs font-bold text-red-900" htmlFor="discard-package-reason">Motivo del descarte</label>
      <textarea id="discard-package-reason" value={reason} onChange={(event) => onReasonChange(event.target.value)} rows={3} required className="mt-1 w-full rounded-lg border border-red-300 bg-paper p-2 text-sm text-ink outline-none focus:border-red-600 focus:ring-2 focus:ring-red-200" />
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={onConfirm} disabled={disabled || !texto(reason)} className="rounded-lg bg-red-700 px-3 py-2 text-xs font-extrabold text-white transition hover:bg-red-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60">Confirmar descarte</button>
        <button type="button" onClick={onCancel} disabled={disabled} className="rounded-lg border border-red-300 bg-paper px-3 py-2 text-xs font-bold text-red-900 transition hover:border-red-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400">Cancelar</button>
      </div>
    </section>
  );
}



export {
  DecisionBar,
  DiscardConfirmation,
  PackageCard,
  PackagePagination,
  ProposalCard,
};
