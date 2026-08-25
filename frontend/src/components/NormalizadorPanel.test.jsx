import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NormalizadorPanel from "./NormalizadorPanel";
import {
  cancelarEjecucionNormalizador,
  iniciarNormalizadorEmpleabilidad,
  iniciarNormalizadorSilabos,
  listarEjecucionesNormalizador,
  decidirPendientesNormalizador,
  obtenerCuarentenaNormalizador,
  obtenerEjecucionNormalizador,
  obtenerErroresNormalizador,
  obtenerPendientesNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  cancelarEjecucionNormalizador: vi.fn(),
  iniciarNormalizadorEmpleabilidad: vi.fn(),
  iniciarNormalizadorSilabos: vi.fn(),
  listarEjecucionesNormalizador: vi.fn(),
  decidirPendientesNormalizador: vi.fn(),
  obtenerReporteEjecucionNormalizador: vi.fn(),
  obtenerUrlReporteEjecucionNormalizador: vi.fn((idEjecucion) => `/api/normalizador/ejecuciones/${idEjecucion}/reporte`),
  eliminarEjecucionHistorialNormalizador: vi.fn(),
  obtenerCuarentenaNormalizador: vi.fn(),
  obtenerEjecucionNormalizador: vi.fn(),
  obtenerErroresNormalizador: vi.fn(),
  obtenerPendientesNormalizador: vi.fn(),
  obtenerUrlOutputNormalizador: vi.fn((idEjecucion, archivo) => `/api/normalizador/ejecuciones/${idEjecucion}/outputs/${archivo}`),
}));

async function renderPanelAfterRecovery() {
  const rendered = render(<NormalizadorPanel />);
  await waitFor(() => expect(screen.queryByText("Recuperando ejecución")).toBeNull());
  return rendered;
}

