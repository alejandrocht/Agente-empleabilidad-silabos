import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HistorialEjecucionesPanel from "./HistorialEjecucionesPanel";
import {
  eliminarEjecucionHistorialNormalizador,
  listarEjecucionesNormalizador,
} from "../api/normalizador";

vi.mock("../api/normalizador", () => ({
  eliminarEjecucionHistorialNormalizador: vi.fn(),
  listarEjecucionesNormalizador: vi.fn(),
}));

describe("historial de ejecuciones", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    listarEjecucionesNormalizador.mockResolvedValue({
      ejecuciones: [
        {
          id_ejecucion: "NOR_0123456789abcdef",
          tipo: "silabos",
          archivo: "marketing.zip",
          parametros: { carrera: "Marketing", periodo: "2026-1" },
          estado: "cancelado",
          actualizada_en: "2026-08-17T12:00:00+00:00",
          resumen: { advertencias: 2, errores: 1, outputs: 4 },
        },
      ],
      retencion: { max_ejecuciones: 20, dias: 15 },
    });
  });

  it("abre la inspección en una pestaña nueva con un enlace seguro", async () => {
    render(<HistorialEjecucionesPanel />);

    expect(await screen.findByText("Marketing")).toBeTruthy();
    expect(
      screen.getByText("2 advertencias · 1 errores · 4 salidas"),
    ).toBeTruthy();
    const inspeccionar = screen.getByRole("link", { name: "Inspeccionar" });
    expect(inspeccionar.tagName).toBe("A");
    expect(inspeccionar.getAttribute("target")).toBeNull();
    expect(inspeccionar.getAttribute("href")).toBe("/NOR_0123456789abcdef");
  });

  it("permite abrir el progreso mientras la ejecución sigue limpiando", async () => {
    listarEjecucionesNormalizador.mockResolvedValueOnce({
      ejecuciones: [
        {
          id_ejecucion: "NOR_activa12345678",
          tipo: "silabos",
          archivo: "marketing.zip",
          parametros: { carrera: "Marketing", periodo: "2026-1" },
          estado: "limpiando",
          actualizada_en: "2026-08-18T12:00:00+00:00",
          resumen: { advertencias: 0, errores: 0, outputs: 0 },
        },
      ],
      retencion: null,
    });

    render(<HistorialEjecucionesPanel />);

    const control = await screen.findByRole("link", { name: "Inspeccionar" });
    expect(control.getAttribute("href")).toBe("/NOR_activa12345678");
  });

  it("confirma y elimina una ejecución del historial", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    eliminarEjecucionHistorialNormalizador.mockResolvedValue({
      eliminado: true,
    });
    render(<HistorialEjecucionesPanel />);
    await screen.findByText("Marketing");

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    await waitFor(() =>
      expect(eliminarEjecucionHistorialNormalizador).toHaveBeenCalledWith(
        "NOR_0123456789abcdef",
      ),
    );
    expect(listarEjecucionesNormalizador).toHaveBeenCalledTimes(2);
  });
});
