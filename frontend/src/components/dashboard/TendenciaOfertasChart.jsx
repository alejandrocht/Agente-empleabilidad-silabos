"use client";

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";
import EstadoGrafico from "./EstadoGrafico";

const chartConfig = {
  ofertas: { label: "Ofertas", color: "#FF5117" },
};

export default function TendenciaOfertasChart({ filas }) {
  const datos = filas || [];
  if (!datos.length) return <EstadoGrafico vacio />;

  return (
    <ChartContainer config={chartConfig} className="h-72 min-h-[18rem] w-full">
      <AreaChart accessibilityLayer data={datos} margin={{ top: 10, right: 12, left: -18, bottom: 4 }}>
        <defs>
          <linearGradient id="ofertas-demo" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--color-ofertas)" stopOpacity={0.34} />
            <stop offset="100%" stopColor="var(--color-ofertas)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="#EAE2D9" />
        <XAxis
          dataKey="periodo"
          axisLine={false}
          tickLine={false}
          tickMargin={10}
          tick={{ fill: "#7A6F66", fontSize: 11 }}
        />
        <YAxis
          allowDecimals={false}
          axisLine={false}
          tickLine={false}
          tickMargin={8}
          tick={{ fill: "#7A6F66", fontSize: 11 }}
        />
        <ChartTooltip
          content={<ChartTooltipContent labelFormatter={(valor) => "Ofertas · " + valor} />}
          cursor={{ stroke: "#DAC9B5", strokeDasharray: "4 4" }}
        />
        <Area
          type="monotone"
          dataKey="ofertas"
          stroke="var(--color-ofertas)"
          fill="url(#ofertas-demo)"
          strokeWidth={2.5}
          dot={{ r: 3, fill: "var(--color-ofertas)", strokeWidth: 0 }}
          activeDot={{ r: 5 }}
        />
      </AreaChart>
    </ChartContainer>
  );
}
