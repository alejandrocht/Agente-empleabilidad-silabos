import { useState } from "react";

export default function BotAvatar({ size = "md", girando = false }) {
  const [fallo, setFallo] = useState(false);
  const medidas = size === "lg" ? "h-14 w-14 p-2" : "h-9 w-9 p-1.5 sm:h-10 sm:w-10";

  return (
    <div className={`${medidas} shrink-0 rounded-xl border border-ulima/30 bg-ulima/10`}>
      {!fallo ? (
        <img
          src="/logo-ulima.png"
          alt="Agente CIAR"
          className={`h-full w-full object-contain ${girando ? "animate-girar" : ""}`}
          onError={() => setFallo(true)}
        />
      ) : (
        <div className="grid h-full w-full place-items-center rounded-lg bg-ulima text-sm font-extrabold text-white">
          AC
        </div>
      )}
    </div>
  );
}
