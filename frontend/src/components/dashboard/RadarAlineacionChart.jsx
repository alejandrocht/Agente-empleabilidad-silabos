"use client";

import { PolarAngleAxis, PolarGrid, Radar, RadarChart } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";

export default function RadarAlineacionChart({ filas, etiquetas = { mercado: "Mercado", curriculo: "Currículo" } }) {
  const chartConfig = {
    mercado: { label: etiquetas.mercado, color: "#FF5117" },
    curriculo: { label: etiquetas.curriculo, color: "#00C5D6" },
  };

  return (
    <ChartContainer config={chartConfig} className="h-72 min-h-[18rem] w-full">
      <RadarChart data={filas} outerRadius="68%">
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(valor) => valor}
              formatter={(valor) => Number(valor).toLocaleString("es-PE") + "%"}
            />
          }
        />
        <PolarGrid stroke="#DAC9B5" />
        <PolarAngleAxis
          dataKey="eje"
          tick={{ fill: "#7A6F66", fontSize: 10, fontWeight: 600 }}
        />
        <Radar
          dataKey="mercado"
          stroke="var(--color-mercado)"
          fill="var(--color-mercado)"
          fillOpacity={0.16}
          strokeWidth={2}
        />
        <Radar
          dataKey="curriculo"
          stroke="var(--color-curriculo)"
          fill="var(--color-curriculo)"
          fillOpacity={0.16}
          strokeWidth={2}
        />
      </RadarChart>
    </ChartContainer>
  );
}
