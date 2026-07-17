"use client";

import { Cell, Pie, PieChart } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "../ui/chart";

const colores = ["#00C5D6", "#FF5117", "#00C78B"];

export default function AnilloAlineacionChart({ indice }) {
  const datos = [
    { nombre: "Cobertura consistente", valor: indice },
    { nombre: "Espacio de revisión", valor: 100 - indice },
  ];

  return (
    <div className="relative">
      <ChartContainer
        config={{
          consistente: { label: "Cobertura consistente", color: "#00C5D6" },
          revision: { label: "Espacio de revisión", color: "#FF5117" },
        }}
        className="h-52 min-h-[13rem] w-full"
      >
        <PieChart accessibilityLayer>
          <ChartTooltip content={<ChartTooltipContent hideLabel />} />
          <Pie
            data={datos}
            dataKey="valor"
            nameKey="nombre"
            innerRadius={64}
            outerRadius={86}
            startAngle={90}
            endAngle={-270}
            cornerRadius={7}
            paddingAngle={4}
          >
            {datos.map((fila, indiceColor) => (
              <Cell key={fila.nombre} fill={colores[indiceColor]} />
            ))}
          </Pie>
        </PieChart>
      </ChartContainer>
      <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
        <div>
          <p className="text-3xl font-extrabold tracking-tight text-ink">{indice}</p>
          <p className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted">índice demo</p>
        </div>
      </div>
    </div>
  );
}
