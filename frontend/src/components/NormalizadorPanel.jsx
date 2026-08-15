"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  CircleDashed,
  Clock3,
  Database,
  BookOpen,
  Download,
  FileSpreadsheet,
  LoaderCircle,
  RefreshCw,
  Upload,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  iniciarNormalizadorEmpleabilidad,
  iniciarNormalizadorSilabos,
  obtenerCuarentenaNormalizador,
  obtenerEjecucionNormalizador,
  obtenerErroresNormalizador,
  obtenerUrlOutputNormalizador,
} from "../api/normalizador";

const ESTADOS_TERMINALES = new Set([
  "normalizado",
  "normalizado_con_advertencias",
  "no_publicado",
  "rechazado",
  "error",
]);

const ESTADOS_TERMINALES_SILABOS = new Set([
  "limpiado",
  "limpiado_con_advertencias",
  "no_publicado",
  "rechazado",
  "error",
]);

function esEstadoTerminal(ejecucion) {
  if (!ejecucion) return false;
  return (ejecucion.tipo === "silabos" ? ESTADOS_TERMINALES_SILABOS : ESTADOS_TERMINALES).has(ejecucion.estado);
}

const ETIQUETAS_ESTADO = {
  recibido: "Recibido",
  validando: "Validando estructura",
  validado: "Estructura validada",
  validado_con_advertencias: "Validada con advertencias",
  limpiando: "Limpiando datos",
  limpiado: "CSV curriculares listos",
  limpiado_con_advertencias: "CSV con advertencias",
  normalizando: "Extrayendo CHH",
  normalizado: "Listo para publicar",
  normalizado_con_advertencias: "Listo con advertencias",
  no_publicado: "No publicado",
  rechazado: "Entrada rechazada",
  error: "Error de ejecución",
};

const PASOS_POR_TIPO = {
  empleabilidad: [
    { id: "entrada", label: "Entrada" },
    { id: "limpieza", label: "Limpieza" },
    { id: "chh", label: "CHH" },
    { id: "gate", label: "Gate" },
  ],
  silabos: [
    { id: "entrada", label: "Carga" },
    { id: "validacion", label: "Validación" },
    { id: "limpieza", label: "Limpieza" },
    { id: "resultado", label: "CSV curriculares" },
  ],
};

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

const INACTIVIDAD_RECIENTE_MS = 5 * 60 * 1000;

const ETIQUETAS_SEVERIDAD = {
  error: "Error",
  warning: "Advertencia",
  info: "Información",
};

function tipoFlujo(ejecucion, modo) {
  return ejecucion?.tipo === "silabos" || modo === "silabos" ? "silabos" : "empleabilidad";
}

function pasosPara(ejecucion, modo) {
  return PASOS_POR_TIPO[tipoFlujo(ejecucion, modo)];
}

function pasoActivo(estado, paso, tipo) {
  if (tipo === "silabos") {
    if (["recibido", "validando", "rechazado"].includes(estado)) return paso === "entrada";
    if (["validado", "validado_con_advertencias"].includes(estado)) return paso === "validacion";
    if (estado === "limpiando") return paso === "limpieza";
    return false;
  }
  if (["recibido", "validando", "rechazado"].includes(estado)) return paso === "entrada";
  if (["validado", "validado_con_advertencias", "limpiando"].includes(estado)) {
    return paso === "limpieza";
  }
  if (["limpiado", "limpiado_con_advertencias", "normalizando"].includes(estado)) {
    return paso === "chh";
  }
  return false;
}

function pasoCompletado(estado, indice, tipo) {
  const orden = tipo === "silabos"
    ? {
        recibido: 0,
        validando: 0,
        validado: 1,
        validado_con_advertencias: 1,
        limpiando: 2,
        limpiado: 4,
        limpiado_con_advertencias: 4,
        no_publicado: 4,
        rechazado: 0,
        error: 0,
      }
    : {
        recibido: 0,
        validando: 0,
        validado: 1,
        validado_con_advertencias: 1,
        limpiando: 1,
        limpiado: 2,
        limpiado_con_advertencias: 2,
        normalizando: 2,
        normalizado: 4,
        normalizado_con_advertencias: 4,
        no_publicado: 4,
        rechazado: 0,
        error: 0,
      };
  return (orden[estado] ?? 0) > indice;
}

function progresoFlujo(estado, tipo) {
  const pasos = PASOS_POR_TIPO[tipo];
  const completados = pasos.reduce(
    (total, _, indice) => total + (pasoCompletado(estado, indice, tipo) ? 1 : 0),
    0,
  );
  return Math.min(100, Math.round((completados / (pasos.length - 1)) * 100));
}

function detalleHallazgo(hallazgo) {
  const ubicacion = [hallazgo.hoja, hallazgo.fila ? `fila ${hallazgo.fila}` : ""]
    .filter(Boolean)
    .join(" · ");
  return [hallazgo.mensaje, ubicacion, hallazgo.detalle].filter(Boolean).join(" — ");
}

function nombreOutput(ruta) {
  return String(ruta || "").split("/").at(-1) || "Archivo de salida";
}

function fechaLegible(fecha) {
  const valor = new Date(fecha);
  if (Number.isNaN(valor.getTime())) return null;
  return new Intl.DateTimeFormat("es-PE", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short",
  }).format(valor);
}

function minutosSinActividad(fecha, ahora = Date.now()) {
  const actualizacion = new Date(fecha).getTime();
  if (!Number.isFinite(actualizacion) || ahora - actualizacion < INACTIVIDAD_RECIENTE_MS) return null;
  return Math.max(1, Math.floor((ahora - actualizacion) / 60000));
}

function estadoActividad({ completada, activa, requiereAtencion = false }) {
  if (requiereAtencion) return "atencion";
  if (completada) return "completada";
  if (activa) return "activa";
  return "pendiente";
}

