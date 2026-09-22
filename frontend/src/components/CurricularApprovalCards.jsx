"use client";

import { Check, LoaderCircle } from "lucide-react";
import {
  ETIQUETAS,
  autoDeduplicadaDe,
  camposDeProveniencia,
  decisionLabel,
  descripcionPropuesta,
  evidenciaDe,
  etiquetasDeSeñal,
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
      <span className="mt-0.5 block font-body font-bold">
        {esAdd ? "Agregar al catálogo" : "Mantener pendiente"}
      </span>
    </button>
  );
}

function ProposalCard({
  fila,
  decision,
  onDecision,
  onImmediateAdd,
  onDiscard,
  disabled,
}) {
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
              <p className="mt-1 text-sm leading-5 text-muted">
                {descripcionPropuesta(fila)}
              </p>
            </div>
            <span className="rounded-lg border border-line bg-fondo px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">
              {ETIQUETAS[tipoDe(fila)]}
            </span>
          </div>

          {señales.length ? (
            <div
              className="mt-3 space-y-2"
              aria-label={`Señales de revisión para ${nombre}`}
            >
              <div className="flex flex-wrap gap-1.5">
                {señales.map((señal) => (
                  <span
                    key={señal.id}
                    className={`rounded-lg border px-2 py-1 font-mono text-[9px] font-bold uppercase tracking-[0.06em] ${señal.className}`}
                  >
                    {señal.label}
                  </span>
                ))}
              </div>
              <ul className="space-y-1 text-xs leading-5 text-muted">
                {señales.map((señal) => (
                  <li key={`${señal.id}-explanation`}>
                    <span className="font-bold text-ink">Por qué:</span>{" "}
                    {señal.explanation}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div
            className="mt-4 rounded-lg border border-line bg-fondo p-3"
            aria-label={`Proveniencia y evidencia de ${nombre}`}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
                Proveniencia y evidencia de fuente
              </p>
              <span className="font-mono text-[9px] text-muted">
                {fila.id_pendiente}
              </span>
            </div>
            {proveniencia.length ? (
              <dl className="mt-2 grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2">
                {proveniencia.map(([etiqueta, valor]) => (
                  <div key={etiqueta} className="min-w-0">
                    <dt className="font-bold text-muted">{etiqueta}</dt>
                    <dd className="break-words text-ink [overflow-wrap:anywhere]">
                      {texto(valor)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-xs leading-5 text-muted">
                El backend no reportó metadatos de ubicación para esta
                propuesta; la identidad y decisión se conservan.
              </p>
            )}
            <div className="mt-3 border-t border-line pt-2">
              <p className="text-xs font-bold text-ink">Evidencia textual</p>
              {evidencia.length ? (
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-ink">
                  {evidencia.map((item, indice) => (
                    <li key={`${fila.id_pendiente}-evidencia-${indice}`}>
                      {item}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs leading-5 text-muted">
                  No se adjuntó evidencia textual.
                </p>
              )}
            </div>
          </div>
        </div>

        {autoDeduplicada ? (
          <div
            className="shrink-0 rounded-lg border border-line bg-fondo p-3 lg:w-64"
            aria-label={`Deduplicación automática para ${nombre}`}
          >
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-ink">
              Deduplicada automáticamente
            </p>
            <p className="mt-1 text-xs leading-5 text-muted">
              Esta evidencia queda en los artefactos auditables. Solo el
              representante {representanteDe(fila) || "determinista"} puede
              recibir una decisión.
            </p>
          </div>
        ) : (
          <div
            className="shrink-0 rounded-lg border border-line bg-fondo p-3 lg:w-64"
            aria-label={`Decisión para ${nombre}`}
          >
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted">
              Decisión explícita
            </p>
            <p className="mt-1 text-xs leading-5 text-muted">
              Elige una acción para esta propuesta. Las señales semánticas
              siguen requiriendo revisión humana.
            </p>
            <div className="mt-3 grid gap-2">
              <DecisionButton
                decision="ADD"
                activa={decision === "ADD"}
                nombre={nombre}
                onClick={() =>
                  onImmediateAdd
                    ? onImmediateAdd(fila.id_pendiente)
                    : onDecision(fila.id_pendiente, "ADD")
                }
                disabled={disabled}
              />
              <DecisionButton
                decision="KEEP_PENDING"
                activa={decision === "KEEP_PENDING"}
                nombre={nombre}
                onClick={() => onDecision(fila.id_pendiente, "KEEP_PENDING")}
                disabled={disabled}
              />
              {onDiscard ? (
                <button
                  type="button"
                  onClick={() => onDiscard(fila.id_pendiente)}
                  disabled={disabled}
                  className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-left text-xs font-extrabold text-red-800 transition hover:border-red-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Descartar propuesta
                </button>
              ) : null}
            </div>
            <p
              className="mt-2 text-[11px] leading-4 text-muted"
              aria-live="polite"
            >
              {decision
                ? `Seleccionado: ${decisionLabel(decision)}`
                : "Sin decisión; seguirá pendiente."}
            </p>
          </div>
        )}
      </div>
    </article>
  );
}

function DecisionBar({ count, onSave, disabled, guardando }) {
  const selectedLabel = `${count} ${count === 1 ? "decisión seleccionada" : "decisiones seleccionadas"}`;
  return (
    <div
      className="sticky bottom-3 z-20 -mx-5 mt-7 rounded-xl border border-line bg-paper px-5 py-4 shadow-[0_-4px_12px_rgba(0,0,0,0.06)] sm:-mx-6 sm:px-6"
      data-testid="curricular-decision-bar"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-extrabold text-ink">
            {count ? selectedLabel : "No hay decisiones seleccionadas"}
          </p>
          <p className="mt-1 text-xs leading-5 text-muted">
            {count
              ? "Las decisiones restantes conservarán su evidencia y seguirán pendientes."
              : "Selecciona una acción para resolver elementos."}
          </p>
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={disabled || !count}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-institucional-naranja px-4 py-2.5 text-sm font-extrabold text-institucional-negro shadow-sm transition-colors hover:bg-institucional-naranja/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-ulima/50 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {guardando ? (
            <LoaderCircle className="animate-girar" size={16} />
          ) : (
            <Check size={16} />
          )}
          {guardando
            ? "Guardando decisiones…"
            : `Guardar decisiones${count ? ` (${count})` : ""}`}
        </button>
      </div>
    </div>
  );
}

export { DecisionBar, ProposalCard };
