import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InspeccionEjecucionNormalizador, {
  parseCsvPreview,
} from "./InspeccionEjecucionNormalizador";
import {
  decidirPendientesNormalizador,
  obtenerPendientesNormalizador,
  obtenerReporteEjecucionNormalizador,
  obtenerUrlOutputNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  decidirPendientesNormalizador: vi.fn(),
  obtenerPendientesNormalizador: vi.fn(),
  obtenerReporteEjecucionNormalizador: vi.fn(),
  obtenerUrlOutputNormalizador: vi.fn(
    (id, archivo) => `/outputs/${id}/${archivo}`,
  ),
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
        release_gate: {
          decision: "ALLOW_IMPORT",
          checks: {
            approval: { pending_decision: 0, canonical_materialized: true },
          },
        },
        aprobacion_curricular: {
          requiere_decision: false,
          pendientes_por_decidir: 0,
          materializacion: { csv_canonicos_disponibles: true },
        },
        limpieza_silabos: {
          registros: 3,
          competencias: 2,
          habilidades: 4,
          herramientas: 1,
          relaciones: 5,
          outputs: [
            {
              archivo: "salidas/catalogo_competencias.csv",
              tipo: "csv_curricular",
              registros: 2,
            },
            {
              archivo: "salidas/catalogo_habilidades.csv",
              tipo: "csv_curricular",
              registros: 45,
            },
            {
              archivo: "salidas/catalogo_herramientas.csv",
              tipo: "csv_curricular",
              registros: 2,
            },
            {
              archivo: "salidas/cobertura_curricular.csv",
              tipo: "csv_curricular",
              registros: 5,
            },
          ],
        },
        hallazgos: [
          {
            codigo: "ARCHIVO_NO_CURRICULAR",
            severidad: "warning",
            mensaje: "Se omitió un archivo accesorio.",
          },
        ],
        progreso_llm: {
          eventos: [
            {
              secuencia: 1,
              fase: "completado",
              mensaje: "Reporte LLM disponible.",
            },
          ],
        },
      },
      reportes: {
        "decisiones_llm.jsonl": [
          {
            estado: "PENDIENTE_REVISION_HUMANA",
            id_habilidad_fuente: "HAB_1",
            justificacion: "Evidencia suficiente.",
          },
          {
            estado: "REVISAR_VALIDACION",
            id_habilidad_fuente: "HAB_2",
            problemas: ["Requiere revisión."],
          },
        ],
        "analisis_llm.json": { estado: "COMPLETADO", propuestas_pendientes: 1 },
      },
    });
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      aprobacion: null,
    });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: null });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url) => ({
        ok: true,
        text: async () => {
          if (url.includes("catalogo_habilidades")) {
            return [
              "id_habilidad,nombre_habilidad",
              ...Array.from(
                { length: 45 },
                (_item, indice) => `HAB_${indice + 1},Habilidad ${indice + 1}`,
              ),
            ].join("\n");
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

  it("muestra el checkpoint humano histórico y explica por qué no habilita Neo4j sin CSV canónicos", async () => {
    const idEjecucion = "NOR_b468b1fb2b9c4268";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "limpiado_con_advertencias",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        limpieza_silabos: {
          outputs: [
            {
              archivo: "salidas/reportes/pendientes_curriculares.jsonl",
              tipo: "pendientes_curriculares",
              registros: 174,
            },
            {
              archivo: "salidas/reportes/release_gate.json",
              tipo: "release_gate",
              registros: 1,
            },
          ],
        },
        aprobacion_curricular: {
          requiere_decision: true,
          pendientes_por_decidir: 174,
          remaining_pending: 174,
          materializacion: { csv_canonicos_disponibles: false },
        },
        release_gate: {
          decision: "BLOCK_IMPORT",
          blockers: ["PENDING_DECISIONS", "CANONICAL_MATERIALIZATION_PENDING"],
          checks: {
            approval: { pending_decision: 174, canonical_materialized: false },
          },
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [
        {
          id_pendiente: "PEND_1",
          tipo: "habilidad",
          propuesta: {
            nombre: "Analítica digital",
            descripcion: "Propuesta curricular",
          },
          evidencia: ["Evidencia del sílabo"],
        },
      ],
      aprobacion: {
        requiere_decision: true,
        pendientes_por_decidir: 174,
        remaining_pending: 174,
      },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    expect(
      await screen.findByRole("heading", {
        name: "Revisión curricular requerida",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: /Agregar al perfil para Analítica digital/i,
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeNull();
    expect(
      within(screen.getByRole("tabpanel", { name: "Normalizador" })).getByText(
        "174",
        { exact: true },
      ),
    ).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Qué falta para publicar" }),
    ).toBeNull();
    expect(
      screen.queryByText("Resolver 174 decisiones curriculares"),
    ).toBeNull();
    expect(screen.queryByText(/CSV listos con advertencias/i)).toBeNull();
  });

  it("muestra la revisión por paquetes cuando el resumen de filas no marca decisiones, pero sí hay paquetes pendientes", async () => {
    const idEjecucion = "NOR_PACKAGE_SUMMARY_DRIFT";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "limpiado_con_advertencias",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        aprobacion_curricular: {
          requiere_decision: false,
          pendientes_por_decidir: 0,
          remaining_pending: 1,
          paquetes: { total: 1, pendientes_por_decidir: 1 },
        },
        release_gate: {
          decision: "BLOCK_IMPORT",
          checks: {
            approval: { pending_decision: 0, canonical_materialized: false },
          },
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [],
      paquetes: [
        {
          id_paquete_chh: "PKG_CHH_PENDING",
          source_identity: {
            carrera: "Marketing",
            periodo: "2026-1",
            id_curso: "MKT-101",
            id_silabo: "SIL-1",
          },
          componentes: {
            competencias: [{ nombre: "Competencia pendiente" }],
            habilidades: [{ nombre: "Habilidad pendiente" }],
            herramientas: [],
          },
          filas: [
            {
              id_pendiente: "PEN_PACKAGE_1",
              evidencia: ["Evidencia del sílabo"],
            },
          ],
          relaciones: [],
        },
      ],
      revision: "rev-package-summary-drift",
      aprobacion: {
        requiere_decision: false,
        pendientes_por_decidir: 0,
        paquetes: { total: 1, pendientes_por_decidir: 1 },
      },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    expect(
      await screen.findByRole("heading", {
        name: "Revisión curricular requerida",
      }),
    ).toBeTruthy();
    expect(screen.getByTestId("curricular-package-card")).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: /Agregar al perfil para paquete PKG_CHH_PENDING/i,
      }),
    ).toBeTruthy();
    const normalizador = screen.getByRole("tabpanel", { name: "Normalizador" });
    expect(
      within(normalizador).getByRole("heading", {
        name: "Resultados positivos y estado",
      }),
    ).toBeTruthy();
    expect(
      within(normalizador).getByRole("heading", {
        name: "Conteos de la normalización",
      }),
    ).toBeTruthy();
    expect(
      within(normalizador).getByRole("heading", {
        name: "Revisión curricular requerida",
      }),
    ).toBeTruthy();
    expect(
      within(normalizador).queryByRole("heading", {
        name: "Qué falta para publicar",
      }),
    ).toBeNull();
    expect(
      within(normalizador).queryByRole("heading", {
        name: "Avisos que requieren atención",
      }),
    ).toBeNull();
    expect(within(normalizador).queryByText("Siguiente paso")).toBeNull();
  });

  it("mantiene Neo4j bloqueado aunque existan tres CSV cuando quedan decisiones sin resolver", async () => {
    const idEjecucion = "NOR_BLOCKED_CSV123456";
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: idEjecucion,
        tipo: "silabos",
        estado: "limpiado",
        parametros: { carrera: "Marketing", periodo: "2026-1" },
        validacion_silabos: { valida: true },
        limpieza_silabos: {
          outputs: [
            {
              archivo: "salidas/catalogo_competencias.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
            {
              archivo: "salidas/catalogo_habilidades.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
            {
              archivo: "salidas/catalogo_herramientas.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
          ],
        },
        aprobacion_curricular: {
          requiere_decision: true,
          pendientes_por_decidir: 1,
          materializacion: { csv_canonicos_disponibles: false },
        },
        release_gate: {
          decision: "BLOCK_IMPORT",
          blockers: ["PENDING_DECISIONS"],
          checks: {
            approval: { pending_decision: 1, canonical_materialized: false },
          },
        },
      },
      reportes: {},
    });
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [
        {
          id_pendiente: "PEND_BLOCKED",
          tipo: "habilidad",
          propuesta: { nombre: "Habilidad pendiente" },
        },
      ],
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion={idEjecucion} />);

    expect(
      await screen.findByRole("heading", {
        name: "Revisión curricular requerida",
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Qué falta para publicar" }),
    ).toBeNull();
    expect(screen.queryByText("Resolver 1 decisión curricular")).toBeNull();
    expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
    expect(screen.queryByText("BLOCK_IMPORT")).toBeNull();
    expect(screen.queryByText("PENDING_DECISIONS")).toBeNull();
    expect(screen.queryByRole("tabpanel", { name: "Logs" })).toBeNull();
  });

  it("tolera hallazgos malformados en reportes legados sin renderizar logs internos", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_LEGACY_SHAPES",
        tipo: "silabos",
        estado: "limpiado",
        carrera: "Marketing legacy",
        periodo: "2025-2",
        hallazgos: [
          null,
          {
            codigo: "LEGACY_WARNING",
            severidad: "warning",
            mensaje: "Advertencia legada.",
          },
        ],
      },
      reportes: {
        "decisiones_llm.jsonl": [
          null,
          { estado: "ACEPTADA", justificacion: "Decisión legada." },
        ],
        eventos_llm: {
          eventos: [null, { fase: "legacy", mensaje: "Evento legado." }],
        },
      },
    });

    render(<InspeccionEjecucionNormalizador idEjecucion="NOR_LEGACY_SHAPES" />);

    await screen.findByRole("tab", { name: "Advertencias y errores" });
    expect(screen.queryByText("Decisión legada.")).toBeNull();
    expect(screen.queryByText("Evento legado.")).toBeNull();
    fireEvent.click(
      screen.getByRole("tab", { name: "Advertencias y errores" }),
    );
    const warnings = screen.getByRole("tabpanel", {
      name: "Advertencias y errores",
    });
    expect(within(warnings).getByText("Advertencia legada.")).toBeTruthy();
  });

  it("expone solo las vistas humanas y mantiene los artefactos técnicos fuera del frontend", async () => {
    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_0123456789abcdef" />,
    );

    const tablist = await screen.findByRole("tablist", {
      name: "Secciones de la inspección",
    });
    expect(within(tablist).getAllByRole("tab")).toHaveLength(2);
    const normalizador = screen.getByRole("tabpanel", { name: "Normalizador" });
    expect(normalizador.hidden).toBe(false);
    expect(within(normalizador).queryByText("Salidas generadas")).toBeNull();
    expect(
      within(normalizador).queryByText("Decisiones LLM aceptadas"),
    ).toBeNull();
    expect(
      screen
        .getByRole("tab", { name: "Normalizador" })
        .getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
    expect(screen.queryByRole("tabpanel", { name: "Logs" })).toBeNull();
    expect(screen.queryByText("Salidas generadas")).toBeNull();
    expect(screen.queryByText("Logs y eventos")).toBeNull();
  });

  it("agrupa hallazgos accionables desde el payload y no duplica la extracción cactus incompleta", async () => {
    obtenerReporteEjecucionNormalizador.mockResolvedValueOnce({
      manifest: {
        id_ejecucion: "NOR_GROUPED_FINDINGS",
        tipo: "silabos",
        estado: "limpiado_con_advertencias",
        hallazgos: [
          {
            codigo: "HABILIDAD_NO_CATALOGADA",
            severidad: "warning",
            mensaje: "No existe en catálogo.",
          },
          {
            codigo: "HABILIDAD_PENDIENTE_CANONICALIZACION",
            severidad: "warning",
            mensaje: "Requiere equivalencia.",
          },
          {
            codigo: "LOGRO_CODIGO_INCONSISTENTE",
            severidad: "warning",
            mensaje: "Código distinto.",
          },
          {
            codigo: "COMPETENCIA_REFERENCIADA_NO_DECLARADA",
            severidad: "error",
            mensaje: "Falta declaración.",
          },
          {
            codigo: "COMPETENCIA_DECLARADA_SIN_LOGRO",
            severidad: "warning",
            mensaje: "Falta logro.",
          },
          {
            codigo: "EXTRACCION_CACTUS_INCOMPLETA",
            severidad: "warning",
            mensaje: "Extracción parcial.",
          },
        ],
      },
      reportes: {
        "extraccion_cactus.json": {
          errores: [
            {
              codigo: "CACTUS_SIN_SILABO",
              mensaje: "No se descargó el sílabo del curso 1.",
            },
            {
              codigo: "CACTUS_SIN_SILABO",
              mensaje: "No se descargó el sílabo del curso 2.",
            },
          ],
        },
      },
    });

    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_GROUPED_FINDINGS" />,
    );
    fireEvent.click(
      await screen.findByRole("tab", { name: "Advertencias y errores" }),
    );

    const panel = screen.getByRole("tabpanel", {
      name: "Advertencias y errores",
    });
    const habilidades = within(panel)
      .getByRole("heading", { name: "Habilidades aún no están en el catálogo" })
      .closest("article");
    const logros = within(panel)
      .getByRole("heading", { name: "Logros tienen un código inconsistente" })
      .closest("article");
    const competencias = within(panel)
      .getByRole("heading", { name: "Inconsistencias en competencias" })
      .closest("article");
    const cactus = within(panel)
      .getByRole("heading", { name: "Cursos sin sílabo descargable" })
      .closest("article");
    expect(within(habilidades).getByText("2 avisos")).toBeTruthy();
    expect(within(logros).getByText("1 aviso")).toBeTruthy();
    expect(within(competencias).getByText("2 avisos")).toBeTruthy();
    expect(within(cactus).getByText("2 avisos")).toBeTruthy();
    expect(cactus.className).toContain("border-line");
    expect(
      within(competencias).getByText("Competencia referenciada no declarada"),
    ).toBeTruthy();
    expect(
      within(competencias).getByText("Competencia declarada sin logro"),
    ).toBeTruthy();
    expect(
      within(cactus).queryByText("EXTRACCION_CACTUS_INCOMPLETA"),
    ).toBeNull();
    expect(
      within(panel).queryByRole("heading", {
        name: "Otros avisos registrados",
      }),
    ).toBeNull();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("muestra resultados positivos, conteos y alertas sin exponer artefactos técnicos", async () => {
    render(
      <InspeccionEjecucionNormalizador idEjecucion="NOR_0123456789abcdef" />,
    );

    expect(await screen.findByText("Inspección de ejecución")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText("Validación curricular aprobada")).toBeTruthy(),
    );
    const parametros = screen.getByRole("region", {
      name: "Parámetros de la ejecución",
    });
    expect(within(parametros).getByText("Marketing")).toBeTruthy();
    expect(within(parametros).getByText("2026-1")).toBeTruthy();
    const main = screen.getByRole("main");
    expect(main.className).toContain("h-[100dvh]");
    expect(main.className).toContain("overflow-y-auto");
    expect(main.className).toContain("overscroll-y-contain");
    expect(main.className).toContain("pb-24");
    expect(main.className).toContain("sm:pb-32");
    const conteos = screen
      .getByRole("heading", { name: "Conteos de la normalización" })
      .closest("section");
    expect(within(conteos).getByText("registros procesados")).toBeTruthy();
    expect(within(conteos).getByText("3", { exact: true })).toBeTruthy();
    expect(within(conteos).getByText("competencias")).toBeTruthy();
    expect(within(conteos).getByText("2", { exact: true })).toBeTruthy();
    expect(within(conteos).getByText("relaciones de cobertura")).toBeTruthy();
    expect(within(conteos).getByText("5", { exact: true })).toBeTruthy();
    const normalizador = screen.getByRole("tabpanel", { name: "Normalizador" });
    expect(within(normalizador).queryByText("Salidas generadas")).toBeNull();
    expect(
      within(normalizador).queryByText("catalogo_competencias.csv"),
    ).toBeNull();
    expect(
      within(normalizador).queryByText("Decisiones LLM aceptadas"),
    ).toBeNull();
    expect(within(normalizador).queryByText("Logs y eventos")).toBeNull();
    expect(
      within(normalizador).queryByRole("heading", {
        name: "Qué falta para publicar",
      }),
    ).toBeNull();
    expect(
      within(normalizador).queryByRole("heading", {
        name: "Avisos que requieren atención",
      }),
    ).toBeNull();
    expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
    expect(screen.queryByRole("tabpanel", { name: "Logs" })).toBeNull();
    expect(
      within(normalizador).queryByText("Se omitió un archivo accesorio."),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("tab", { name: "Advertencias y errores" }),
    );
    const warnings = screen.getByRole("tabpanel", {
      name: "Advertencias y errores",
    });
    expect(within(warnings).getByText("Advertencias y errores")).toBeTruthy();
    expect(
      within(warnings).getByText("Se omitió un archivo accesorio."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Normalizador" }));
    expect(
      await within(
        screen.getByRole("tabpanel", { name: "Normalizador" }),
      ).findByRole("button", { name: "Subir datos a Neo4j" }),
    ).toBeTruthy();
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
          outputs: [
            {
              archivo: "salidas/final.csv",
              tipo: "csv_curricular",
              registros: 1,
            },
          ],
        },
        reportes: {},
      });

    try {
      render(<InspeccionEjecucionNormalizador idEjecucion="NOR_ACTIVA" />);

      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });

      const progreso = screen.getByRole("status", {
        name: "Progreso de la ejecución",
      });
      expect(progreso).toBeTruthy();
      expect(screen.getByText("Ejecución en curso")).toBeTruthy();
      expect(within(progreso).getByText("Limpiando datos")).toBeTruthy();
      expect(screen.getByText(/29 de 38 chunks completados/)).toBeTruthy();
      expect(
        within(progreso).getByText(/Las salidas se habilitarán al finalizar\./),
      ).toBeTruthy();
      expect(
        screen.queryByText("Esta ejecución no declara salidas CSV accesibles."),
      ).toBeNull();
      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(1);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("tab", { name: "Logs" })).toBeNull();
      expect(screen.queryByText("final.csv")).toBeNull();
      const llamadasTrasEstadoTerminal =
        obtenerReporteEjecucionNormalizador.mock.calls.length;

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });

      expect(obtenerReporteEjecucionNormalizador).toHaveBeenCalledTimes(
        llamadasTrasEstadoTerminal,
      );
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

    const parametros = await screen.findByRole("region", {
      name: "Parámetros de la ejecución",
    });
    expect(within(parametros).getByText("Marketing legacy")).toBeTruthy();
    expect(within(parametros).getByText("2025-2")).toBeTruthy();
  });

  it("parsea celdas CSV con comillas y respeta el límite solicitado", () => {
    const contenido = [
      "id,nombre,detalle",
      '1,"Competencia, datos","Texto con ""comillas"""',
      ...Array.from(
        { length: 120 },
        (_item, indice) => `${indice + 2},Nombre ${indice + 2},Detalle`,
      ),
    ].join("\n");

    const preview = parseCsvPreview(contenido, 100);

    expect(preview.encabezados).toEqual(["id", "nombre", "detalle"]);
    expect(preview.filas[0]).toEqual([
      "1",
      "Competencia, datos",
      'Texto con "comillas"',
    ]);
    expect(preview.filas).toHaveLength(100);
    expect(preview.truncado).toBe(true);
  });
});
