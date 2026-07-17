"use client";

import { Bar, BarChart, CartesianGrid, Legend, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";

function abreviar(valor) {
  return valor.length > 25 ? valor.slice(0, 24) + "…" : valor;
}

export default function BarrasComparativasChart({ filas, series, etiquetaEje = "elemento", apiladas = false }) {
  const config = Object.fromEntries(
    series.map((serie) => [serie.clave, { label: serie.etiqueta, color: serie.color }]),
  );

  return (
    <ChartContainer config={config} className="h-72 min-h-[18rem] w-full">
      <BarChart accessibilityLayer data={[...filas].reverse()} layout="vertical" margin={{ top: 2, right: 16, left: 6, bottom: 2 }}>
        <CartesianGrid horizontal={false} stroke="#EAE2D9" />
        <XAxis type="number" domain={[0, 100]} tickFormatter={(valor) => valor + "%"} axisLine={false} tickLine={false} tick={{ fill: "#7A6F66", fontSize: 11 }} />
        <YAxis dataKey={etiquetaEje} type="category" width={136} axisLine={false} tickLine={false} tick={{ fill: "#4F463F", fontSize: 11 }} tickFormatter={abreviar} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(valor) => valor} formatter={(valor) => Number(valor).toLocaleString("es-PE") + "%"} />} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, paddingTop: 12 }} />
        {series.map((serie) => (
          <Bar
            key={serie.clave}
            dataKey={serie.clave}
            name={serie.etiqueta}
            fill={serie.color}
            stackId={apiladas ? "estado" : undefined}
            radius={[4, 4, 4, 4]}
          />
        ))}
      </BarChart>
    </ChartContainer>
  );
}