function actividadPorEtapas(ejecucion) {
  if (!ejecucion) return [];
  const esSilabo = ejecucion.tipo === "silabos";
  const estado = ejecucion.estado;
  const validacion = esSilabo ? ejecucion.validacion_silabos : ejecucion.validacion;
  const limpieza = esSilabo ? ejecucion.limpieza_silabos : ejecucion.limpieza;
  const tieneSalida = Array.isArray(ejecucion.outputs) && ejecucion.outputs.length > 0;
  const fallida = ["rechazado", "error", "no_publicado"].includes(estado);
  const validacionCompletada = Boolean(validacion) || ["validado", "validado_con_advertencias", "limpiando", "limpiado", "limpiado_con_advertencias", "normalizando", "normalizado", "normalizado_con_advertencias", "no_publicado"].includes(estado);
  const limpiezaCompletada = Boolean(limpieza) || ["limpiado", "limpiado_con_advertencias", "normalizando", "normalizado", "normalizado_con_advertencias", "no_publicado"].includes(estado);
  const normalizacionCompletada = Boolean(ejecucion.normalizacion) || ["normalizado", "normalizado_con_advertencias", "no_publicado"].includes(estado);

  const etapas = [
    {
      id: "recepcion",
      titulo: "Recepción",
      detalle: ejecucion.archivo ? `Fuente recibida: ${ejecucion.archivo}` : "Fuente recibida.",
      estado: estadoActividad({ completada: true, requiereAtencion: estado === "rechazado" }),
    },
    {
      id: "validacion",
      titulo: "Validación",
      detalle: validacion?.valida === false
        ? "La estructura fue rechazada durante la validación."
        : validacionCompletada
          ? "La estructura fue validada."
          : estado === "validando"
            ? "Validando la estructura de la fuente."
            : "Pendiente de validación.",
      estado: estadoActividad({
        completada: validacionCompletada && validacion?.valida !== false,
        activa: estado === "validando",
        requiereAtencion: validacion?.valida === false || estado === "rechazado",
      }),
    },
    {
      id: "limpieza",
      titulo: "Limpieza",
      detalle: limpiezaCompletada
        ? esSilabo
          ? `${limpieza?.registros ?? 0} sílabos extraídos para el resultado curricular.`
          : "Staging de la fuente preparado."
        : estado === "limpiando"
          ? "Limpiando y estructurando los datos."
          : "Pendiente de limpieza.",
      estado: estadoActividad({
        completada: limpiezaCompletada,
        activa: estado === "limpiando",
        requiereAtencion: fallida && !limpiezaCompletada,
      }),
    },
  ];

  if (!esSilabo) {
    etapas.push({
      id: "normalizacion",
      titulo: "Normalización",
      detalle: normalizacionCompletada
        ? ejecucion.normalizacion?.publicable === false
          ? "La normalización terminó con observaciones que impiden publicar."
          : "Relaciones CHH normalizadas."
        : estado === "normalizando"
          ? "Extrayendo y normalizando relaciones CHH."
          : "Pendiente de normalización.",
      estado: estadoActividad({
        completada: normalizacionCompletada && ejecucion.normalizacion?.publicable !== false,
        activa: estado === "normalizando",
        requiereAtencion: ejecucion.normalizacion?.publicable === false || estado === "no_publicado",
      }),
    });
  }

  etapas.push({
    id: "publicacion",
    titulo: esSilabo ? "Publicación curricular" : "Publicación",
    detalle: tieneSalida
      ? `${ejecucion.outputs.length} archivo${ejecucion.outputs.length === 1 ? "" : "s"} registrado${ejecucion.outputs.length === 1 ? "" : "s"} como salida.`
      : estado === "no_publicado"
        ? "No se publicaron salidas hasta corregir los hallazgos."
        : "Pendiente de publicar las salidas.",
    estado: estadoActividad({
      completada: tieneSalida,
      requiereAtencion: estado === "no_publicado" || (esEstadoTerminal(ejecucion) && !tieneSalida),
    }),
  });

  return etapas;
}

function hallazgosActividad(ejecucion) {
  const fuentes = [
    ...(ejecucion?.hallazgos || []),
    ...(ejecucion?.validacion_silabos?.hallazgos || []),
    ...(ejecucion?.limpieza_silabos?.hallazgos || []),
    ...(ejecucion?.normalizacion?.hallazgos || []),
  ];
  const vistos = new Set();
  return fuentes.filter((hallazgo) => {
    const clave = [hallazgo.codigo, hallazgo.severidad, hallazgo.mensaje, hallazgo.hoja, hallazgo.fila].join("|");
    if (vistos.has(clave)) return false;
    vistos.add(clave);
    return true;
  });
}

const ETIQUETAS_FASE_LLM = {
  preparando: "Preparando…",
  extrayendo: "Extrayendo sílabos",
  analista: "Analista LLM",
  analista_residual: "Analista residual",
  inspector: "Inspector LLM",
  inspector_residual: "Inspector residual",
  finalizando: "Finalizando reporte",
  completado: "Completado",
  error: "Con observaciones",
};

const ETIQUETAS_REPORTE_LLM = {
  pendiente: "pendiente",
  disponible: "disponible",
  error: "no disponible",
};

function numeroProgreso(valor) {
  return Number.isFinite(Number(valor)) ? Number(valor) : 0;
}

