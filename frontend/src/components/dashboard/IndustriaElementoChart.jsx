"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";
import EstadoGrafico from "./EstadoGrafico";

const chartConfig = {
  ofertas: { label: "Ofertas", color: "#2E8C7F" },
};

export default function IndustriaElementoChart({ filas, cargando, error }) {
  if (cargando || error || !filas?.length) {
    return <EstadoGrafico cargando={cargando} error={error} vacio={!filas?.length} />;
  }

  return (
    <ChartContainer config={chartConfig} className="h-60 min-h-[15rem] w-full">
      <BarChart accessibilityLayer data={[...filas].reverse()} layout="vertical" margin={{ top: 2, right: 12, left: 4, bottom: 2 }}>
        <CartesianGrid horizontal={false} stroke="#EAE2D9" />
        <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#7A6F66", fontSize: 11 }} />
        <YAxis
          dataKey="industria"
          type="category"
          width={145}
          axisLine={false}
          tickLine={false}
          tick={{ fill: "#4F463F", fontSize: 11 }}
        />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(valor) => valor} />} />
        <Bar dataKey="ofertas" fill="var(--color-ofertas)" radius={[5, 5, 5, 5]} />
      </BarChart>
    </ChartContainer>
  );
}
