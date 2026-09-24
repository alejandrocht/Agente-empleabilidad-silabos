"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  ChevronDown,
  Database,
  LoaderCircle,
  RefreshCw,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  iniciarNormalizadorSilabos,
  iniciarNormalizadorSilabosCactus,
  listarEjecucionesNormalizador,
  obtenerEjecucionNormalizador,
  registrarCambioHitlNormalizador,
} from "../api/normalizador";
import HistorialEjecucionesPanel from "./HistorialEjecucionesPanel";

const ESTADOS_TERMINALES = new Set([
  "normalizado",
  "normalizado_con_advertencias",
  "no_publicado",
  "rechazado",
  "error",
  "cancelado",
  "limpiado",
  "limpiado_con_advertencias",
]);

const ESTADOS_RECONOCIDOS = new Set([
  "recibido",
  "extrayendo",
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

function fechaEjecucion(ejecucion) {
  const fecha = new Date(
    ejecucion?.actualizada_en || ejecucion?.creada_en || "",
  ).getTime();
  return Number.isFinite(fecha) ? fecha : null;
}

function ultimaEjecucionActiva(ejecuciones) {
  return (
    ejecuciones
      .filter(
        (ejecucion) => ejecucion?.id_ejecucion && esEjecucionActiva(ejecucion),
      )
      .sort((a, b) => {
        const fechaA = fechaEjecucion(a);
        const fechaB = fechaEjecucion(b);
        if (fechaA === null && fechaB === null) return 0;
        if (fechaA === null) return 1;
        if (fechaB === null) return -1;
        return fechaB - fechaA;
      })[0] || null
  );
}

const CARRERAS_ULIMA = [
  "Administración",
  "Arquitectura",
  "Comunicación",
  "Contabilidad y Finanzas",
  "Derecho",
  "Economía",
  "Ingeniería Ambiental",
  "Ingeniería Civil",
  "Ingeniería Industrial",
  "Ingeniería de Sistemas",
  "Ingeniería Mecatrónica",
  "Marketing",
  "Negocios Internacionales",
  "Psicología",
];

const PERIODOS_SILABOS = [
  "2026-1",
  "2026-2",
  "2027-1",
  "2027-2",
  "2028-1",
  "2028-2",
  "2029-1",
  "2029-2",
  "2030-1",
];

const MENSAJE_ERROR_HITL =
  "No se pudo registrar el cambio del control HITL. Intenta nuevamente.";

export default function NormalizadorPanel() {
  const router = useRouter();
  const inputRef = useRef(null);
  const restauracionRef = useRef(0);
  const [archivo, setArchivo] = useState(null);
  const [fuenteSilabos, setFuenteSilabos] = useState("cactus");
  const [hitl, setHitl] = useState(1);
  const [carrera, setCarrera] = useState("");
  const [periodo, setPeriodo] = useState("");
  const [usuario, setUsuario] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [ejecucion, setEjecucion] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [recuperando, setRecuperando] = useState(true);
  const [errorRed, setErrorRed] = useState("");
  const [errorHitl, setErrorHitl] = useState("");

  const consultar = useCallback(async (id, puedeAplicar = () => true) => {
    const datos = await obtenerEjecucionNormalizador(id);
    if (puedeAplicar()) setEjecucion(datos);
    return datos;
  }, []);

  useEffect(() => {
    let desmontado = false;
    const version = restauracionRef.current;
    const puedeAplicar = () =>
      !desmontado && version === restauracionRef.current;

    async function restaurarEjecucionActiva() {
      try {
        const historial = await listarEjecucionesNormalizador(20);
        if (!puedeAplicar()) return;
        const activa = ultimaEjecucionActiva(
          Array.isArray(historial?.ejecuciones) ? historial.ejecuciones : [],
        );
        if (activa) await consultar(activa.id_ejecucion, puedeAplicar);
      } catch (error) {
        if (puedeAplicar()) {
          setErrorRed(
            error.message || "No se pudo recuperar la ejecución activa.",
          );
        }
      } finally {
        if (puedeAplicar()) setRecuperando(false);
      }
    }

    restaurarEjecucionActiva();
    return () => {
      desmontado = true;
    };
  }, [consultar]);

  useEffect(() => {
    if (!ejecucion?.id_ejecucion || !esEjecucionActiva(ejecucion))
      return undefined;
    const timer = window.setInterval(() => {
      consultar(ejecucion.id_ejecucion).catch((error) =>
        setErrorRed(error.message || "No se pudo actualizar la ejecución."),
      );
    }, 900);
    return () => window.clearInterval(timer);
  }, [consultar, ejecucion]);

  const cambiarHitl = () => {
    const siguiente = hitl === 1 ? 0 : 1;
    setHitl(siguiente);
    setErrorHitl("");
    Promise.resolve(registrarCambioHitlNormalizador(siguiente)).catch(() =>
      setErrorHitl(MENSAJE_ERROR_HITL),
    );
  };

  const iniciar = async (event) => {
    event.preventDefault();
    if (controlesBloqueados) return;
    if (fuenteSilabos === "manual" && !archivo) return;
    restauracionRef.current += 1;
    setRecuperando(false);
    setCargando(true);
    setErrorRed("");
    setErrorHitl("");
    try {
      if (!carrera.trim() || !periodo.trim()) {
        setErrorRed("Para procesar sílabos debes indicar carrera y periodo.");
        return;
      }
      if (
        fuenteSilabos === "cactus" &&
        (!usuario.trim() || !contrasena)
      ) {
        setErrorRed(
          "Para extraer desde Cactus debes indicar usuario y contraseña de ULima.",
        );
        return;
      }
      const datos =
        fuenteSilabos === "cactus"
          ? await iniciarNormalizadorSilabosCactus(
              carrera.trim(),
              periodo.trim(),
              usuario.trim(),
              contrasena,
              hitl,
            )
          : await iniciarNormalizadorSilabos(
              archivo,
              carrera.trim(),
              periodo.trim(),
              hitl,
            );
      if (fuenteSilabos === "cactus") setContrasena("");
      setEjecucion(datos);
      router.push(`/${encodeURIComponent(datos.id_ejecucion)}`);
    } catch (error) {
      setErrorRed(error.message || "No se pudo iniciar la ejecución.");
    } finally {
      setCargando(false);
    }
  };

  const seleccionarArchivo = (event) => {
    const siguiente = event.target.files?.[0] || null;
    setArchivo(siguiente);
    if (siguiente) setFuenteSilabos("manual");
    setErrorRed("");
  };

  const resetear = () => {
    setArchivo(null);
    setErrorRed("");
    setErrorHitl("");
    setFuenteSilabos("cactus");
    setUsuario("");
    setContrasena("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const ejecucionActiva = Boolean(ejecucion && esEjecucionActiva(ejecucion));
  const controlesBloqueados = recuperando || cargando || ejecucionActiva;
  const fuenteLista =
    fuenteSilabos === "cactus"
      ? Boolean(
          carrera.trim() && periodo.trim() && usuario.trim() && contrasena,
        )
      : Boolean(archivo && carrera.trim() && periodo.trim());

  return (
    <main className="h-[100dvh] w-full overflow-y-auto overscroll-contain bg-fondo text-ink">
      <header className="sticky top-0 z-20 border-b border-line bg-paper/95 backdrop-blur-xl">
        <div className="mx-auto flex h-[4.5rem] max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link
            href="/"
            aria-disabled={ejecucionActiva}
            className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-1 py-2 text-sm font-bold text-ink transition hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40 ${ejecucionActiva ? "pointer-events-none opacity-45" : ""}`}
          >
            <span aria-hidden="true">←</span>
            <span>Volver al agente</span>
          </Link>
          <span className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted sm:text-[11px]">
            Normalizador
          </span>
        </div>
      </header>

      <div className="min-h-[calc(100dvh-4.5rem)]">
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 lg:py-6">
          <section className="flex flex-col justify-between gap-4 border-b border-line pb-5 sm:flex-row sm:items-end">
            <div>
              <p className="font-body text-[11px] font-bold uppercase tracking-[0.19em] text-ulima">
                CIAR / data workbench
              </p>
              <h1 className="mt-2 font-editorial text-4xl font-bold leading-none tracking-[-0.035em] text-ink sm:text-4xl">
                Normalizador de data
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted sm:text-base">
                Elige una fuente para iniciar la normalización o consulta el
                historial de ejecuciones.
              </p>
            </div>
            {ejecucionActiva ? (
              <p className="flex items-center gap-2 text-xs font-bold text-ulima">
                <LoaderCircle className="animate-girar" size={14} />
                Ejecución activa
              </p>
            ) : null}
          </section>

          <section className="mt-5 rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5">
            <div>
              <p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">
                01 / entrada
              </p>
              <h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">
                Paquete curricular
              </h2>
              <p className="mt-1 text-sm leading-5 text-muted">
                Valida y limpia la estructura de tus sílabos.
              </p>
            </div>

            <form onSubmit={iniciar}>
              <section
                className="mt-4 rounded-xl border border-line bg-fondo p-3.5"
                aria-label="Control HITL técnico"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-extrabold text-ink">
                      {hitl === 1
                        ? "Revisión técnica manual"
                        : "Aprobación técnica automática"}
                    </p>
                    <p className="mt-1 max-w-3xl text-xs leading-5 text-muted">
                      Esta opción se aplicará a la próxima ejecución. El modo de
                      la ejecución activa se consulta en su inspección.
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-label="HITL técnico"
                    aria-checked={hitl === 1}
                    disabled={controlesBloqueados}
                    onClick={cambiarHitl}
                    className={`relative inline-flex h-11 min-h-11 w-20 shrink-0 cursor-pointer items-center rounded-full border px-1 transition focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-50 ${hitl === 1 ? "border-ulima bg-ulima hover:bg-ulima/90" : "border-line bg-ash hover:border-ulima/60"}`}
                  >
                    <span
                      aria-hidden="true"
                      className={`grid h-9 w-9 place-items-center rounded-full bg-white shadow-sm transition-transform ${hitl === 1 ? "translate-x-9" : "translate-x-0"}`}
                    />
                  </button>
                </div>
              </section>

              {errorHitl ? (
                <p role="alert" className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm font-semibold leading-5 text-amber-900">
                  {errorHitl}
                </p>
              ) : null}

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="text-sm font-bold text-ink">
                  Carrera
                  <span className="relative mt-2 block">
                    <select
                      aria-label="Carrera"
                      disabled={controlesBloqueados}
                      value={carrera}
                      onChange={(event) => setCarrera(event.target.value)}
                      className="w-full appearance-none rounded-xl border border-line bg-paper px-3 py-2.5 pr-10 text-sm font-normal outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20 disabled:cursor-not-allowed disabled:bg-ash disabled:text-muted"
                    >
                      <option value="">Selecciona una carrera</option>
                      {CARRERAS_ULIMA.map((opcion) => (
                        <option key={opcion} value={opcion}>
                          {opcion}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" size={16} aria-hidden="true" />
                  </span>
                </label>
                <label className="text-sm font-bold text-ink">
                  Periodo
                  <span className="relative mt-2 block">
                    <select
                      aria-label="Periodo"
                      disabled={controlesBloqueados}
                      value={periodo}
                      onChange={(event) => setPeriodo(event.target.value)}
                      className="w-full appearance-none rounded-xl border border-line bg-paper px-3 py-2.5 pr-10 text-sm font-normal outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20 disabled:cursor-not-allowed disabled:bg-ash disabled:text-muted"
                    >
                      <option value="">Selecciona un ciclo</option>
                      {PERIODOS_SILABOS.map((opcion) => (
                        <option key={opcion} value={opcion}>
                          {opcion}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" size={16} aria-hidden="true" />
                  </span>
                </label>
              </div>

              <div className="mt-4 rounded-xl border border-line bg-fondo p-3.5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-extrabold text-ink">
                      Origen de los sílabos
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted">
                      Elige extracción automática desde Cactus o carga un paquete existente.
                    </p>
                  </div>
                  <span className="rounded-full bg-paper px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
                    Fuente curricular
                  </span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2" role="group" aria-label="Origen de los sílabos">
                  <button
                    type="button"
                    aria-pressed={fuenteSilabos === "cactus"}
                    disabled={controlesBloqueados}
                    onClick={() => {
                      setFuenteSilabos("cactus");
                      setArchivo(null);
                      if (inputRef.current) inputRef.current.value = "";
                    }}
                    className={`rounded-lg border px-3 py-2 text-left text-xs font-extrabold transition focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-50 ${fuenteSilabos === "cactus" ? "border-ulima bg-[#FFF5F1] text-ulima" : "border-line bg-paper text-muted hover:border-ulima/50"}`}
                  >
                    Extraer desde Cactus
                    <span className="mt-0.5 block text-[11px] font-normal leading-4 text-muted">Navegación y descarga automática</span>
                  </button>
                  <button
                    type="button"
                    aria-pressed={fuenteSilabos === "manual"}
                    disabled={controlesBloqueados}
                    onClick={() => setFuenteSilabos("manual")}
                    className={`rounded-lg border px-3 py-2 text-left text-xs font-extrabold transition focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-50 ${fuenteSilabos === "manual" ? "border-ulima bg-[#FFF5F1] text-ulima" : "border-line bg-paper text-muted hover:border-ulima/50"}`}
                  >
                    Cargar archivo manual
                    <span className="mt-0.5 block text-[11px] font-normal leading-4 text-muted">ZIP, DOCX o PDF ya descargado</span>
                  </button>
                </div>
                {fuenteSilabos === "cactus" ? (
                  <div className="mt-3 border-t border-line pt-3">
                    <p className="text-xs leading-5 text-muted">
                      Tus credenciales solo se usan durante esta ejecución y no se guardan en el manifest.
                    </p>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <label className="text-sm font-bold text-ink">
                        Usuario ULima
                        <input aria-label="Usuario ULima" type="text" autoComplete="username" disabled={controlesBloqueados} value={usuario} onChange={(event) => setUsuario(event.target.value)} className="mt-2 w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm font-normal outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20 disabled:cursor-not-allowed disabled:bg-ash disabled:text-muted" />
                      </label>
                      <label className="text-sm font-bold text-ink">
                        Contraseña ULima
                        <input aria-label="Contraseña ULima" type="password" autoComplete="current-password" disabled={controlesBloqueados} value={contrasena} onChange={(event) => setContrasena(event.target.value)} className="mt-2 w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-sm font-normal outline-none transition focus:border-ulima focus:ring-2 focus:ring-ulima/20 disabled:cursor-not-allowed disabled:bg-ash disabled:text-muted" />
                      </label>
                    </div>
                  </div>
                ) : null}
              </div>

              <label className={`mt-4 flex min-h-36 flex-col items-center justify-center rounded-xl border border-dashed border-ulima/45 bg-[#FFF9F7] px-5 text-center transition focus-within:ring-2 focus-within:ring-ulima/30 ${controlesBloqueados ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-ulima hover:bg-[#FFF5F1]"}`}>
                <span className="grid h-11 w-11 place-items-center rounded-full bg-white text-ulima shadow-sm"><Upload size={21} /></span>
                <span className="mt-3 max-w-full truncate text-sm font-extrabold">
                  {archivo ? archivo.name : fuenteSilabos === "cactus" ? "Cargar un paquete manual (opcional)" : "Seleccionar ZIP, DOCX o PDF"}
                </span>
                <span className="mt-1 text-xs leading-5 text-muted">
                  {fuenteSilabos === "cactus" ? "Si eliges un archivo, cambiaremos al modo manual." : "Puedes cargar un archivo o un paquete de sílabos."}
                </span>
                <input ref={inputRef} disabled={controlesBloqueados} type="file" accept=".zip,.docx,.pdf,application/zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only" onChange={seleccionarArchivo} />
              </label>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button type="submit" disabled={!fuenteLista || controlesBloqueados} className="inline-flex items-center gap-2 rounded-xl bg-ulima px-4 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:-translate-y-px focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none">
                  {cargando ? <LoaderCircle className="animate-girar" size={16} /> : <Database size={16} />}
                  {fuenteSilabos === "cactus" ? "Extraer y normalizar sílabos" : "Iniciar limpieza curricular"}
                </button>
                {archivo ? (
                  <button type="button" onClick={resetear} disabled={controlesBloqueados} className="inline-flex items-center gap-2 rounded-xl border border-line bg-paper px-4 py-2.5 text-sm font-bold text-muted transition hover:border-ink hover:text-ink disabled:cursor-not-allowed disabled:opacity-45">
                    <RefreshCw size={15} /> Nueva fuente
                  </button>
                ) : null}
              </div>
              {errorRed ? <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-semibold leading-5 text-red-700">{errorRed}</p> : null}
            </form>
          </section>

          {ejecucionActiva ? (
            <section className="mt-4 rounded-xl border border-ulima/20 bg-[#FFF9F7] px-4 py-3" role="status" aria-label="Ejecución activa">
              <p className="text-sm font-bold text-ink">Hay una normalización en curso.</p>
              <Link href={`/${encodeURIComponent(ejecucion.id_ejecucion)}`} className="mt-1 inline-flex text-sm font-bold text-ulima underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-ulima/40">
                Abrir inspección de ejecución
              </Link>
            </section>
          ) : null}

          <HistorialEjecucionesPanel />
        </div>
      </div>
    </main>
  );
}