function progresoLLM(ejecucion) {
  const progresoRegistrado = ejecucion?.progreso_llm;
  const progreso = progresoRegistrado && typeof progresoRegistrado === "object"
    ? progresoRegistrado
    : ejecucion?.tipo === "silabos" && ejecucion?.estado === "limpiando"
      ? {
          fase: "preparando",
          chunks_completados: 0,
          chunks_totales: 0,
          logros_detectados: 0,
          logros_procesados: 0,
          logros_totales: 0,
          silabos_detectados: 0,
          silabos_procesados: 0,
          silabos_totales: ejecucion?.validacion_silabos?.archivos?.length || 0,
          decisiones_cacheadas: 0,
          reintentos: 0,
          mensaje: "Preparando la extracción de sílabos. El seguimiento aparecerá aquí enseguida.",
          eventos: [],
          reporte_final: "pendiente",
        }
      : null;
  if (!progreso) return null;
  const chunksCompletados = numeroProgreso(progreso.chunks_completados);
  const chunksTotales = numeroProgreso(progreso.chunks_totales);
  const eventos = Array.isArray(progreso.eventos)
    ? progreso.eventos
        .filter((evento) => evento && typeof evento === "object")
        .slice(-100)
    : [];
  return {
    ...progreso,
    chunksCompletados,
    chunksTotales,
    logrosDetectados: numeroProgreso(progreso.logros_detectados),
    logrosProcesados: numeroProgreso(progreso.logros_procesados),
    logrosTotales: numeroProgreso(progreso.logros_totales),
    silabosDetectados: numeroProgreso(
      progreso.silabos_detectados ?? ejecucion?.validacion_silabos?.archivos?.length,
    ),
    silabosProcesados: numeroProgreso(progreso.silabos_procesados),
    silabosTotales: numeroProgreso(progreso.silabos_totales),
    decisionesCacheadas: numeroProgreso(progreso.decisiones_cacheadas),
    reintentos: numeroProgreso(progreso.reintentos),
    eventos,
    mensaje: String(progreso.mensaje || "Preparando el siguiente hito de limpieza."),
    porcentaje: chunksTotales ? Math.min(100, Math.round((chunksCompletados / chunksTotales) * 100)) : 0,
  };
}

function metricas(ejecucion, cuarentena) {
  if (ejecucion?.tipo === "silabos") {
    return [
      { label: "Sílabos extraídos", value: ejecucion.limpieza_silabos?.registros ?? "—" },
      { label: "Relaciones curriculares", value: ejecucion.limpieza_silabos?.relaciones ?? "—" },
      { label: "En cuarentena", value: cuarentena?.total ?? "—" },
    ];
  }
  const normalizacion = ejecucion?.normalizacion;
  const limpieza = ejecucion?.limpieza;
  return [
    {
      label: "Registros procesados",
      value: normalizacion
        ? Object.values(normalizacion.registros_procesados || {}).reduce((a, b) => a + b, 0)
        : limpieza
          ? Object.values(limpieza.registros_por_universo || {}).reduce((a, b) => a + b, 0)
          : "—",
    },
    { label: "Relaciones CHH", value: normalizacion?.relaciones ?? "—" },
    { label: "En cuarentena", value: normalizacion?.cuarentena ?? "—" },
  ];
}

