import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InspeccionEjecucionNormalizador, { parseCsvPreview } from "./InspeccionEjecucionNormalizador";
import {
  obtenerReporteEjecucionNormalizador,
  obtenerUrlOutputNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  obtenerReporteEjecucionNormalizador: vi.fn(),
  obtenerUrlOutputNormalizador: vi.fn((id, archivo) => `/outputs/${id}/${archivo}`),
  obtenerUrlReporteEjecucionNormalizador: vi.fn((id) => `/reports/${id}`),
}));

vi.mock("../api/neo4j", () => ({
  importarEnNeo4j: vi.fn(),
  listarImportacionesNeo4j: vi.fn().mockResolvedValue({ importaciones: [] }),
  revertirImportacionNeo4j: vi.fn(),
  validarImportacionNeo4j: vi.fn(),
}));

describe("inspección de ejecución normalizada", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    obtenerReporteEjecucionNormalizador.mockResolvedValue({
      manifest: {
        id_ejecucion: "NOR_0123456789abcdef",
        estado: "limpiado",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        validacion_silabos: { valida: true },
        limpieza_silabos: {
          registros: 3,
          competencias: 2,
          habilidades: 4,
          herramientas: 1,
          relaciones: 5,
          outputs: [
            { archivo: "salidas/catalogo_competencias.csv", tipo: "csv_curricular", registros: 2 },
            { archivo: "salidas/catalogo_habilidades.csv", tipo: "csv_curricular", registros: 45 },
            { archivo: "salidas/catalogo_herramientas.csv", tipo: "csv_curricular", registros: 2 },
            { archivo: "salidas/cobertura_curricular.csv", tipo: "csv_curricular", registros: 5 },
          ],
        },
        hallazgos: [{ codigo: "ARCHIVO_NO_CURRICULAR", severidad: "warning", mensaje: "Se omitió un archivo accesorio." }],
        progreso_llm: {
          eventos: [{ secuencia: 1, fase: "completado", mensaje: "Reporte LLM disponible." }],
        },
      },
      reportes: {
        "decisiones_llm.jsonl": [
          { estado: "ACEPTADA", id_habilidad_fuente: "HAB_1", justificacion: "Evidencia suficiente." },
          { estado: "REVISAR_INSPECTOR", id_habilidad_fuente: "HAB_2", problemas: ["Requiere revisión."] },
        ],
        "analisis_llm.json": { estado: "COMPLETADO", decisiones_aceptadas: 1 },
      },
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url) => ({
        ok: true,
        text: async () => {
          if (url.includes("catalogo_habilidades")) {
            return ["id_habilidad,nombre_habilidad", ...Array.from({ length: 45 }, (_item, indice) => `HAB_${indice + 1},Habilidad ${indice + 1}`)].join("\n");
          }
          if (url.includes("catalogo_herramientas")) {
            return "id_herramienta,nombre_herramienta\nHERR_1,Excel\nHERR_2,Power BI\n";
          }
          if (url.includes("competencias")) {
            return "id_competencia,nombre_competencia\nCOM_1,Analizar datos\nCOM_2,Comunicar resultados\n";
          }
          return "id_cob_curricular,id_curso\nCOB_1,CUR_1\nCOB_2,CUR_2\n";
        },
      })),
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("muestra resultados positivos, conteos, CSV, decisiones aceptadas y alertas separadas", async () => {
    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_0123456789abcdef" />);

    expect(await screen.findByText("Inspección de ejecución")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Validación curricular aprobada")).toBeTruthy());
    const parametros = screen.getByRole("region", { name: "Parámetros de la ejecución" });
    expect(within(parametros).getByText("Marketing")).toBeTruthy();
    expect(within(parametros).getByText("2026-1")).toBeTruthy();
    const main = screen.getByRole("main");
    expect(main.className).toContain("h-[100dvh]");
    expect(main.className).toContain("overflow-y-auto");
    expect(main.className).toContain("overscroll-y-contain");
    expect(main.className).toContain("pb-24");
    expect(main.className).toContain("sm:pb-32");
    const conteos = screen.getByRole("heading", { name: "Conteos de la normalización" }).parentElement;
    expect(within(conteos).getByText("registros procesados")).toBeTruthy();
    expect(within(conteos).getByText("3", { exact: true })).toBeTruthy();
    expect(within(conteos).getByText("competencias")).toBeTruthy();
    expect(within(conteos).getByText("2", { exact: true })).toBeTruthy();
    expect(within(conteos).getByText("relaciones de cobertura")).toBeTruthy();
    expect(within(conteos).getByText("5", { exact: true })).toBeTruthy();
    expect(screen.getByText("catalogo_competencias.csv")).toBeTruthy();
    expect(screen.getByText("Analizar datos")).toBeTruthy();
    expect(screen.getByText("catalogo_habilidades.csv")).toBeTruthy();
    expect(screen.getByText("catalogo_herramientas.csv")).toBeTruthy();
    expect(screen.queryByText("Vista previa de cobertura_curricular.csv")).toBeNull();
    expect(screen.getByText("Habilidad 1")).toBeTruthy();
    expect(screen.queryByText("Habilidad 21")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Página siguiente de catalogo_habilidades.csv" }));
    expect(screen.getByText("Habilidad 21")).toBeTruthy();
    expect(screen.getByText(/Página 2 de 3/)).toBeTruthy();
    expect(screen.getByText("Evidencia suficiente.")).toBeTruthy();
    expect(screen.getByText("Advertencias y errores")).toBeTruthy();
    expect(screen.getByText("Se omitió un archivo accesorio.")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Subir datos a Neo4j" })).toBeTruthy();
    expect(obtenerUrlOutputNormalizador).toHaveBeenCalled();
  });

  it("muestra el progreso activo, no trata la ausencia temporal de CSV como fallo y hace polling hasta el estado terminal", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    obtenerReporteEjecucionNormalizador.mockReset();
    obtenerReporteEjecucionNormalizador
      .mockResolvedValueOnce({
        manifest: {
          id_ejecucion: "NOR_ACTIVA",
          estado: "limpiando",
          parametros: { carrera: "Marketing", periodo: "2026-1" },
          progreso_llm: {
            chunks_completados: 29,
            chunks_totales: 38,
            eventos: [{ secuencia: 29, mensaje: "Chunk 29 completado." }],
          },
        },
        reportes: {},
      })
      .mockResolvedValueOnce({
        manifest: {
          id_ejecucion: "NOR_ACTIVA",
          estado: "limpiado",
          parametros: { carrera: "Marketing", periodo: "2026-1" },
          outputs: [{ archivo: "salidas/final.csv", tipo: "csv_curricular", registros: 1 }],
        },
        reportes: {},
      });

    try {
      render(<InspeccionEjecucionNormalizador idEjecucion="NOR_ACTIVA" />);

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const progreso = screen.getByRole("status", { name: "Progreso de la ejecución" });
      expect(progreso).toBeTruthy();
      expect(screen.getByText("Ejecución en curso")).toBeTruthy();
      expect(within(progreso).getByText("Limpiando datos")).toBeTruthy();
      expect(screen.getByText(/29 de 38 chunks completados/)).toBeTruthy();
      expect(within(progreso).getByText(/Las salidas CSV se habilitarán al finalizar\./)).toBeTruthy();
      expect(screen.queryByText("Esta ejecución no declara salidas CSV accesibles.")).toBeNull();
      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(2);
      expect(screen.getByText("final.csv")).toBeTruthy();
      const llamadasTrasEstadoTerminal = obtenerReporteEjecucionNormalizador.mock.calls.length;

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(llamadasTrasEstadoTerminal);
    } finally {
      vi.useRealTimers();
    }
  });

  it("usa campos legados cuando el manifest no tiene parametros anidados", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_LEGACY",
        estado: "limpiado",
        carrera: "Marketing legacy",
        periodo: "2025-2",
      },
      reportes: {},
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_LEGACY" />);

    const parametros = await screen.findByRole("region", { name: "Parámetros de la ejecución" });
    expect(within(parametros).getByText("Marketing legacy")).toBeTruthy();
    expect(within(parametros).getByText("2025-2")).toBeTruthy();
  });

  it("parsea celdas CSV con comillas y respeta el límite solicitado", () => {
    const contenido = [
      "id,nombre,detalle",
      '1,"Competencia, datos","Texto con ""comillas"""',
      ...Array.from({ length: 120 }, (_item, indice) => `${indice + 2},Nombre ${indice + 2},Detalle`),
    ].join("\n");

    const preview = parseCsvPreview(contenido, 100);

    expect(preview.encabezados).toEqual(["id", "nombre", "detalle"]);
    expect(preview.filas[0]).toEqual(["1", "Competencia, datos", 'Texto con "comillas"']);
    expect(preview.filas).toHaveLength(100);
    expect(preview.truncado).toBe(true);
  });
});
