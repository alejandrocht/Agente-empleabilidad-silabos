import { afterEach, describe, expect, it, vi } from "vitest";
import {
  iniciarNormalizadorSilabos,
  iniciarNormalizadorSilabosCactus,
} from "./normalizador";

describe("iniciarNormalizadorSilabos", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends hitl=1 by default in the file FormData payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ id_ejecucion: "NOR_file" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const archivo = new File(["zip"], "curriculo.zip", {
      type: "application/zip",
    });

    await iniciarNormalizadorSilabos(archivo, "Marketing", "2026-1");

    const [, request] = fetchMock.mock.calls[0];
    expect(request.body).toBeInstanceOf(FormData);
    expect(request.body.get("hitl")).toBe("1");
  });

  it("sends hitl=0 in the file FormData payload when selected", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ id_ejecucion: "NOR_file_auto" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const archivo = new File(["zip"], "curriculo.zip", {
      type: "application/zip",
    });

    await iniciarNormalizadorSilabos(archivo, "Marketing", "2026-1", 0);

    const [, request] = fetchMock.mock.calls[0];
    expect(request.body.get("hitl")).toBe("0");
  });
});

describe("iniciarNormalizadorSilabosCactus", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends hitl=1 by default in the Cactus JSON payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ id_ejecucion: "NOR_cactus" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await iniciarNormalizadorSilabosCactus(
      "Marketing",
      "2026-1",
      "usuario",
      "secreto",
    );

    const [, request] = fetchMock.mock.calls[0];
    expect(JSON.parse(request.body)).toMatchObject({
      carrera: "Marketing",
      periodo: "2026-1",
      usuario: "usuario",
      contrasena: "secreto",
      hitl: 1,
    });
  });

  it("sends hitl=0 in the Cactus JSON payload when selected", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ id_ejecucion: "NOR_cactus_auto" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await iniciarNormalizadorSilabosCactus(
      "Marketing",
      "2026-1",
      "usuario",
      "secreto",
      0,
    );

    const [, request] = fetchMock.mock.calls[0];
    expect(JSON.parse(request.body).hitl).toBe(0);
  });
});
