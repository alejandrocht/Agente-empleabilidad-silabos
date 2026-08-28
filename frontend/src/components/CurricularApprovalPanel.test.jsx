import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CurricularApprovalPanel from "./CurricularApprovalPanel";
import {
  decidirPendientesNormalizador,
  obtenerPendientesNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  decidirPendientesNormalizador: vi.fn(),
  obtenerPendientesNormalizador: vi.fn(),
}));

const propuestas = [
  {
    id_pendiente: "PEN_EXACT_1",
    tipo: "competencia",
    archivo: "marketing.docx",
    id_curso: "MKT-101",
    id_silabo: "SIL-1",
    propuesta: { nombre: "Diseño omnicanal", descripcion: "Diseñar campañas omnicanal." },
    descripcion_fuente: "La fuente declara diseño omnicanal.",
    evidencia: ["Diseñar campañas omnicanal."],
    flags: ["EXACT_DUPLICATE"],
    duplicado_exacto: true,
    grupo_duplicado_exacto: "EXACT_123",
    exact_duplicate_representative_id: "PEN_EXACT_1",
    auto_deduplicated: false,
  },
  {
    id_pendiente: "PEN_EXACT_2",
    tipo: "competencia",
    archivo: "marketing.docx",
    id_curso: "MKT-102",
    id_silabo: "SIL-2",
    propuesta: { nombre: "Diseño omnicanal", descripcion: "Gestionar campañas omnicanal." },
    evidencia: ["Gestionar campañas omnicanal."],
    flags: ["EXACT_DUPLICATE"],
    duplicado_exacto: true,
    grupo_duplicado_exacto: "EXACT_123",
    exact_duplicate_representative_id: "PEN_EXACT_1",
    auto_deduplicated: true,
    auto_deduplication_state: "AUTO_DEDUPLICATED",
  },
  {
    id_pendiente: "PEN_SEM_1",
    tipo: "habilidad",
    archivo: "marketing.docx",
    id_curso: "MKT-201",
    id_silabo: "SIL-3",
    etiqueta_logro: "L1",
    propuesta: { nombre: "Análisis de datos empresariales", descripcion: "Analizar datos." },
    evidencia: ["Analizar datos."],
    flags: ["POSSIBLE_SEMANTIC_DUPLICATE"],
    posible_duplicado_semantico: true,
    grupo_duplicado_semantico: "SEM_456",
  },
  {
    id_pendiente: "PEN_SEM_2",
    tipo: "habilidad",
    archivo: "marketing.docx",
    id_curso: "MKT-202",
    id_silabo: "SIL-4",
    propuesta: { nombre: "Análisis de datos comerciales", descripcion: "Analizar datos." },
    evidencia: ["Analizar datos."],
    flags: ["POSSIBLE_SEMANTIC_DUPLICATE"],
    posible_duplicado_semantico: true,
    grupo_duplicado_semantico: "SEM_456",
  },
  {
    id_pendiente: "PEN_TOOL",
    tipo: "herramienta",
    archivo: "marketing.docx",
    id_curso: "MKT-301",
    id_silabo: "SIL-5",
    propuesta: { nombre: "Slack", descripcion: "Herramienta de colaboración." },
    descripcion_fuente: "La actividad evalúa estados financieros.",
    evidencia: ["Evaluar estados financieros."],
    flags: ["SUSPICIOUS_UNRELATED_TOOL"],
    herramienta_no_relacionada: true,
    relevancia_herramienta: "SUSPICIOUS_UNRELATED",
  },
];

const resumen = {
  requiere_decision: true,
  total: propuestas.length,
  pendientes_por_decidir: propuestas.length - 1,
  remaining_pending: propuestas.length - 1,
  clasificacion: {
    exact_duplicate_rows: 2,
    semantic_duplicate_rows: 2,
    suspicious_unrelated_tool_rows: 1,
  },
};