describe("panel del normalizador", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    listarEjecucionesNormalizador.mockResolvedValue({ ejecuciones: [], retencion: null });
    iniciarNormalizadorEmpleabilidad.mockResolvedValue({
      id_ejecucion: "NOR_0123456789abcdef",
      archivo: "fuente.xlsx",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_0123456789abcdef",
      archivo: "fuente.xlsx",
      estado: "normalizado",
      normalizacion: {
        publicable: true,
        registros_procesados: { publicaciones: 1, informes: 0 },
        relaciones: 1,
        cuarentena: 0,
      },
      catalogo_chh: { version: "demo", competencias: 1, habilidades: 1, herramientas: 1 },
      outputs: [{ tipo: "csv", archivo: "salidas/requerimiento_laboral.csv", registros: 1 }],
      hallazgos: [],
    });
    obtenerErroresNormalizador.mockResolvedValue({ hallazgos: [] });
    obtenerCuarentenaNormalizador.mockResolvedValue({ total: 0, filas: [] });
  });

  it("recupera al montar una ejecución curricular activa y continúa su seguimiento", async () => {
    const idEjecucion = "NOR_restaurar12345678";
    let resolverDetalle;
    const detallePendiente = new Promise((resolve) => {
      resolverDetalle = resolve;
    });
    listarEjecucionesNormalizador.mockResolvedValue({
      ejecuciones: [{
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        archivo: "marketing.zip",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        estado: "limpiando",
        actualizada_en: "2026-08-18T12:00:00+00:00",
      }],
      retencion: null,
    });
    obtenerEjecucionNormalizador.mockReturnValue(detallePendiente);

    render(<NormalizadorPanel />);

    expect(screen.getByText("Recuperando ejecución")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Sílabos" }).disabled).toBe(true);
    await waitFor(() => expect(obtenerEjecucionNormalizador).toHaveBeenCalledWith(idEjecucion));

    resolverDetalle({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "marketing.zip",
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [{ nombre: "marketing.pdf" }] },
      outputs: [],
      hallazgos: [],
      progreso_llm: {
        fase: "analista",
        chunks_completados: 2,
        chunks_totales: 4,
        logros_detectados: 20,
        logros_procesados: 10,
        logros_totales: 20,
        silabos_detectados: 1,
        silabos_procesados: 1,
        silabos_totales: 1,
        decisiones_cacheadas: 0,
        reintentos: 0,
        eventos: [],
      },
    });

    await waitFor(() => expect(screen.getByText("Limpiando datos")).toBeTruthy());
    expect(screen.queryByText("Recibido")).toBeNull();
    expect(screen.getByRole("tab", { name: "Sílabos" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("combobox", { name: "Carrera" }).value).toBe("Marketing");
    expect(screen.getByRole("combobox", { name: "Periodo" }).value).toBe("2026-1");
    expect(screen.getByText(/Procesamos los sílabos por lotes/)).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Progreso del flujo" }).getAttribute("aria-valuetext")).toMatch(/50%/);
  });

  it("limpia el polling al desmontar una ejecución restaurada", async () => {
    const idEjecucion = "NOR_timer12345678";
    const ejecucionActiva = {
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "marketing.zip",
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      outputs: [],
      hallazgos: [],
    };
    listarEjecucionesNormalizador.mockResolvedValue({ ejecuciones: [ejecucionActiva], retencion: null });
    obtenerEjecucionNormalizador.mockResolvedValue(ejecucionActiva);

    const { unmount } = render(<NormalizadorPanel />);
    await waitFor(() => expect(screen.getByText("Limpiando datos")).toBeTruthy());
    const llamadasAntesDeDesmontar = obtenerEjecucionNormalizador.mock.calls.length;

    unmount();
    await new Promise((resolve) => setTimeout(resolve, 1000));

    expect(obtenerEjecucionNormalizador).toHaveBeenCalledTimes(llamadasAntesDeDesmontar);
  });

  it("permite seleccionar una fuente y muestra el estado final", async () => {
    const { container } = await renderPanelAfterRecovery();
    const archivo = new File(["xlsx"], "fuente.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [archivo] } });

    expect(screen.getByText("fuente.xlsx")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Iniciar normalización" }));

    await waitFor(() => expect(screen.getByText("Listo para publicar")).toBeTruthy());
    expect(iniciarNormalizadorEmpleabilidad).toHaveBeenCalledWith(archivo);
    expect(screen.getByText(/Catálogo demo/)).toBeTruthy();
    const descarga = screen.getByRole("link", { name: /requerimiento_laboral\.csv/ });
    expect(descarga.getAttribute("download")).toBe("");
    expect(descarga.getAttribute("href")).toContain("/outputs/salidas/requerimiento_laboral.csv");
  });

  it("bloquea los controles mientras la ejecución curricular está activa", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_fedcba9876543210",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_fedcba9876543210",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      hallazgos: [],
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    const archivo = new File(["zip"], "curriculo.zip", { type: "application/zip" });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [archivo] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() => expect(screen.getByText("Limpiando datos")).toBeTruthy());
    expect(screen.getByRole("tab", { name: "Empleabilidad" }).disabled).toBe(true);
    expect(screen.getByRole("tab", { name: "Sílabos" }).disabled).toBe(true);
    expect(screen.getByRole("combobox", { name: "Carrera" }).disabled).toBe(true);
    expect(screen.getByRole("combobox", { name: "Periodo" }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Iniciar limpieza curricular" }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Nueva fuente" }).disabled).toBe(true);
    expect(iniciarNormalizadorSilabos).toHaveBeenCalledWith(archivo, "Marketing", "2026-1");
  });

  it("confirma la cancelación y detiene el polling de la ejecución curricular", async () => {
    const confirmacion = vi.spyOn(window, "confirm").mockReturnValue(true);
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      outputs: [],
      hallazgos: [],
    });
    cancelarEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_cancelar12345678",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      cancelacion_solicitada: true,
      hallazgos: [],
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(["zip"], "curriculo.zip", { type: "application/zip" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    const botonCancelar = await screen.findByRole("button", { name: "Cancelar procesamiento" });
    fireEvent.click(botonCancelar);

    await waitFor(() => expect(cancelarEjecucionNormalizador).toHaveBeenCalledWith("NOR_cancelar12345678"));
    expect(confirmacion).toHaveBeenCalledWith("¿Estás seguro de que deseas cancelar el procesamiento?");
    expect(screen.getByText("Cancelación solicitada. Recomendamos revisar el historial cuando el worker termine de cerrar la ejecución.")).toBeTruthy();
    confirmacion.mockRestore();
  });

  it("muestra el registro por etapas, hallazgos y una ejecución sin actividad reciente", async () => {
    const haceSeisMinutos = new Date(Date.now() - 6 * 60 * 1000).toISOString();
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_sin_actividad",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_sin_actividad",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      actualizada_en: haceSeisMinutos,
      validacion_silabos: { valida: true, archivos: [] },
      limpieza_silabos: null,
      outputs: [],
      hallazgos: [{
        codigo: "SILABO_CAMPO_FALTANTE",
        severidad: "warning",
        mensaje: "Falta una competencia en el sílabo.",
        hoja: "Marketing",
        fila: 8,
      }],
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    const archivo = new File(["zip"], "curriculo.zip", { type: "application/zip" });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [archivo] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "Registro de actividad" })).toBeTruthy());
    const registro = screen.getByLabelText("Registro de actividad");
    expect(within(registro).getByText("Recepción")).toBeTruthy();
    expect(within(registro).getByText("Validación")).toBeTruthy();
    expect(within(registro).getByText("Limpieza")).toBeTruthy();
    expect(within(registro).getByText("Publicación curricular")).toBeTruthy();
    expect(within(registro).getByText("Sin actividad reciente")).toBeTruthy();
    expect(within(registro).getByText("Advertencia")).toBeTruthy();
    expect(within(registro).getByText("SILABO_CAMPO_FALTANTE")).toBeTruthy();
    expect(within(registro).getByText(/Falta una competencia/)).toBeTruthy();
  });

  it("muestra la revisión curricular antes de los CSV y mantiene separados los artefactos de auditoría", async () => {
    const idEjecucion = "NOR_pre_csv12345678";
    const aprobacionPendiente = {
      requiere_decision: true,
      total: 1,
      pendientes_por_decidir: 1,
      remaining_pending: 1,
      materializacion: {
        candidatos_persistidos: true,
        csv_canonicos_disponibles: false,
      },
    };
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiado",
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      validacion_silabos: { valida: true, archivos: [] },
      limpieza_silabos: { registros: 1, relaciones: 1 },
      release_gate: {
        decision: "BLOCK_IMPORT",
        checks: { approval: { pending_decision: 1, canonical_materialized: false } },
      },
      aprobacion_curricular: aprobacionPendiente,
      outputs: [
        { tipo: "provenance", archivo: "salidas/reportes/competencias_fuente.jsonl", registros: 1 },
        { tipo: "pendientes_curriculares", archivo: "salidas/reportes/pendientes_curriculares.jsonl", registros: 1 },
        { tipo: "candidatos_curriculares", archivo: "salidas/reportes/candidatos_curriculares.json", registros: 1 },
        { tipo: "release_gate", archivo: "salidas/reportes/release_gate.json", registros: 1 },
      ],
      hallazgos: [],
    });
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [{
        id_pendiente: "PEND_1",
        tipo: "herramienta",
        archivo: "marketing.pdf",
        id_curso: "MKT-101",
        id_silabo: "SIL-1",
        propuesta: { nombre: "Google Analytics", descripcion: "Métrica de campañas" },
        evidencia: ["Analiza campañas con Google Analytics"],
        flags: ["SUSPICIOUS_UNRELATED_TOOL"],
        relevancia_herramienta: "SUSPICIOUS_UNRELATED",
      }],
      aprobacion: aprobacionPendiente,
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(["zip"], "curriculo.zip", { type: "application/zip" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() => expect(screen.getByText("Revisión requerida antes de generar CSV")).toBeTruthy());
    await waitFor(() => expect(screen.getByRole("heading", { name: "Revisión curricular requerida" })).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Auditoría y proveniencia" })).toBeTruthy();
    expect(screen.getByText("competencias_fuente.jsonl")).toBeTruthy();
    expect(screen.getByText("Google Analytics")).toBeTruthy();
    expect(screen.getByText("Herramienta sospechosa / no relacionada")).toBeTruthy();
    expect(screen.getByText("Los CSV canónicos no están disponibles hasta completar las decisiones curriculares.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "CSV curriculares listos" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Subir catálogos a Neo4j" })).toBeNull();
  });

  it("habilita la publicación en Neo4j solo con CSV materializados y release gate permitido", async () => {
    const idEjecucion = "NOR_allow_csv123456";
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "validando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: idEjecucion,
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiado",
      parametros: { carrera: "Marketing", periodo: "2026-1" },
      validacion_silabos: { valida: true, archivos: [] },
      release_gate: {
        decision: "ALLOW_IMPORT",
        checks: { approval: { pending_decision: 0, canonical_materialized: true } },
      },
      aprobacion_curricular: {
        requiere_decision: false,
        pendientes_por_decidir: 0,
        materializacion: { csv_canonicos_disponibles: true },
      },
      outputs: [
        { tipo: "csv_curricular", archivo: "salidas/catalogo_competencias.csv", registros: 1 },
        { tipo: "provenance", archivo: "salidas/reportes/provenance.jsonl", registros: 1 },
      ],
      hallazgos: [],
    });
    obtenerPendientesNormalizador.mockResolvedValue({ filas: [], aprobacion: null });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(["zip"], "curriculo.zip", { type: "application/zip" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() => expect(screen.getByRole("heading", { name: "CSV curriculares listos" })).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Subir catálogos a Neo4j" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /catalogo_competencias\.csv/ })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Revisión curricular requerida" })).toBeNull();
  });
});

