import { afterEach, describe, expect, it, vi } from "vitest";
import { obtenerEstadoNeo4j } from "./neo4j";

describe("obtenerEstadoNeo4j", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads the safe Neo4j status endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ state: "connected" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(obtenerEstadoNeo4j()).resolves.toEqual({ state: "connected" });

    expect(fetchMock).toHaveBeenCalledWith("/api/neo4j/estado", { signal: undefined });
  });

  it("rejects failed status requests with the API detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      json: vi.fn().mockResolvedValue({ detail: "No disponible" }),
    }));

    await expect(obtenerEstadoNeo4j()).rejects.toThrow("No disponible");
  });
});