describe("aprobación de propuestas curriculares", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("muestra filtros, badges con explicación y proveniencia sin ocultar filas", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({ filas: propuestas, aprobacion: resumen });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    expect(await screen.findByRole("heading", { name: "Revisión curricular requerida" })).toBeTruthy();
    expect(screen.getByText(/Las coincidencias exactas se deduplican automáticamente/)).toBeTruthy();
    expect(screen.getAllByTestId("curricular-proposal-card")).toHaveLength(5);
    expect(screen.getAllByText("Duplicado exacto")).toHaveLength(2);
    expect(screen.getAllByText(/deduplicó automáticamente/)).toHaveLength(2);
    expect(screen.getAllByText(/fusionó automáticamente/)).toHaveLength(2);
    expect(screen.getAllByText("Posible duplicado semántico")).toHaveLength(2);
    expect(screen.getAllByText("Proveniencia y evidencia de fuente")).toHaveLength(5);
    expect(screen.getAllByText("marketing.docx")).toHaveLength(5);
    expect(screen.getAllByText("Diseñar campañas omnicanal.")).toHaveLength(2);
    const autoCard = screen.getAllByTestId("curricular-proposal-card").find(
      (card) => card.dataset.pendingId === "PEN_EXACT_2",
    );
    expect(autoCard).toBeTruthy();
    expect(within(autoCard).queryByRole("button", { name: /ADD:/ })).toBeNull();
    expect(within(autoCard).getByText(/Deduplicada automáticamente/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Duplicados exactos/ }));
    expect(screen.getAllByTestId("curricular-proposal-card")).toHaveLength(2);
    expect(screen.queryByText("Análisis de datos empresariales")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Todas/ }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar propuestas curriculares" }), {
      target: { value: "Slack" },
    });
    expect(screen.getAllByTestId("curricular-proposal-card")).toHaveLength(1);
    expect(screen.getByText("Herramienta sospechosa / no relacionada")).toBeTruthy();
    expect(screen.getByText(/La evidencia no relaciona claramente la herramienta/)).toBeTruthy();
  });

  it("permite decisiones ADD y KEEP_PENDING explícitas y envía solo lo seleccionado", async () => {
    obtenerPendientesNormalizador
      .mockResolvedValueOnce({ filas: propuestas.slice(2, 4), aprobacion: { ...resumen, total: 2, pendientes_por_decidir: 2 } })
      .mockResolvedValueOnce({ filas: [], aprobacion: { requiere_decision: false, accepted: 1, remaining_pending: 1 } });
    decidirPendientesNormalizador.mockResolvedValue({
      aprobacion: { accepted_in_request: 1, kept_pending_in_request: 1, remaining_pending: 1 },
    });
    const onResolved = vi.fn();

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" onResolved={onResolved} />);

    expect(await screen.findAllByText("Análisis de datos empresariales")).toHaveLength(1);
    const cards = screen.getAllByTestId("curricular-proposal-card");
    fireEvent.click(within(cards[0]).getByRole("button", { name: /ADD: agregar Análisis de datos empresariales/ }));
    fireEvent.click(within(cards[1]).getByRole("button", { name: /KEEP_PENDING: mantener pendiente Análisis de datos comerciales/ }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar decisiones (2)" }));

    await waitFor(() => {
      expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
        "NOR_0123456789abcdef",
        [
          { id_pendiente: "PEN_SEM_1", decision: "ADD" },
          { id_pendiente: "PEN_SEM_2", decision: "KEEP_PENDING" },
        ],
      );
      expect(onResolved).toHaveBeenCalled();
    });
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(within(screen.getByRole("status")).getByText(/Decisiones guardadas/)).toBeTruthy();
  });

  it("no permite guardar un lote vacío y conserva visibles las propuestas sin decisión", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [propuestas[0]],
      aprobacion: { requiere_decision: true, total: 1, pendientes_por_decidir: 1 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    const guardar = await screen.findByRole("button", { name: "Guardar decisiones" });
    expect(guardar.disabled).toBe(true);
    expect(screen.getByText("Sin decisión; seguirá pendiente.")).toBeTruthy();
    expect(screen.getByTestId("curricular-proposal-card")).toBeTruthy();
  });

  it("renderiza el paquete completo y envía una sola decisión atómica", async () => {
    const paquete = {
      id_paquete_chh: "PKG_CHH_123",
      source_identity: { carrera: "MARKETING", periodo: "2026-1", id_curso: "MKT-101", id_silabo: "SIL-1" },
      componentes: {
        competencias: [{ nombre: "Diseño omnicanal" }],
        habilidades: [{ nombre: "Diseñar campañas" }],
        herramientas: [],
      },
      filas: [{ id_pendiente: "PEN_COMP", evidencia: ["Diseñar campañas omnicanal."] }],
      relaciones: [{ id_competencia: "COMP_1", id_habilidad: "HAB_1", id_herramienta: "" }],
    };
    obtenerPendientesNormalizador.mockResolvedValueOnce({
      filas: [],
      paquetes: [paquete],
      revision: "rev-1",
      aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
    }).mockResolvedValueOnce({ filas: [], paquetes: [], aprobacion: { requiere_decision: false } });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: { accepted_in_request: 1 } });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);
    const card = await screen.findByTestId("curricular-package-card");
    expect(within(card).getByText("Diseño omnicanal")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: /ADD: agregar paquete PKG_CHH_123/ }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar decisiones (1)" }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_0123456789abcdef",
      [{ id_paquete_chh: "PKG_CHH_123", decision: "ADD" }],
      "ejecutor",
      "rev-1",
    ));
  });

  it("usa el fallback legacy cuando el API devuelve paquetes vacío", async () => {
    obtenerPendientesNormalizador
      .mockResolvedValueOnce({
        filas: [propuestas[0]],
        paquetes: [],
        aprobacion: { requiere_decision: true, pendientes_por_decidir: 1 },
      })
      .mockResolvedValueOnce({ filas: [], paquetes: [], aprobacion: { requiere_decision: false } });
    decidirPendientesNormalizador.mockResolvedValue({ aprobacion: { accepted_in_request: 1 } });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    const card = await screen.findByTestId("curricular-proposal-card");
    expect(within(card).getByText("Diseño omnicanal")).toBeTruthy();
    expect(screen.queryByTestId("curricular-package-card")).toBeNull();
    fireEvent.click(within(card).getByRole("button", { name: /ADD: agregar Diseño omnicanal/ }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar decisiones (1)" }));

    await waitFor(() => expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
      "NOR_0123456789abcdef",
      [{ id_pendiente: "PEN_EXACT_1", decision: "ADD" }],
    ));
  });

  it("no muestra el checkpoint cuando no hay propuestas abiertas", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      aprobacion: { requiere_decision: false, total: 0 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_0123456789abcdef" />);

    await waitFor(() => expect(obtenerPendientesNormalizador).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: "Revisión curricular requerida" })).toBeNull();
  });
});
