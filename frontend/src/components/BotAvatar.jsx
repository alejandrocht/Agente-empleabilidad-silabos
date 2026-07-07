import { useState } from "react";

export default function BotAvatar({ size = "md" }) {
  const [fallo, setFallo] = useState(false);
  const medidas = size === "lg" ? "h-14 w-14" : "h-10 w-10";

  return (
    <div className={`${medidas} shrink-0 overflow-hidden rounded-full bg-ulima/10 ring-1 ring-ulima/20`}>
      {!fallo ? (
        <img
          src="/images.png"
          alt="Agente Ciar"
          className="h-full w-full object-cover"
          onError={() => setFallo(true)}
        />
      ) : (
        <div className="grid h-full w-full place-items-center bg-ulima text-sm font-extrabold text-white">
          AC
        </div>
      )}
    </div>
  );
}
