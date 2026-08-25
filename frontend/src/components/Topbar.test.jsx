import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Topbar from "./Topbar";
import { obtenerEstadoNeo4j } from "../api/neo4j";

vi.mock("../api/neo4j", () => ({
  obtenerEstadoNeo4j: vi.fn(),
}));

function renderTopbar() {
  return render(<Topbar conversacion={{ titulo: "Consulta" }} onAbrirMenu={vi.fn()} />);
}

describe("Topbar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("shows a loading status before reporting a connected Neo4j graph", async () => {
    obtenerEstadoNeo4j.mockResolvedValue({ state: "connected" });

    renderTopbar();

    expect(screen.getByRole("status", { name: "Estado de Neo4j: verificando" })).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByRole("status", { name: "Estado de Neo4j: conectado" })).toBeTruthy();
    });
  });

  it("shows an accessible mismatch state when Neo4j has the wrong graph", async () => {
    obtenerEstadoNeo4j.mockResolvedValue({
      state: "schema_mismatch",
      missing_labels: ["OfertaLaboral"],
    });

    renderTopbar();

    expect(await screen.findByRole("status", { name: "Estado de Neo4j: esquema incompatible" })).toBeTruthy();
    expect(screen.getByTitle("Neo4j: esquema incompatible")).toBeTruthy();
  });

  it("shows a disconnected state when the status request fails", async () => {
    obtenerEstadoNeo4j.mockRejectedValue(new Error("network down"));

    renderTopbar();

    expect(await screen.findByRole("status", { name: "Estado de Neo4j: no disponible" })).toBeTruthy();
  });

  it("polls every five seconds and cleans the timer on unmount", async () => {
    vi.useFakeTimers();
    obtenerEstadoNeo4j.mockResolvedValue({ state: "connected" });

    const { unmount } = renderTopbar();
    await act(async () => {});
    expect(obtenerEstadoNeo4j).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(obtenerEstadoNeo4j).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(obtenerEstadoNeo4j).toHaveBeenCalledTimes(2);
  });
});
