"use client";

import { CartesianGrid, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";
import EstadoGrafico from "./EstadoGrafico";

const chartConfig = {
  brecha: { label: "Brecha", color: "#FF5117" },
};

export default function MapaPriorizacionChart({ filas, cargando, error, disponible, motivo }) {
  if (cargando || error || !disponible || !filas?.length) {
    return (
      <EstadoGrafico
        cargando={cargando}
        error={error}
        vacio={!disponible || !filas?.length}
        mensajeVacio={motivo || "No hay elementos comparables para estos filtros."}
      />
    );
  }

  const datos = filas.map((fila) => ({
    ...fila,
    coberturaPct: fila.cobertura * 100,
    demandaPct: fila.demanda * 100,
    tamano: Math.max(36, Math.min(180, fila.ofertas_que_requieren)),
  }));

  return (
    <ChartContainer config={chartConfig} className="h-72 min-h-[18rem] w-full">
      <ScatterChart accessibilityLayer margin={{ top: 10, right: 18, left: -8, bottom: 8 }}>
        <CartesianGrid stroke="#EAE2D9" strokeDasharray="3 3" />
        <XAxis
          dataKey="coberturaPct"
          type="number"
          name="Cobertura declarada"
          domain={[0, 100]}
          unit="%"
          axisLine={false}
          tickLine={false}
          tick={{ fill: "#7A6F66", fontSize: 11 }}
        />
        <YAxis
          dataKey="demandaPct"
          type="number"
          name="Demanda laboral"
          domain={[0, 100]}
          unit="%"
          axisLine={false}
          tickLine={false}
          tick={{ fill: "#7A6F66", fontSize: 11 }}
        />
        <ZAxis dataKey="tamano" range={[40, 210]} />
        <ChartTooltip
          cursor={{ strokeDasharray: "4 4" }}
          content={
            <ChartTooltipContent
              labelFormatter={(_, payload) => payload?.[0]?.payload?.elemento || "Elemento"}
              formatter={(valor) => Number(valor).toLocaleString("es-PE", { maximumFractionDigits: 1 }) + "%"}
            />
          }
        />
        <Scatter data={datos} fill="var(--color-brecha)" />
      </ScatterChart>
    </ChartContainer>
  );
}
