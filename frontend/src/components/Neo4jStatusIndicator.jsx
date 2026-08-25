"use client";

import { useEffect, useRef, useState } from "react";
import { obtenerEstadoNeo4j } from "../api/neo4j";

const POLLING_INTERVAL_MS = 5000;

const STATUS_DETAILS = {
  loading: {
    label: "verificando",
    className: "bg-slate-400",
  },
  connected: {
    label: "conectado",
    className: "bg-emerald-500",
  },
  schema_mismatch: {
    label: "esquema incompatible",
    className: "bg-amber-500",
  },
  disconnected: {
    label: "no disponible",
    className: "bg-rose-500",
  },
};

function toStatusState(status) {
  return status?.state === "connected" || status?.state === "schema_mismatch"
    ? status.state
    : "disconnected";
}

export default function Neo4jStatusIndicator() {
  const [state, setState] = useState("loading");
  const inFlight = useRef(false);
  const controller = useRef(null);
  const status = STATUS_DETAILS[state];
  const accessibleLabel = `Estado de Neo4j: ${status.label}`;

  useEffect(() => {
    let mounted = true;

    const refresh = async () => {
      if (inFlight.current) return;

      inFlight.current = true;
      controller.current = new AbortController();
      try {
        const nextStatus = await obtenerEstadoNeo4j({ signal: controller.current.signal });
        if (mounted) setState(toStatusState(nextStatus));
      } catch (error) {
        if (mounted && error?.name !== "AbortError") setState("disconnected");
      } finally {
        inFlight.current = false;
      }
    };

    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLLING_INTERVAL_MS);

    return () => {
      mounted = false;
      window.clearInterval(timer);
      controller.current?.abort();
    };
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={accessibleLabel}
      title={`Neo4j: ${status.label}`}
      className="inline-flex items-center gap-1.5 rounded-xl border border-line px-2.5 py-2 text-xs font-bold text-muted"
    >
      <span aria-hidden="true" className={`size-2 rounded-full ${status.className}`} />
      <span className="hidden sm:inline">Neo4j</span>
      <span className="sr-only">{accessibleLabel}</span>
    </div>
  );
}
