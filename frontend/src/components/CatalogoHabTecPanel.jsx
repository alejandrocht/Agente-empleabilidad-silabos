"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  LoaderCircle,
  Upload,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  cargarCatalogoHabTec,
  obtenerCatalogoHabTec,
  vectorizarCatalogoHabTec,
} from "../api/normalizador";

const ESTADOS_ACTIVOS = new Set(["vectorizando"]);

function etiquetaEstado(estado) {
  return {
    listo_para_vectorizar: "Validado y listo para vectorizar",
    vectorizando: "Vectorizando y sincronizando Neo4j",
    vectorizado: "Índice local y catálogo Neo4j listos",
    rechazado: "Requiere corrección",
    error: "La vectorización no terminó",
  }[estado] || "Preparando catálogo";
}

export default function CatalogoHabTecPanel() {
  const inputRef = useRef(null);
  const [archivo, setArchivo] = useState(null);
  const [catalogo, setCatalogo] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!catalogo?.id_catalogo || !ESTADOS_ACTIVOS.has(catalogo.estado)) return undefined;
    const temporizador = window.setInterval(async () => {
      try {
        setCatalogo(await obtenerCatalogoHabTec(catalogo.id_catalogo));
      } catch (causa) {
        setError(causa.message || "No se pudo actualizar el estado del catálogo.");
      }
    }, 1200);
    return () => window.clearInterval(temporizador);
  }, [catalogo?.id_catalogo, catalogo?.estado]);

  const subir = async () => {
    if (!archivo || cargando) return;
    setCargando(true);
    setError("");
    try {
      setCatalogo(await cargarCatalogoHabTec(archivo));
    } catch (causa) {
      setError(causa.message || "No se pudo validar el catálogo.");
    } finally {
      setCargando(false);
    }
  };

  const vectorizar = async () => {
    if (!catalogo?.id_catalogo || cargando) return;
    setCargando(true);
    setError("");
    try {
      setCatalogo(await vectorizarCatalogoHabTec(catalogo.id_catalogo));
    } catch (causa) {
      setError(causa.message || "No se pudo iniciar la vectorización.");
    } finally {
      setCargando(false);
    }
  };

  const reiniciar = () => {
    setArchivo(null);
    setCatalogo(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const activo = Boolean(catalogo && ESTADOS_ACTIVOS.has(catalogo.estado));
  const resumen = catalogo?.resumen;

  return (
    <main className="h-[100dvh] overflow-y-auto overscroll-contain bg-fondo text-ink">
      <header className="sticky top-0 z-20 border-b border-line bg-paper/95 backdrop-blur-xl">
        <div className="mx-auto flex h-[4.5rem] max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-4">
            <Link
              href="/normalizador"
              className="inline-flex items-center gap-2 rounded-xl px-1 py-2 text-sm font-bold text-ink transition hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40"
            >
              <ArrowLeft size={17} />
              <span>Volver al normalizador</span>
            </Link>
            <span className="hidden h-6 w-px bg-line sm:block" aria-hidden="true" />
            <div className="hidden items-center gap-2.5 sm:flex">
              <img src="/logo-ulima.png" alt="Universidad de Lima" className="h-8 w-8 object-contain" />
              <div className="leading-none">
                <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-ink">CIAR</p>
                <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.12em] text-muted">Data workbench</p>
              </div>
            </div>
          </div>
          <span className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted sm:text-[11px]">Catálogo HAB_TEC</span>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 lg:py-6">
        <section className="flex flex-col justify-between gap-4 border-b border-line pb-5 sm:flex-row sm:items-end">
          <div>
            <p className="font-body text-[11px] font-bold uppercase tracking-[0.19em] text-ulima">CIAR / catálogo semántico</p>
            <h1 className="mt-2 font-editorial text-4xl font-bold leading-none tracking-[-0.035em] text-ink">Índice de HAB_TEC</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted sm:text-base">
              Carga el catálogo oficial, valida IDs inmutables, crea un índice local y sincroniza el catálogo estructurado en Neo4j.
            </p>
          </div>
          <div className="flex items-center gap-2 self-start rounded-full border border-line bg-paper px-3 py-2 text-xs font-bold text-muted sm:self-auto">
            <span className="h-2 w-2 rounded-full bg-ulima" aria-hidden="true" />
            Versionado local
          </div>
        </section>

        <section className="mt-5 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5" aria-label="Carga de catálogo HAB_TEC">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
            <div>
              <p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">01 / fuente oficial</p>
              <h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">Sube el Excel del catálogo</h2>
              <p className="mt-1 text-sm leading-6 text-muted">Columnas requeridas: <strong>Carrera</strong>, <strong>id</strong>, <strong>nombre</strong> y <strong>descripcion</strong>.</p>
            </div>
            {catalogo ? <span className="rounded-full bg-ash px-3 py-1.5 text-xs font-bold text-muted">{etiquetaEstado(catalogo.estado)}</span> : null}
          </div>

          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className={`flex min-h-24 flex-1 cursor-pointer items-center gap-3 rounded-xl border border-dashed p-4 transition ${activo ? "cursor-not-allowed border-line bg-ash" : "border-line bg-fondo hover:border-ulima/60"}`}>
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[#FFF5F1] text-ulima"><FileSpreadsheet size={20} /></span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-bold text-ink">{archivo?.name || "Seleccionar Excel (.xlsx)"}</span>
                <span className="mt-1 block text-xs leading-5 text-muted">La carga crea una versión aislada; no reemplaza ningún catálogo activo.</span>
              </span>
              <input
                ref={inputRef}
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                disabled={activo}
                className="sr-only"
                onChange={(event) => {
                  setArchivo(event.target.files?.[0] || null);
                  setCatalogo(null);
                  setError("");
                }}
              />
            </label>
            <button type="button" onClick={subir} disabled={!archivo || activo || cargando} className="inline-flex items-center justify-center gap-2 rounded-xl bg-ulima px-4 py-3 text-sm font-extrabold text-white transition hover:-translate-y-px focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-45">
              {cargando ? <LoaderCircle className="animate-girar" size={16} /> : <Upload size={16} />}
              Validar catálogo
            </button>
            {(archivo || catalogo) && !activo ? <button type="button" onClick={reiniciar} className="rounded-xl border border-line px-4 py-3 text-sm font-bold text-muted transition hover:border-ink hover:text-ink">Nueva carga</button> : null}
          </div>
          {error ? <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-semibold text-red-700"><AlertTriangle className="mt-0.5 shrink-0" size={16} />{error}</p> : null}
        </section>

        {catalogo ? <>
          <section className="mt-5 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5" aria-label="Resumen de validación">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
              <div>
                <p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">02 / validación</p>
                <h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">{etiquetaEstado(catalogo.estado)}</h2>
                <p className="mt-1 text-sm text-muted">Hoja detectada: {catalogo.hoja || "—"} · Archivo: {catalogo.archivo}</p>
              </div>
              {catalogo.estado === "listo_para_vectorizar" ? <button type="button" onClick={vectorizar} disabled={cargando} className="inline-flex items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-extrabold text-white transition hover:bg-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:opacity-45">
                {cargando ? <LoaderCircle className="animate-girar" size={16} /> : <Database size={16} />}
                Vectorizar con Qwen local
              </button> : null}
              {activo ? <span className="inline-flex items-center gap-2 text-sm font-bold text-ulima"><LoaderCircle className="animate-girar" size={16} />Creando vectores y sincronizando catálogo…</span> : null}
              {catalogo.estado === "vectorizado" ? <span className="inline-flex items-center gap-2 text-sm font-bold text-emerald-700"><CheckCircle2 size={17} />Índice local y catálogo Neo4j listos</span> : null}
            </div>
            <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["HAB_TEC válidas", resumen?.habilidades ?? 0],
                ["Errores", resumen?.errores ?? 0],
                ["Advertencias", resumen?.advertencias ?? 0],
                ["Dimensión", resumen?.dimension_embedding ?? "—"],
              ].map(([etiqueta, valor]) => <div key={etiqueta} className="rounded-xl border border-line bg-fondo p-3"><dt className="text-xs font-bold text-muted">{etiqueta}</dt><dd className="mt-1 text-2xl font-extrabold tracking-tight text-ink">{valor}</dd></div>)}
            </dl>
            {(catalogo.hallazgos || []).length ? <div className="mt-5 rounded-xl border border-line bg-fondo p-3" aria-label="Hallazgos de validación">
              <div className="flex items-center justify-between gap-3"><div><p className="text-sm font-extrabold text-ink">Hallazgos de validación</p><p className="mt-0.5 text-xs text-muted">Se muestran los primeros 100 hallazgos. Desplaza esta lista para revisarlos.</p></div><AlertTriangle className="shrink-0 text-amber-600" size={18} /></div>
              <div className="mt-3 max-h-64 space-y-2 overflow-y-auto pr-1">
                {catalogo.hallazgos.map((hallazgo, indice) => <p key={`${hallazgo.codigo}-${indice}`} className={`rounded-lg border px-3 py-2.5 text-sm ${hallazgo.severidad === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-amber-200 bg-amber-50 text-amber-800"}`}><strong>{hallazgo.codigo}</strong>{hallazgo.fila ? ` · Fila ${hallazgo.fila}` : ""}: {hallazgo.mensaje}{hallazgo.detalle ? ` ${hallazgo.detalle}` : ""}</p>)}
              </div>
            </div> : null}
            {resumen?.modelo_embedding ? <p className="mt-4 text-xs font-semibold text-muted">Modelo del índice: {resumen.modelo_embedding}</p> : null}
            {catalogo.error ? <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-semibold text-red-700">{catalogo.error} Verifica Ollama, las credenciales de ingestión y las carreras registradas en Neo4j.</p> : null}
          </section>

          <section className="mt-5 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5" aria-label="Vista previa del catálogo">
            <div className="flex items-center justify-between gap-3"><div><p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">03 / revisión</p><h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">Primeras HAB_TEC</h2></div><span className="text-xs font-bold text-muted">Vista previa de hasta 100 filas</span></div>
            <div className="mt-4 overflow-x-auto rounded-xl border border-line"><table className="min-w-full text-left text-sm"><thead className="bg-fondo text-xs uppercase tracking-wide text-muted"><tr><th className="px-3 py-3">ID</th><th className="px-3 py-3">Nombre</th><th className="px-3 py-3">Carrera</th><th className="px-3 py-3">Descripción</th></tr></thead><tbody className="divide-y divide-line">{(catalogo.preview || []).map((fila) => <tr key={`${fila.id}-${fila.fila}`}><td className="whitespace-nowrap px-3 py-3 font-mono text-xs font-bold text-ulima">{fila.id}</td><td className="px-3 py-3 font-bold text-ink">{fila.nombre}</td><td className="px-3 py-3 text-muted">{fila.carrera}</td><td className="min-w-72 px-3 py-3 text-muted">{fila.descripcion}</td></tr>)}</tbody></table></div>
          </section>
        </> : null}
      </div>
    </main>
  );
}