describe("progreso LLM del normalizador", () => {
  afterEach(() => cleanup());

  it("muestra el progreso serializado por el manifest sin requerir un endpoint adicional", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_progreso_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_progreso_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [] },
      limpieza_silabos: null,
      outputs: [],
      hallazgos: [],
      progreso_llm: {
        fase: "inspector",
        chunks_completados: 3,
        chunks_totales: 5,
        logros_detectados: 40,
        logros_procesados: 24,
        logros_totales: 40,
        silabos_detectados: 10,
        silabos_procesados: 6,
        silabos_totales: 10,
        decisiones_cacheadas: 16,
        reintentos: 1,
        ultimo_chunk: { fase: "inspector", logros: 8, silabos: 2 },
        reporte_final: "pendiente",
        eventos: [{
          secuencia: 7,
          fase: "inspector",
          mensaje: "Chunk 3/5 de Inspector LLM completado: 8 logros y 2 sílabos únicos.",
          chunks_completados: 3,
          chunks_totales: 5,
          logros_chunk: 8,
          silabos_chunk: 2,
          logros_detectados: 40,
          silabos_detectados: 10,
          silabos_procesados: 6,
          decisiones_cacheadas: 16,
          reintentos: 1,
        }],
      },
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    const archivo = new File(["zip"], "curriculo.zip", { type: "application/zip" });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [archivo] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() => expect(screen.getByLabelText("Progreso de limpieza LLM")).toBeTruthy());
    const progreso = screen.getByLabelText("Progreso de limpieza LLM");
    expect(within(progreso).getByText("Inspector LLM")).toBeTruthy();
    expect(within(progreso).getByText("3/5 chunks de la fase actual.")).toBeTruthy();
    expect(within(progreso).getByText("Logros detectados")).toBeTruthy();
    expect(within(progreso).getByText("40")).toBeTruthy();
    expect(within(progreso).getByText("24 / 40")).toBeTruthy();
    expect(within(progreso).getByText("6 / 10")).toBeTruthy();
    expect(within(progreso).getByText("Sílabos detectados")).toBeTruthy();
    expect(within(progreso).getByText("Sílabos procesados por LLM")).toBeTruthy();
    expect(within(progreso).getByText(/sílabos detectados 10 · sílabos LLM 6/)).toBeTruthy();
    expect(within(progreso).getByText("16")).toBeTruthy();
    expect(within(progreso).getByText("Último chunk de Inspector LLM: 8 logros y 2 sílabos.")).toBeTruthy();
    expect(within(progreso).getByText("Chunk 3/5 de Inspector LLM completado: 8 logros y 2 sílabos únicos.")).toBeTruthy();
    const barra = within(progreso).getByRole("progressbar", { name: "Avance de chunks LLM" });
    expect(barra.getAttribute("aria-valuenow")).toBe("3");
    expect(barra.getAttribute("aria-valuetext")).toBe("3 de 5 chunks");
    expect(obtenerEjecucionNormalizador).toHaveBeenCalledWith("NOR_progreso_llm");
  });

  it("mantiene visible el seguimiento mientras el manifest aún no tiene progreso LLM", async () => {
    iniciarNormalizadorSilabos.mockResolvedValue({
      id_ejecucion: "NOR_preparando_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
    });
    obtenerEjecucionNormalizador.mockResolvedValue({
      id_ejecucion: "NOR_preparando_llm",
      tipo: "silabos",
      archivo: "curriculo.zip",
      estado: "limpiando",
      validacion_silabos: { valida: true, archivos: [{ nombre: "uno.pdf" }] },
      limpieza_silabos: null,
      outputs: [],
      hallazgos: [],
      progreso_llm: null,
    });

    const { container } = await renderPanelAfterRecovery();
    fireEvent.click(screen.getByRole("tab", { name: "Sílabos" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Carrera" }), { target: { value: "Marketing" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Periodo" }), { target: { value: "2026-1" } });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(["zip"], "curriculo.zip", { type: "application/zip" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Iniciar limpieza curricular" }));

    await waitFor(() => expect(screen.getByLabelText("Progreso de limpieza LLM")).toBeTruthy());
    expect(screen.getByText("Preparando…")).toBeTruthy();
    expect(screen.getAllByText(/El seguimiento aparecerá aquí enseguida/).length).toBeGreaterThan(0);
  });
});