export default function NormalizadorPanel() {
  const inputRef = useRef(null);
  const [modo, setModo] = useState("empleabilidad");
  const [archivo, setArchivo] = useState(null);
  const [carrera, setCarrera] = useState("");
  const [periodo, setPeriodo] = useState("");
  const [ejecucion, setEjecucion] = useState(null);
  const [cuarentena, setCuarentena] = useState(null);
  const [errores, setErrores] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [errorRed, setErrorRed] = useState("");

  const consultar = useCallback(async (id) => {
    const datos = await obtenerEjecucionNormalizador(id);
    setEjecucion(datos);
    if (esEstadoTerminal(datos)) {
      const [detalleErrores, detalleCuarentena] = await Promise.all([
        obtenerErroresNormalizador(id),
        obtenerCuarentenaNormalizador(id, { limite: 8 }),
      ]);
      setErrores(detalleErrores.hallazgos || []);
      setCuarentena(detalleCuarentena);
    }
    return datos;
  }, []);

  useEffect(() => {
    if (!ejecucion?.id_ejecucion || esEstadoTerminal(ejecucion)) return undefined;
    const timer = window.setInterval(() => {
      consultar(ejecucion.id_ejecucion).catch((error) => setErrorRed(error.message));
    }, 900);
    return () => window.clearInterval(timer);
  }, [consultar, ejecucion]);

  const iniciar = async () => {
    if (!archivo) return;
    setCargando(true);
    setErrorRed("");
    setEjecucion(null);
    setCuarentena(null);
    setErrores([]);
    try {
      if (modo === "silabos" && (!carrera.trim() || !periodo.trim())) {
        setErrorRed("Para limpiar sílabos debes indicar carrera y periodo.");
        return;
      }
      const datos = modo === "silabos"
        ? await iniciarNormalizadorSilabos(archivo, carrera.trim(), periodo.trim())
        : await iniciarNormalizadorEmpleabilidad(archivo);
      setEjecucion(datos);
      await consultar(datos.id_ejecucion);
    } catch (error) {
      setErrorRed(error.message || "No se pudo iniciar la ejecución.");
    } finally {
      setCargando(false);
    }
  };

  const seleccionarArchivo = (event) => {
    const siguiente = event.target.files?.[0] || null;
    setArchivo(siguiente);
    setErrorRed("");
  };

  const resetear = () => {
    setArchivo(null);
    setEjecucion(null);
    setCuarentena(null);
    setErrores([]);
    setErrorRed("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const estado = ejecucion?.estado || "recibido";
  const esCurricular = ejecucion?.tipo === "silabos" || modo === "silabos";
  const esFinal = esEstadoTerminal(ejecucion);
  const flujo = tipoFlujo(ejecucion, modo);
  const pasos = pasosPara(ejecucion, modo);
  const controlesBloqueados = cargando || Boolean(ejecucion);
  const ejecucionActiva = cargando || Boolean(ejecucion && !esFinal);
  const resultadoListo = esCurricular
    ? ["limpiado", "limpiado_con_advertencias"].includes(estado)
      && ejecucion?.validacion_silabos?.valida === true
    : ejecucion?.normalizacion?.publicable === true;
  const tituloEstado = ETIQUETAS_ESTADO[estado] || "Preparando ejecución";
  const resumenMetricas = useMemo(() => metricas(ejecucion, cuarentena), [ejecucion, cuarentena]);
  const progresoLimpiezaLLM = useMemo(() => progresoLLM(ejecucion), [ejecucion]);
  const registroActividad = useMemo(() => actividadPorEtapas(ejecucion), [ejecucion]);
  const hallazgosRegistro = useMemo(() => hallazgosActividad(ejecucion), [ejecucion]);
  const minutosInactivo = !esFinal ? minutosSinActividad(ejecucion?.actualizada_en) : null;
  const ultimaActualizacion = fechaLegible(ejecucion?.actualizada_en);
  const IconoFuente = esCurricular ? BookOpen : FileSpreadsheet;
  const pasoEnCurso = pasos.find((paso) => pasoActivo(estado, paso.id, flujo));
  const progreso = progresoFlujo(estado, flujo);
  const detalleSeguimiento = !ejecucion && !cargando
    ? "Selecciona una fuente y presiona el botón de inicio para comenzar."
    : esFinal
      ? (esCurricular ? "La estructura quedó registrada y ya puedes revisar sus hallazgos." : "La ejecución terminó y el gate dejó su resultado registrado.")
      : `Etapa actual: ${pasoEnCurso?.label || "preparación"}. Los controles permanecen bloqueados hasta terminar.`;

  return (
    <main className="h-[100dvh] w-full overflow-y-auto overscroll-contain bg-fondo text-ink">
      <header className="sticky top-0 z-20 border-b border-line bg-paper/95 backdrop-blur-xl">
        <div className="mx-auto flex h-[4.5rem] max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-4">
            <Link href="/" aria-disabled={ejecucionActiva} className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-1 py-2 text-sm font-bold text-ink transition hover:text-ulima focus:outline-none focus:ring-2 focus:ring-ulima/40 ${ejecucionActiva ? "pointer-events-none opacity-45" : ""}`}>
              <ArrowLeft size={17} />
              <span className="hidden sm:inline">Volver al agente</span>
              <span className="sm:hidden">Volver</span>
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
          <span className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted sm:text-[11px]">
            Normalizador
          </span>
        </div>
      </header>

      <div className="min-h-[calc(100dvh-4.5rem)]">
        <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 lg:py-6">
          <section className="flex flex-col justify-between gap-4 border-b border-line pb-5 sm:flex-row sm:items-end">
            <div>
              <p className="font-body text-[11px] font-bold uppercase tracking-[0.19em] text-ulima">CIAR / data workbench</p>
              <h1 className="mt-2 font-editorial text-4xl font-bold leading-none tracking-[-0.035em] text-ink sm:text-4xl">Normalizador de data</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted sm:text-base">
                Carga una fuente, sigue su transformación y revisa el resultado antes de publicarlo.
              </p>
            </div>
            <div className="flex items-center gap-2 self-start rounded-full border border-line bg-paper px-3 py-2 text-xs font-bold text-muted sm:self-auto">
              <span className="h-2 w-2 rounded-full bg-ulima" aria-hidden="true" />
              Flujo trazable
            </div>
          </section>

          <section className="mt-5 rounded-2xl border border-line bg-paper p-4 shadow-sm" aria-label="Tipo de fuente">
            <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
              <div>
                <p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">01 / entrada</p>
                <h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">¿Qué vas a normalizar?</h2>
              </div>
              {ejecucionActiva ? (
                <p className="flex items-center gap-2 text-xs font-bold text-ulima">
                  <LoaderCircle className="animate-girar" size={14} />
                  Fuente bloqueada durante la ejecución
                </p>
              ) : null}
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2" role="tablist" aria-label="Selecciona el tipo de fuente">
              <button
                type="button"
                role="tab"
                aria-label="Empleabilidad"
                aria-selected={modo === "empleabilidad"}
                aria-controls="panel-fuente"
                disabled={controlesBloqueados}
                onClick={() => { setModo("empleabilidad"); setArchivo(null); if (inputRef.current) inputRef.current.value = ""; }}
                className={`group flex items-center gap-3 rounded-xl border px-4 py-2.5 text-left transition focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-50 ${modo === "empleabilidad" ? "border-ulima bg-[#FFF5F1]" : "border-line bg-paper hover:border-ulima/50 hover:bg-fondo"}`}
              >
                <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg transition ${modo === "empleabilidad" ? "bg-ulima text-white" : "bg-ash text-muted group-hover:text-ulima"}`}>
                  <FileSpreadsheet size={19} />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-extrabold text-ink">Empleabilidad</span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted">Fuente XLSX y relaciones CHH</span>
                </span>
                <span className={`ml-auto h-2.5 w-2.5 shrink-0 rounded-full border transition ${modo === "empleabilidad" ? "border-ulima bg-ulima" : "border-line bg-paper"}`} aria-hidden="true" />
              </button>
              <button
                type="button"
                role="tab"
                aria-label="Sílabos"
                aria-selected={modo === "silabos"}
                aria-controls="panel-fuente"
                disabled={controlesBloqueados}
                onClick={() => { setModo("silabos"); setArchivo(null); if (inputRef.current) inputRef.current.value = ""; }}
                className={`group flex items-center gap-3 rounded-xl border px-4 py-2.5 text-left transition focus:outline-none focus:ring-2 focus:ring-ulima/30 disabled:cursor-not-allowed disabled:opacity-50 ${modo === "silabos" ? "border-ulima bg-[#FFF5F1]" : "border-line bg-paper hover:border-ulima/50 hover:bg-fondo"}`}
              >
                <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg transition ${modo === "silabos" ? "bg-ulima text-white" : "bg-ash text-muted group-hover:text-ulima"}`}>
                  <BookOpen size={19} />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-extrabold text-ink">Sílabos</span>
                  <span className="mt-0.5 block text-xs leading-5 text-muted">DOCX, PDF o ZIP curricular</span>
                </span>
                <span className={`ml-auto h-2.5 w-2.5 shrink-0 rounded-full border transition ${modo === "silabos" ? "border-ulima bg-ulima" : "border-line bg-paper"}`} aria-hidden="true" />
              </button>
            </div>
          </section>

          <section id="panel-fuente" className="mt-4 grid gap-4 lg:grid-cols-[.88fr_1.12fr]" role="tabpanel">
            <section className="rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5" aria-label="Carga de fuente">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">Carga de fuente</p>
                  <h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">{esCurricular ? "Paquete curricular" : "Archivo operativo"}</h2>
                  <p className="mt-1 text-sm leading-5 text-muted">{esCurricular ? "Valida y limpia la estructura de tus sílabos." : "Valida, limpia y normaliza tus relaciones de empleabilidad."}</p>
                </div>
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-[#FFF5F1] text-ulima">
                  <IconoFuente size={21} />
                </span>
              </div>

              {modo === "silabos" ? (
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
                        {CARRERAS_ULIMA.map((opcion) => <option key={opcion} value={opcion}>{opcion}</option>)}
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
                        {PERIODOS_SILABOS.map((opcion) => <option key={opcion} value={opcion}>{opcion}</option>)}
                      </select>
                      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" size={16} aria-hidden="true" />
                    </span>
                  </label>
                </div>
              ) : null}

              <label className={`mt-4 flex min-h-36 flex-col items-center justify-center rounded-xl border border-dashed border-ulima/45 bg-[#FFF9F7] px-5 text-center transition focus-within:ring-2 focus-within:ring-ulima/30 ${controlesBloqueados ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-ulima hover:bg-[#FFF5F1]"}`}>
                <span className="grid h-11 w-11 place-items-center rounded-full bg-white text-ulima shadow-sm">
                  <Upload size={21} />
                </span>
                <span className="mt-3 max-w-full truncate text-sm font-extrabold">{archivo ? archivo.name : esCurricular ? "Seleccionar ZIP, DOCX o PDF" : "Seleccionar archivo XLSX"}</span>
                <span className="mt-1 text-xs leading-5 text-muted">{esCurricular ? "Puedes cargar un archivo o un paquete de sílabos." : "Los años de las hojas pueden variar."}</span>
                <input disabled={controlesBloqueados} ref={inputRef} type="file" accept={esCurricular ? ".zip,.docx,.pdf,application/zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" : ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"} className="sr-only" onChange={seleccionarArchivo} />
              </label>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button type="button" onClick={iniciar} disabled={!archivo || controlesBloqueados || (modo === "silabos" && (!carrera.trim() || !periodo.trim()))} className="inline-flex items-center gap-2 rounded-xl bg-ulima px-4 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:-translate-y-px hover:shadow-[0_8px_20px_rgba(255,81,23,0.24)] focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none">
                  {cargando ? <LoaderCircle className="animate-girar" size={16} /> : <Database size={16} />}
                  {esCurricular ? "Iniciar limpieza curricular" : "Iniciar normalización"}
                </button>
                {(archivo || ejecucion) ? (
                  <button type="button" onClick={resetear} disabled={ejecucionActiva} className="inline-flex items-center gap-2 rounded-xl border border-line bg-paper px-4 py-2.5 text-sm font-bold text-muted transition hover:border-ink hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/40 disabled:cursor-not-allowed disabled:opacity-45">
                    <RefreshCw size={15} />
                    Nueva fuente
                  </button>
                ) : null}
              </div>
              {errorRed ? <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-semibold leading-5 text-red-700">{errorRed}</p> : null}
            </section>

            <section className="rounded-2xl border border-line bg-paper p-4 shadow-sm sm:p-5" aria-label="Seguimiento del flujo">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="font-body text-[10px] font-bold uppercase tracking-[0.18em] text-muted">02 / seguimiento</p>
                  <h2 className="mt-1.5 text-xl font-extrabold tracking-[-0.025em]">Progreso de la normalización</h2>
                </div>
                <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border ${ejecucionActiva ? "border-ulima/30 bg-[#FFF5F1] text-ulima" : "border-line bg-fondo text-muted"}`}>
                  {ejecucionActiva ? <LoaderCircle className="animate-girar" size={20} /> : <CircleDashed size={20} />}
                </span>
              </div>

              <div className="mt-5" role="progressbar" aria-label="Progreso del flujo" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progreso} aria-valuetext={`${progreso}% completado`}>
                <div className="mb-2.5 flex items-center justify-between font-body text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
                  <span>{esCurricular ? "Flujo curricular" : "Flujo de empleabilidad"}</span>
                  <span className="text-ulima">{progreso}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-ash">
                  <div className="h-full rounded-full bg-ulima transition-[width] duration-700 ease-out" style={{ width: `${progreso}%` }} />
                </div>
              </div>

              <div className="mt-5 grid grid-cols-4" aria-label="Etapas del flujo">
                {pasos.map((paso, indice) => {
                  const completado = pasoCompletado(estado, indice, flujo);
                  const activo = pasoActivo(estado, paso.id, flujo);
                  const siguienteCompletado = indice < pasos.length - 1 && pasoCompletado(estado, indice + 1, flujo);
                  return (
                    <div key={paso.id} className="relative flex min-w-0 flex-col items-center text-center">
                      {indice > 0 ? <span className={`absolute left-0 right-1/2 top-4 h-px transition-colors duration-500 ${completado ? "bg-ulima" : "bg-line"}`} aria-hidden="true" /> : null}
                      {indice < pasos.length - 1 ? <span className={`absolute left-1/2 right-0 top-4 h-px transition-colors duration-500 ${siguienteCompletado ? "bg-ulima" : "bg-line"}`} aria-hidden="true" /> : null}
                      <span className={`relative z-10 grid h-8 w-8 place-items-center rounded-full border-2 bg-paper transition-all duration-500 ${completado ? "border-ulima bg-ulima text-white" : activo ? "border-ulima text-ulima shadow-[0_0_0_5px_rgba(255,81,23,0.10)]" : "border-line text-muted"}`}>
                        {completado ? <Check size={14} strokeWidth={3} /> : <span className="font-body text-[10px] font-extrabold">{String(indice + 1).padStart(2, "0")}</span>}
                      </span>
                      <p className={`mt-2 w-full truncate px-1 font-body text-[10px] font-bold uppercase tracking-[0.08em] ${activo || completado ? "text-ink" : "text-muted"}`}>{paso.label}</p>
                      <p className={`mt-1 w-full truncate px-1 font-body text-[9px] uppercase tracking-[0.08em] ${completado ? "text-ulima" : activo ? "text-ink" : "text-muted/70"}`}>
                        {completado ? "listo" : activo ? "en curso" : "pendiente"}
                      </p>
                    </div>
                  );
                })}
              </div>

              <div className="mt-5 flex items-start gap-3 rounded-xl border border-line bg-fondo px-3.5 py-3">
                <div className={`mt-0.5 shrink-0 ${ejecucionActiva ? "text-ulima" : esFinal ? "text-emerald-600" : "text-muted"}`}>
                  {ejecucionActiva ? <LoaderCircle className="animate-girar" size={17} /> : esFinal ? <Check size={17} /> : <CircleDashed size={17} />}
                </div>
                <div className="min-w-0">
                  <p className="font-body text-[10px] font-bold uppercase tracking-[0.14em] text-muted">
                    {ejecucionActiva ? "Proceso en curso" : esFinal ? "Proceso registrado" : "Esperando fuente"}
                  </p>
                  <p className="mt-1 text-sm leading-5 text-muted">{detalleSeguimiento}</p>
                </div>
              </div>

              <div className="mt-5 border-t border-line pt-4">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <div>
                    <p className="font-body text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Estado actual</p>
                    <p className="mt-1.5 text-2xl font-extrabold tracking-[-0.035em]">{tituloEstado}</p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 font-body text-[10px] font-bold uppercase tracking-[0.08em] ${esFinal ? resultadoListo ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700" : ejecucionActiva ? "bg-[#FFF5F1] text-ulima" : "bg-ash text-muted"}`}>
                    {esFinal ? resultadoListo ? "Revisado" : "Requiere atención" : ejecucionActiva ? "En curso" : "Sin iniciar"}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted">
                  {ejecucion ? `Ejecución ${ejecucion.id_ejecucion} · ${ejecucion.archivo}` : "La ejecución aparecerá aquí cuando cargues una fuente."}
                </p>
              </div>
            </section>
          </section>

          {ejecucion ? (
            <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-label="Registro de actividad">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">03 / actividad</p>
                  <h2 className="mt-2 text-xl font-extrabold tracking-[-0.025em]">Registro de actividad</h2>
                  <p className="mt-1 text-sm leading-5 text-muted">Actualizado desde el estado registrado por la ejecución.</p>
                </div>
                <div className="flex items-center gap-2 rounded-full border border-line bg-fondo px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-muted">
                  <Clock3 size={13} aria-hidden="true" />
                  {ultimaActualizacion ? `Actualizado ${ultimaActualizacion}` : "Sin marca de actualización"}
                </div>
              </div>

              {minutosInactivo ? (
                <div role="status" className="mt-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-amber-900">
                  <Clock3 className="mt-0.5 shrink-0" size={17} aria-hidden="true" />
                  <div>
                    <p className="text-sm font-extrabold">Sin actividad reciente</p>
                    <p className="mt-0.5 text-sm leading-5">Esta ejecución sigue sin estado terminal, pero no se actualiza desde hace {minutosInactivo} min. Espera una nueva actualización o revisa el proceso antes de asumir que continúa activo.</p>
                  </div>
                </div>
              ) : null}

              {progresoLimpiezaLLM ? (
                <section
                  className="mt-5 rounded-xl border border-ulima/20 bg-[#FFF5F1] p-4"
                  aria-label="Progreso de limpieza LLM"
                  aria-live="polite"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-ulima">Limpieza LLM en tiempo real</p>
                      <h3 className="mt-1 text-base font-extrabold text-ink">{ETIQUETAS_FASE_LLM[progresoLimpiezaLLM.fase] || "Procesando"}</h3>
                      <p className="mt-1 text-xs leading-5 text-muted">
                        {progresoLimpiezaLLM.chunksTotales
                          ? `${progresoLimpiezaLLM.chunksCompletados}/${progresoLimpiezaLLM.chunksTotales} chunks de la fase actual.`
                          : progresoLimpiezaLLM.mensaje}
                      </p>
                    </div>
                    <span className="rounded-full border border-ulima/20 bg-paper px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.08em] text-ulima">
                      Reporte final: {ETIQUETAS_REPORTE_LLM[progresoLimpiezaLLM.reporte_final] || "pendiente"}
                    </span>
                  </div>

                  <div
                    className="mt-3 h-2 overflow-hidden rounded-full bg-ulima/10"
                    role="progressbar"
                    aria-label="Avance de chunks LLM"
                    aria-valuemin={0}
                    aria-valuemax={progresoLimpiezaLLM.chunksTotales}
                    aria-valuenow={progresoLimpiezaLLM.chunksCompletados}
                    aria-valuetext={`${progresoLimpiezaLLM.chunksCompletados} de ${progresoLimpiezaLLM.chunksTotales} chunks`}
                  >
                    <div className="h-full rounded-full bg-ulima transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${progresoLimpiezaLLM.porcentaje}%` }} />
                  </div>

                  <dl className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-6">
                    <div className="rounded-lg border border-line bg-paper px-3 py-2">
                      <dt className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">Logros detectados</dt>
                      <dd className="mt-1 font-extrabold text-ink">{progresoLimpiezaLLM.logrosDetectados}</dd>
                    </div>
                    <div className="rounded-lg border border-line bg-paper px-3 py-2">
                      <dt className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">Logros procesados por LLM</dt>
                      <dd className="mt-1 font-extrabold text-ink">{progresoLimpiezaLLM.logrosProcesados} / {progresoLimpiezaLLM.logrosTotales}</dd>
                    </div>
                    <div className="rounded-lg border border-line bg-paper px-3 py-2">
                      <dt className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">Sílabos detectados</dt>
                      <dd className="mt-1 font-extrabold text-ink">{progresoLimpiezaLLM.silabosDetectados} / {progresoLimpiezaLLM.silabosTotales}</dd>
                    </div>
                    <div className="rounded-lg border border-line bg-paper px-3 py-2">
                      <dt className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">Sílabos procesados por LLM</dt>
                      <dd className="mt-1 font-extrabold text-ink">{progresoLimpiezaLLM.silabosProcesados} / {progresoLimpiezaLLM.silabosTotales}</dd>
                    </div>
                    <div className="rounded-lg border border-line bg-paper px-3 py-2">
                      <dt className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">Decisiones cacheadas</dt>
                      <dd className="mt-1 font-extrabold text-ink">{progresoLimpiezaLLM.decisionesCacheadas}</dd>
                    </div>
                    <div className="rounded-lg border border-line bg-paper px-3 py-2">
                      <dt className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-muted">Reintentos</dt>
                      <dd className="mt-1 font-extrabold text-ink">{progresoLimpiezaLLM.reintentos}</dd>
                    </div>
                  </dl>

                  {progresoLimpiezaLLM.ultimo_chunk ? (
                    <p className="mt-3 border-t border-ulima/15 pt-3 text-xs leading-5 text-muted">
                      Último chunk de {ETIQUETAS_FASE_LLM[progresoLimpiezaLLM.ultimo_chunk.fase] || "LLM"}: {numeroProgreso(progresoLimpiezaLLM.ultimo_chunk.logros)} logros y {numeroProgreso(progresoLimpiezaLLM.ultimo_chunk.silabos)} sílabo{numeroProgreso(progresoLimpiezaLLM.ultimo_chunk.silabos) === 1 ? "" : "s"}.
                    </p>
                  ) : null}

                  <div className="mt-4 border-t border-ulima/15 pt-3">
                    <div className="flex items-baseline justify-between gap-3">
                      <h4 className="text-sm font-extrabold text-ink">Línea de tiempo</h4>
                      <span className="font-mono text-[10px] font-bold text-muted">{progresoLimpiezaLLM.eventos.length} hitos</span>
                    </div>
                    <ol className="mt-2 max-h-60 space-y-2 overflow-y-auto pr-1" aria-label="Hitos de limpieza LLM" aria-live="polite">
                      {progresoLimpiezaLLM.eventos.length ? progresoLimpiezaLLM.eventos.map((evento, indice) => (
                        <li key={`${evento.secuencia || "hito"}-${indice}`} className="flex gap-2 rounded-lg border border-ulima/10 bg-paper px-2.5 py-2 text-xs leading-5 text-muted">
                          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ulima" aria-hidden="true" />
                          <div className="min-w-0">
                            <p className="font-semibold text-ink">{evento.mensaje || "Hito de limpieza actualizado."}</p>
                            <p>{numeroProgreso(evento.chunks_completados)}/{numeroProgreso(evento.chunks_totales)} chunks · logros detectados {numeroProgreso(evento.logros_detectados)} · sílabos detectados {numeroProgreso(evento.silabos_detectados)} · sílabos LLM {numeroProgreso(evento.silabos_procesados)} · caché {numeroProgreso(evento.decisiones_cacheadas)} · reintentos {numeroProgreso(evento.reintentos)}</p>
                          </div>
                        </li>
                      )) : (
                        <li className="rounded-lg border border-dashed border-ulima/20 bg-paper px-2.5 py-2 text-xs leading-5 text-muted">{progresoLimpiezaLLM.mensaje}</li>
                      )}
                    </ol>
                  </div>
                </section>
              ) : null}

              <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,.9fr)_minmax(0,1.1fr)]">
                <ol className="space-y-2" aria-label="Etapas registradas">
                  {registroActividad.map((evento) => {
                    const estilos = {
                      completada: "border-emerald-200 bg-emerald-50 text-emerald-700",
                      activa: "border-ulima/30 bg-[#FFF5F1] text-ulima",
                      atencion: "border-red-200 bg-red-50 text-red-700",
                      pendiente: "border-line bg-fondo text-muted",
                    }[evento.estado];
                    const etiqueta = {
                      completada: "listo",
                      activa: "en curso",
                      atencion: "requiere atención",
                      pendiente: "pendiente",
                    }[evento.estado];
                    return (
                      <li key={evento.id} className="flex items-start gap-3 rounded-xl border border-line bg-fondo px-3 py-2.5">
                        <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[10px] ${estilos}`} aria-hidden="true">
                          {evento.estado === "completada" ? <Check size={12} strokeWidth={3} /> : evento.estado === "activa" ? <LoaderCircle className="animate-girar" size={12} /> : evento.estado === "atencion" ? <AlertTriangle size={12} /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
                        </span>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
                            <p className="text-sm font-extrabold text-ink">{evento.titulo}</p>
                            <span className={`font-mono text-[9px] font-bold uppercase tracking-[0.08em] ${evento.estado === "pendiente" ? "text-muted" : estilos.split(" ").at(-1)}`}>{etiqueta}</span>
                          </div>
                          <p className="mt-0.5 text-xs leading-5 text-muted">{evento.detalle}</p>
                        </div>
                      </li>
                    );
                  })}
                </ol>

                <div className="min-w-0 rounded-xl border border-line bg-fondo p-3.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <h3 className="font-bold">Hallazgos y avisos</h3>
                      <p className="mt-1 text-xs leading-5 text-muted">Las observaciones aparecen conforme el manifest las registra.</p>
                    </div>
                    <span className="font-mono text-[10px] font-bold text-muted">{hallazgosRegistro.length}</span>
                  </div>
                  {hallazgosRegistro.length ? (
                    <ul className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1" aria-label="Hallazgos de la ejecución">
                      {hallazgosRegistro.slice(0, 12).map((hallazgo, indice) => {
                        const severidad = String(hallazgo.severidad || "info").toLowerCase();
                        const estilos = {
                          error: "border-red-200 bg-red-50 text-red-700",
                          warning: "border-amber-200 bg-amber-50 text-amber-800",
                          info: "border-sky-200 bg-sky-50 text-sky-700",
                        }[severidad] || "border-line bg-paper text-muted";
                        return (
                          <li key={`${hallazgo.codigo}-${indice}`} className="rounded-lg border border-line bg-paper px-3 py-2.5 text-sm">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`rounded-full border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.08em] ${estilos}`}>{ETIQUETAS_SEVERIDAD[severidad] || "Aviso"}</span>
                              <span className="font-mono text-[10px] font-bold text-ink">{hallazgo.codigo || "SIN_CODIGO"}</span>
                            </div>
                            <p className="mt-1.5 leading-5 text-muted">{detalleHallazgo(hallazgo) || "Sin detalle adicional."}</p>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="mt-4 rounded-lg border border-dashed border-line px-3 py-3 text-sm leading-5 text-muted">Aún no hay hallazgos registrados para esta ejecución.</p>
                  )}
                </div>
              </div>
            </section>
          ) : null}

          {ejecucion ? (
            <section className="mt-5 rounded-2xl border border-line bg-paper p-5 shadow-panel sm:p-6" aria-live="polite">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">04 / resultado</p>
                  <h2 className="mt-2 text-xl font-extrabold tracking-[-0.025em]">{resultadoListo ? (esCurricular ? "CSV curriculares listos" : "Paquete listo para la siguiente etapa") : esCurricular ? "La fuente curricular requiere corrección" : "La fuente no se publica todavía"}</h2>
                </div>
                {resultadoListo ? <Check className="text-emerald-600" size={25} /> : <XCircle className="text-red-600" size={25} />}
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                {resumenMetricas.map((metrica) => (
                  <div key={metrica.label} className="rounded-xl bg-ash px-4 py-3">
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.13em] text-muted">{metrica.label}</p>
                    <p className="mt-1 text-2xl font-extrabold tracking-[-0.04em]">{metrica.value}</p>
                  </div>
                ))}
              </div>

              {Array.isArray(ejecucion.outputs) && ejecucion.outputs.length ? (
                <div className="mt-5 border-t border-line pt-5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <h3 className="font-bold">Archivos disponibles</h3>
                      <p className="mt-1 text-sm leading-5 text-muted">Descarga los resultados registrados por esta ejecución.</p>
                    </div>
                    <span className="font-mono text-xs text-muted">{ejecucion.outputs.length} archivo{ejecucion.outputs.length === 1 ? "" : "s"}</span>
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {ejecucion.outputs.map((output) => (
                      <a
                        key={output.archivo}
                        href={obtenerUrlOutputNormalizador(ejecucion.id_ejecucion, output.archivo)}
                        download
                        className="group flex items-center justify-between gap-3 rounded-xl border border-line bg-fondo px-3.5 py-3 transition hover:border-ulima hover:bg-[#FFF5F1] focus:outline-none focus:ring-2 focus:ring-ulima/30"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-extrabold text-ink">{nombreOutput(output.archivo)}</span>
                          <span className="mt-1 block text-xs text-muted">
                            {output.tipo || "archivo"}{output.registros !== undefined ? ` · ${output.registros} registros` : ""}
                          </span>
                        </span>
                        <Download className="shrink-0 text-ulima transition group-hover:translate-y-0.5" size={17} aria-hidden="true" />
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}

              {!resultadoListo && esFinal ? (
                <div className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="mt-0.5 shrink-0 text-red-600" size={18} />
                    <div className="min-w-0">
                      <p className="font-bold text-red-800">{esCurricular ? "Corrige estos hallazgos antes de continuar" : "Corrige estos hallazgos antes de publicar"}</p>
                      <div className="mt-2 space-y-2 text-sm leading-5 text-red-700">
                        {(errores.length ? errores : ejecucion.hallazgos || []).slice(0, 12).map((hallazgo, indice) => (
                          <p key={`${hallazgo.codigo}-${indice}`}><span className="font-mono text-xs font-bold">{hallazgo.codigo}</span> · {detalleHallazgo(hallazgo)}</p>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ) : null}

              {cuarentena?.total ? (
                <div className="mt-5 border-t border-line pt-5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="font-bold">Filas en cuarentena</h3>
                    <span className="font-mono text-xs text-muted">Mostrando {cuarentena.filas.length} de {cuarentena.total}</span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {cuarentena.filas.map((fila, indice) => (
                      <div key={`${fila.id_registro}-${indice}`} className="rounded-xl border border-line bg-ash/60 px-3 py-2.5 text-sm">
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-ulima">{fila.codigo} · {fila.origen?.hoja || "origen no disponible"} · fila {fila.origen?.fila || "—"}</p>
                        <p className="mt-1 text-muted">{fila.detalle || fila.mensaje}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {resultadoListo && ejecucion.catalogo_chh ? (
                <p className="mt-5 border-t border-line pt-4 font-mono text-[11px] leading-5 text-muted">
                  {esCurricular ? "Contexto CHH disponible para la siguiente extracción" : `Catálogo ${ejecucion.catalogo_chh.version} · ${ejecucion.catalogo_chh.competencias} competencias · ${ejecucion.catalogo_chh.habilidades} habilidades · ${ejecucion.catalogo_chh.herramientas} herramientas`}
                </p>
              ) : null}
            </section>
          ) : null}
        </div>
      </div>
    </main>
  );
}
