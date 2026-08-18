"use client";

import { AlertTriangle, Check, Database, LoaderCircle, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  importarEnNeo4j,
  listarImportacionesNeo4j,
  revertirImportacionNeo4j,
  validarImportacionNeo4j,
} from "../api/neo4j";

const ESTADOS_REVERSIBLES = new Set(["completada"]);

function numero(valor) {
  return new Intl.NumberFormat("es-PE").format(Number(valor || 0));
}

function resumenDe(preview) {
  const resumen = preview?.resumen || {};
  return [
    ["Competencias nuevas", resumen.nuevas_competencias],
    ["Habilidades nuevas", resumen.nuevas_habilidades],
    ["Herramientas nuevas", resumen.nuevas_herramientas],
    ["Coberturas nuevas", resumen.nuevas_coberturas],
    ["Sin cambios", resumen.sin_cambios],
  ];
}

function ultimaImportacionReversible(importaciones) {
  return importaciones.find((importacion) => ESTADOS_REVERSIBLES.has(importacion.estado)) || null;
}

export default function Neo4jImportPanel({ idEjecucion }) {
  const [preview, setPreview] = useState(null);
  const [importaciones, setImportaciones] = useState([]);
  const [dialogo, setDialogo] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");

  const cargarHistorial = useCallback(async () => {
    try {
      const datos = await listarImportacionesNeo4j();
      setImportaciones(Array.isArray(datos.importaciones) ? datos.importaciones : []);
    } catch (errorHistorial) {
      setError(errorHistorial.message || "No se pudo consultar el historial de importaciones.");
    }
  }, []);

  useEffect(() => {
    cargarHistorial();
  }, [cargarHistorial]);

  useEffect(() => {
    if (!dialogo) return undefined;
    const cerrarConEscape = (event) => {
      if (event.key === "Escape" && !cargando) setDialogo(null);
    };
    window.addEventListener("keydown", cerrarConEscape);
    return () => window.removeEventListener("keydown", cerrarConEscape);
  }, [cargando, dialogo]);

  const ultimaReversible = useMemo(
    () => ultimaImportacionReversible(importaciones),
    [importaciones],
  );

  const validar = async () => {
    setCargando(true);
    setError("");
    setMensaje("");
    try {
      const datos = await validarImportacionNeo4j(idEjecucion);
      setPreview(datos);
      setDialogo("confirmar");
    } catch (errorValidacion) {
      setError(errorValidacion.message || "No se pudo validar la publicación en Neo4j.");
    } finally {
      setCargando(false);
    }
  };

  const confirmarImportacion = async () => {
    if (!preview?.puede_importar) return;
    setCargando(true);
    setError("");
    try {
      const datos = await importarEnNeo4j(
        preview.id_ejecucion,
        preview.fingerprint,
        true,
      );
      setDialogo(null);
      setPreview(null);
      setMensaje(`${datos.mensaje || "La data fue agregada a Neo4j."} ID: ${datos.id_importacion}`);
      await cargarHistorial();
    } catch (errorImportacion) {
      setError(errorImportacion.message || "No se pudo agregar la data a Neo4j.");
    } finally {
      setCargando(false);
    }
  };

  const confirmarReversion = async () => {
    if (!ultimaReversible) return;
    setCargando(true);
    setError("");
    try {
      const datos = await revertirImportacionNeo4j(ultimaReversible.id_importacion, true);
      setDialogo(null);
      setMensaje(datos.mensaje || "La importación fue revertida.");
      await cargarHistorial();
    } catch (errorReversion) {
      setError(errorReversion.message || "No se pudo revertir la importación.");
    } finally {
      setCargando(false);
    }
  };

  const cerrarDialogo = () => {
    if (!cargando) setDialogo(null);
  };

  return (
    <>
      <section className="mt-5 border-t border-line pt-5" aria-labelledby="neo4j-import-title">
        <div className="rounded-2xl border border-[#E6D3CB] bg-[#FFF8F5] p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ulima/10 text-ulima">
                <Database size={20} aria-hidden="true" />
              </span>
              <div>
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-ulima">
                  05 / publicación
                </p>
                <h3 id="neo4j-import-title" className="mt-1 text-lg font-extrabold tracking-[-0.02em]">
                  Subir catálogos a Neo4j
                </h3>
              </div>
            </div>
            <span className="rounded-full border border-[#E6D3CB] bg-paper px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted">
              Revisión manual
            </span>
          </div>

          <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">
            Recomendamos revisar los datos antes de subirlos a la base de datos. Primero validaremos
            el formato, las referencias y si cada fila es realmente nueva.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={validar}
              disabled={cargando}
              className="inline-flex items-center gap-2 rounded-xl bg-ulima px-4 py-3 text-sm font-extrabold text-white transition hover:bg-[#8f1e16] focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {cargando ? <LoaderCircle className="animate-spin" size={17} aria-hidden="true" /> : <Database size={17} aria-hidden="true" />}
              Subir datos a Neo4j
            </button>
            {ultimaReversible ? (
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setDialogo("revertir");
                }}
                disabled={cargando}
                className="inline-flex items-center gap-2 rounded-xl border border-line bg-paper px-4 py-3 text-sm font-extrabold text-ink transition hover:border-ulima hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <RotateCcw size={17} aria-hidden="true" />
                Revertir última importación
              </button>
            ) : null}
          </div>

          {mensaje ? (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-3 text-sm leading-5 text-emerald-800" role="status">
              <Check className="mt-0.5 shrink-0" size={17} aria-hidden="true" />
              <p>{mensaje}</p>
            </div>
          ) : null}
          {error ? (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm leading-5 text-red-700" role="alert">
              <AlertTriangle className="mt-0.5 shrink-0" size={17} aria-hidden="true" />
              <p>{error}</p>
            </div>
          ) : null}
          {ultimaReversible ? (
            <p className="mt-4 font-mono text-[10px] leading-5 text-muted">
              Última importación reversible: {ultimaReversible.id_importacion}
            </p>
          ) : null}
        </div>
      </section>

      {dialogo ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/45 p-4 backdrop-blur-sm"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) cerrarDialogo();
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="neo4j-dialog-title"
            aria-describedby="neo4j-dialog-description"
            className="max-h-[90dvh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-paper p-5 shadow-2xl sm:p-6"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-ulima">
                  {dialogo === "revertir" ? "Reversión inmediata" : "Validación previa"}
                </p>
                <h2 id="neo4j-dialog-title" className="mt-2 text-xl font-extrabold tracking-[-0.025em]">
                  {dialogo === "revertir" ? "¿Revertir la importación reciente?" : "Revisar datos antes de publicar"}
                </h2>
              </div>
              <button
                type="button"
                onClick={cerrarDialogo}
                disabled={cargando}
                aria-label="Cerrar ventana"
                className="rounded-lg p-1.5 text-muted transition hover:bg-ash hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:opacity-50"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            {dialogo === "revertir" ? (
              <>
                <p id="neo4j-dialog-description" className="mt-4 text-sm leading-6 text-muted">
                  Solo se eliminarán los nodos y relaciones creados por esta importación. Los datos
                  existentes o conectados por otros procesos se conservarán.
                </p>
                <div className="mt-5 flex justify-end gap-2">
                  <button type="button" onClick={cerrarDialogo} disabled={cargando} className="rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-ink hover:bg-ash focus:outline-none focus:ring-2 focus:ring-ulima/30">
                    Cancelar
                  </button>
                  <button type="button" onClick={confirmarReversion} disabled={cargando} className="inline-flex items-center gap-2 rounded-xl bg-ulima px-4 py-2.5 text-sm font-extrabold text-white hover:bg-[#8f1e16] focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:opacity-60">
                    {cargando ? <LoaderCircle className="animate-spin" size={16} aria-hidden="true" /> : <RotateCcw size={16} aria-hidden="true" />}
                    Revertir importación
                  </button>
                </div>
              </>
            ) : (
              <>
                <p id="neo4j-dialog-description" className="mt-4 text-sm leading-6 text-muted">
                  {preview?.mensaje || "La data fue revisada."} Recomendamos revisar los datos antes de subirlos a la base de datos.
                </p>
                <div className="mt-4 grid gap-2 sm:grid-cols-3">
                  {resumenDe(preview).map(([etiqueta, valor]) => (
                    <div key={etiqueta} className="rounded-xl bg-ash px-3.5 py-3">
                      <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-muted">{etiqueta}</p>
                      <p className="mt-1 text-xl font-extrabold">{numero(valor)}</p>
                    </div>
                  ))}
                </div>
                {preview?.archivos?.length ? (
                  <div className="mt-4 rounded-xl border border-line bg-fondo p-3.5">
                    <p className="font-bold">Detalle de archivos</p>
                    <ul className="mt-2 space-y-1.5 text-xs leading-5 text-muted">
                      {preview.archivos.map((archivo) => (
                        <li key={archivo.archivo} className="flex flex-wrap justify-between gap-2">
                          <span>{archivo.archivo}</span>
                          <span className="font-mono">{numero(archivo.nuevas)} nuevas · {numero(archivo.sin_cambios)} sin cambios</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {preview?.errores?.length || preview?.conflictos?.length ? (
                  <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-sm text-amber-900">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 shrink-0" size={17} aria-hidden="true" />
                      <div>
                        <p className="font-bold">No se puede publicar todavía</p>
                        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5">
                          {[...(preview.errores || []), ...(preview.conflictos || [])].slice(0, 8).map((hallazgo, indice) => (
                            <li key={`${hallazgo.codigo || "hallazgo"}-${indice}`}>{hallazgo.mensaje}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                ) : null}
                <p className="mt-5 text-sm font-bold text-ink">
                  {preview?.puede_importar
                    ? "¿Estás seguro de que deseas agregar estos datos a Neo4j?"
                    : "Corrige o revisa los hallazgos antes de intentar la publicación."}
                </p>
                <div className="mt-5 flex justify-end gap-2">
                  <button type="button" onClick={cerrarDialogo} disabled={cargando} className="rounded-xl border border-line px-4 py-2.5 text-sm font-bold text-ink hover:bg-ash focus:outline-none focus:ring-2 focus:ring-ulima/30">
                    Cancelar
                  </button>
                  <button type="button" onClick={confirmarImportacion} disabled={!preview?.puede_importar || cargando} className="inline-flex items-center gap-2 rounded-xl bg-ulima px-4 py-2.5 text-sm font-extrabold text-white hover:bg-[#8f1e16] focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-45">
                    {cargando ? <LoaderCircle className="animate-spin" size={16} aria-hidden="true" /> : <Database size={16} aria-hidden="true" />}
                    Agregar a Neo4j
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      ) : null}
    </>
  );
}
