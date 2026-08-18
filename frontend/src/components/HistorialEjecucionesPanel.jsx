"use client";

import {
  AlertTriangle,
  Eye,
  History,
  LoaderCircle,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  eliminarEjecucionHistorialNormalizador,
  listarEjecucionesNormalizador,
} from "../api/normalizador";

function fechaLegible(fecha) {
  const valor = new Date(fecha);
  if (Number.isNaN(valor.getTime())) return "Fecha no disponible";
  return new Intl.DateTimeFormat("es-PE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(valor);
}

function textoParametro(ejecucion, clave, fallback) {
  return ejecucion?.parametros?.[clave] || fallback;
}

const ESTADOS_TERMINALES = new Set([
  "limpiado",
  "limpiado_con_advertencias",
  "normalizado",
  "normalizado_con_advertencias",
  "no_publicado",
  "rechazado",
  "error",
  "cancelado",
]);

const ESTADOS_RECONOCIDOS = new Set([
  "recibido",
  "validando",
  "validado",
  "validado_con_advertencias",
  "limpiando",
  "limpiado",
  "limpiado_con_advertencias",
  "normalizando",
  "normalizado",
  "normalizado_con_advertencias",
  "no_publicado",
  "rechazado",
  "error",
  "cancelado",
]);

function esEjecucionActiva(ejecucion) {
  const estado = String(ejecucion?.estado || "").toLowerCase();
  return ESTADOS_RECONOCIDOS.has(estado) && !ESTADOS_TERMINALES.has(estado);
}

export default function HistorialEjecucionesPanel() {
  const [ejecuciones, setEjecuciones] = useState([]);
  const [retencion, setRetencion] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [eliminando, setEliminando] = useState("");
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const datos = await listarEjecucionesNormalizador(20);
      setEjecuciones(Array.isArray(datos.ejecuciones) ? datos.ejecuciones : []);
      setRetencion(datos.retencion || null);
      setError("");
    } catch (err) {
      setError(err.message || "No se pudo cargar el historial.");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const eliminar = async (ejecucion) => {
    if (!window.confirm(`¿Eliminar ${ejecucion.id_ejecucion} del historial? Esta acción no se puede deshacer.`)) return;
    setEliminando(ejecucion.id_ejecucion);
    try {
      await eliminarEjecucionHistorialNormalizador(ejecucion.id_ejecucion);
      await cargar();
    } catch (err) {
      setError(err.message || "No se pudo eliminar la ejecución.");
    } finally {
      setEliminando("");
    }
  };

  return (
    <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-labelledby="historial-ejecuciones-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">05 / historial</p>
          <h2 id="historial-ejecuciones-title" className="mt-2 flex items-center gap-2 text-xl font-extrabold tracking-[-0.025em]">
            <History className="text-ulima" size={21} />
            Historial de ejecuciones
          </h2>
          <p className="mt-1 max-w-2xl text-sm leading-5 text-muted">
            Recomendamos revisar los datos y hallazgos antes de publicar. Se conservan los reportes auditables y se purgan los binarios temporales.
          </p>
        </div>
        <button type="button" onClick={cargar} disabled={cargando} className="inline-flex items-center gap-2 rounded-lg border border-line bg-fondo px-3 py-2 text-xs font-bold text-muted transition hover:border-ink hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-wait disabled:opacity-60">
          {cargando ? <LoaderCircle className="animate-girar" size={14} /> : <History size={14} />}
          Actualizar
        </button>
      </div>

      {retencion ? (
        <p className="mt-4 rounded-xl border border-line bg-fondo px-3.5 py-2.5 text-xs leading-5 text-muted">
          Retención automática: últimas {retencion.max_ejecuciones} ejecuciones terminales o {retencion.dias} días.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm font-semibold leading-5 text-red-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={16} />
          {error}
        </p>
      ) : null}

      {!cargando && !ejecuciones.length && !error ? (
        <p className="mt-4 rounded-xl border border-dashed border-line px-3.5 py-4 text-sm leading-5 text-muted">Todavía no hay ejecuciones guardadas en el historial.</p>
      ) : null}

      {ejecuciones.length ? (
        <div className="mt-4 space-y-2" aria-label="Ejecuciones históricas">
          {ejecuciones.map((ejecucion) => {
            const resumen = ejecucion.resumen || {};
            const carrera = textoParametro(ejecucion, "carrera", ejecucion.tipo === "silabos" ? "Carrera no indicada" : "Empleabilidad");
            const periodo = textoParametro(ejecucion, "periodo", "—");
            const inspeccionBloqueada = esEjecucionActiva(ejecucion);
            return (
              <article key={ejecucion.id_ejecucion} className="flex flex-col gap-3 rounded-xl border border-line bg-fondo px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-sm font-extrabold text-ink">{carrera}</h3>
                    <span className="rounded-full border border-line bg-paper px-2 py-0.5 font-mono text-[10px] font-bold text-muted">{periodo}</span>
                    <span className="rounded-full bg-[#FFF5F1] px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.06em] text-ulima">{ejecucion.estado}</span>
                  </div>
                  <p className="mt-1 truncate text-xs text-muted">{ejecucion.id_ejecucion} · {ejecucion.archivo} · {fechaLegible(ejecucion.actualizada_en || ejecucion.creada_en)}</p>
                  <p className="mt-1 text-xs text-muted">{resumen.advertencias || 0} advertencias · {resumen.errores || 0} errores · {resumen.outputs || 0} salidas</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {inspeccionBloqueada ? (
                    <button
                      type="button"
                      disabled
                      title="Disponible al finalizar la ejecución"
                      aria-label="Inspeccionar — disponible al finalizar"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-2 text-xs font-bold text-muted disabled:cursor-wait disabled:opacity-70"
                    >
                      <LoaderCircle className="animate-girar" size={14} aria-hidden="true" />
                      <span>Inspeccionar</span>
                      <span className="font-semibold">Disponible al finalizar</span>
                    </button>
                  ) : (
                    <a
                      href={`/normalizador/ejecuciones/${encodeURIComponent(ejecucion.id_ejecucion)}/inspeccion`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-paper px-3 py-2 text-xs font-bold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/30"
                    >
                      <Eye size={14} />
                      Inspeccionar
                    </a>
                  )}
                  <button type="button" onClick={() => eliminar(ejecucion)} disabled={eliminando === ejecucion.id_ejecucion} className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-bold text-red-700 transition hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-300 disabled:cursor-wait disabled:opacity-60">
                    {eliminando === ejecucion.id_ejecucion ? <LoaderCircle className="animate-girar" size={14} /> : <Trash2 size={14} />}
                    Eliminar
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
