import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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

const technicalProposal = {
  id_pendiente: "PROP_TEC_1",
  tipo: "competencia_tecnica",
  nombre_competencia: "Diseñar arquitecturas de software",
  descripcion_breve_competencia: "Seleccionar patrones técnicos.",
  nombre_curso: "Arquitectura de software",
  id_curso: "CUR-TECH-1",
  id_silabo: "SIL-TECH-1",
  evidencia: ["Diseña arquitecturas de software."],
};

function approvalResponse(filas = [technicalProposal]) {
  return {
    filas,
    revision: "rev-technical",
    aprobacion: {
      requiere_decision: Boolean(filas.length),
      pendientes_por_decidir: filas.length,
    },
  };
}

describe("aprobación técnica de propuestas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    obtenerPendientesNormalizador.mockResolvedValue(approvalResponse());
  });

  afterEach(() => cleanup());

  it("muestra el nombre del curso y oculta los IDs de curso y sílabo", async () => {
    render(<CurricularApprovalPanel idEjecucion="NOR_TECHNICAL" />);

    const card = await screen.findByTestId("curricular-proposal-card");
    expect(within(card).getByText("Arquitectura de software")).toBeTruthy();
    expect(within(card).queryByText("CUR-TECH-1", { exact: true })).toBeNull();
    expect(within(card).queryByText("SIL-TECH-1", { exact: true })).toBeNull();
    expect(within(card).getByText("PROP_TEC_1", { exact: true })).toBeTruthy();
    expect(screen.queryByTestId("curricular-package-card")).toBeNull();
  });

  it("conserva el ID interno al enviar una decisión técnica", async () => {
    obtenerPendientesNormalizador
      .mockResolvedValueOnce(approvalResponse())
      .mockResolvedValueOnce(approvalResponse([]));
    decidirPendientesNormalizador.mockResolvedValue({
      aprobacion: { accepted_in_request: 1, remaining_pending: 0 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_TECHNICAL" />);
    const card = await screen.findByTestId("curricular-proposal-card");
    fireEvent.click(
      within(card).getByRole("button", {
        name: /Agregar al catálogo para Diseñar arquitecturas de software/,
      }),
    );

    await waitFor(() =>
      expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
        "NOR_TECHNICAL",
        [{ id_pendiente: "PROP_TEC_1", decision: "ADD" }],
        "ejecutor",
        "rev-technical",
      ),
    );
  });

  it("descarta una propuesta técnica con un solo clic y sin motivo", async () => {
    obtenerPendientesNormalizador
      .mockResolvedValueOnce(approvalResponse())
      .mockResolvedValueOnce(approvalResponse([]));
    decidirPendientesNormalizador.mockResolvedValue({
      aprobacion: { discarded: 1, remaining_pending: 0 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_DISCARD" />);
    const card = await screen.findByTestId("curricular-proposal-card");
    fireEvent.click(
      within(card).getByRole("button", { name: "Descartar propuesta" }),
    );

    expect(screen.queryByLabelText("Motivo del descarte")).toBeNull();
    expect(screen.queryByRole("button", { name: "Confirmar descarte" })).toBeNull();
    await waitFor(() =>
      expect(decidirPendientesNormalizador).toHaveBeenCalledWith(
        "NOR_DISCARD",
        [{ id_pendiente: "PROP_TEC_1", decision: "DISCARD" }],
        "ejecutor",
        "rev-technical",
      ),
    );
  });

  it("no muestra el checkpoint cuando no hay propuestas técnicas abiertas", async () => {
    obtenerPendientesNormalizador.mockResolvedValue({
      filas: [],
      aprobacion: { requiere_decision: false, pendientes_por_decidir: 0 },
    });

    render(<CurricularApprovalPanel idEjecucion="NOR_EMPTY" />);

    await waitFor(() =>
      expect(obtenerPendientesNormalizador).toHaveBeenCalled(),
    );
    expect(
      screen.queryByRole("heading", { name: "Revisión técnica requerida" }),
    ).toBeNull();
  });
});
