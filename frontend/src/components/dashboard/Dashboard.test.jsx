import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";

function ChartStub({ filas, cargando, error, disponible = true, motivo }) {
  if (cargando) return <p>Cargando datos del grafo...</p>;
  if (error) return <p>{error}</p>;
  if (!disponible || !filas?.length) return <p>{motivo || "No hay datos para estos filtros."}</p>;
  return <div data-testid="chart-success">{filas.length} filas</div>;
}

vi.mock("next/link", () => ({
  default: ({ children, ...props }) => <a {...props}>{children}</a>,
}));
vi.mock("./TendenciaOfertasChart", () => ({ default: ChartStub }));
vi.mock("./RankingDimensionChart", () => ({ default: ChartStub }));
vi.mock("./BrechaCurriculoMercadoChart", () => ({ default: ChartStub }));
vi.mock("./BarrasComparativasChart", () => ({ default: ChartStub }));

function createApi(dataRows = [{ elemento: "Python", ofertas: 3 }]) {
  const response = (filas = dataRows) => Promise.resolve({ filas });
  return {
    obtenerMetadatosDashboard: () => Promise.resolve({
      periodo_disponible: { desde: "2025-01-01", hasta: "2025-01-31" },
    }),
    obtenerCarrerasDashboard: () => Promise.resolve({
      carreras: [{ id: "CAR_demo", nombre: "Sistemas", cursos_conectados: 2 }],
    }),
    obtenerTendenciaDashboard: () => response([{ anio: 2025, mes: 1, ofertas: 3 }]),
    obtenerCarrerasPorDemandaDashboard: () => response(),
    obtenerIndustriasPorCarreraDashboard: () => response(),
    obtenerDemandaDashboard: () => response(),
    obtenerCoberturaDashboard: () => response(),
    obtenerBrechasDashboard: () => response(),
    obtenerEmpresasDashboard: () => response(),
  };
}

describe("Dashboard data boundary", () => {
  afterEach(() => cleanup());

  it("shows a loading state while the backend catalog is pending", () => {
    let resolveMetadata;
    const api = createApi();
    api.obtenerMetadatosDashboard = () => new Promise((resolve) => { resolveMetadata = resolve; });

    render(<Dashboard api={api} />);

    expect(screen.getByText(/Cargando catálogo/)).toBeTruthy();
    resolveMetadata({ periodo_disponible: { desde: null, hasta: null } });
  });

  it("renders connected data after metadata and query requests succeed", async () => {
    render(<Dashboard api={createApi()} />);

    await waitFor(() => expect(screen.getAllByText("Datos del grafo").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByTestId("chart-success").length).toBeGreaterThan(0));
  });

  it("allows changing the connected date range within the available period", async () => {
    const api = createApi();
    const tendencias = [];
    api.obtenerTendenciaDashboard = (parametros) => {
      tendencias.push(parametros);
      return Promise.resolve({ filas: [{ anio: 2025, mes: 1, ofertas: 3 }] });
    };

    render(<Dashboard api={api} />);

    const desde = await screen.findByLabelText("Desde");
    const hasta = screen.getByLabelText("Hasta");
    expect(desde.disabled).toBe(false);
    expect(hasta.disabled).toBe(false);
    expect(desde.getAttribute("min")).toBe("2025-01-01");
    expect(hasta.getAttribute("max")).toBe("2025-01-31");

    fireEvent.change(desde, { target: { value: "2025-01-10" } });

    await waitFor(() => expect(
      tendencias.some((parametros) => parametros.desde === "2025-01-10"),
    ).toBe(true));
  });

  it("uses the documented demo fallback only when the backend is unavailable", async () => {
    const api = createApi();
    api.obtenerMetadatosDashboard = () => Promise.reject(Object.assign(new Error("offline"), { status: 503 }));

    render(<Dashboard api={api} />);

    await waitFor(() => expect(screen.getByText("Datos de demostración")).toBeTruthy());
    expect(screen.getByText(/API del dashboard no está disponible/)).toBeTruthy();
  });

  it("renders an empty state when the connected backend returns no rows", async () => {
    render(<Dashboard api={createApi([])} />);

    await waitFor(() => expect(screen.getAllByText("No hay datos para estos filtros.").length).toBeGreaterThan(0));
    expect(screen.queryByText("Datos de demostración")).toBeNull();
  });
});
