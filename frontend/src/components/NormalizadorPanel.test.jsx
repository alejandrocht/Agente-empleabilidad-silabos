import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NormalizadorPanel from "./NormalizadorPanel";
import {
  iniciarNormalizadorEmpleabilidad,
  iniciarNormalizadorSilabos,
  obtenerCuarentenaNormalizador,
  obtenerEjecucionNormalizador,
  obtenerErroresNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  iniciarNormalizadorEmpleabilidad: vi.fn(),
  iniciarNormalizadorSilabos: vi.fn(),
  obtenerCuarentenaNormalizador: vi.fn(),
  obtenerEjecucionNormalizador: vi.fn(),
  obtenerErroresNormalizador: vi.fn(),
  obtenerUrlOutputNormalizador: vi.fn((idEjecucion, archivo) => `/api/normalizador/ejecuciones/${idEjecucion}/outputs/${archivo}`),
}));

describe("panel del normalizador", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
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

  it("permite seleccionar una fuente y muestra el estado final", async () => {
    const { container } = render(<NormalizadorPanel />);
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

    const { container } = render(<NormalizadorPanel />);
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

    const { container } = render(<NormalizadorPanel />);
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

    const { container } = render(<NormalizadorPanel />);
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

    const { container } = render(<NormalizadorPanel />);
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
