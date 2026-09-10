import { Check, Copy } from "lucide-react";
import { useState } from "react";
import BotAvatar from "./BotAvatar";
import PanelRazonamiento, { detalleError } from "./PanelRazonamiento";

const ETIQUETAS_FASE = {
  analizando: "Analizando tu consulta…",
  preparando_consulta: "Preparando la consulta…",
  validando_consulta: "Validando consulta de solo lectura…",
  consultando_grafo: "Consultando el grafo…",
  redactando: "Escribiendo la respuesta…",
  completado: "Respuesta lista",
};

function textoEnLinea(texto) {
  return texto.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((parte, indice) => {
    if (parte.startsWith("**") && parte.endsWith("**")) {
      return <strong key={`${indice}-${parte}`}>{parte.slice(2, -2)}</strong>;
    }
    if (parte.startsWith("`") && parte.endsWith("`")) {
      return (
        <code key={`${indice}-${parte}`} className="rounded bg-ash px-1 py-0.5 text-[0.9em]">
          {parte.slice(1, -1)}
        </code>
      );
    }
    return parte;
  });
}

export function renderRespuesta(texto) {
  const bloques = [];
  let parrafo = [];
  let lista = [];

  const cerrarParrafo = () => {
    if (parrafo.length) {
      bloques.push(
        <p key={`p-${bloques.length}`}>
          {textoEnLinea(parrafo.join(" "))}
        </p>,
      );
      parrafo = [];
    }
  };

  const cerrarLista = () => {
    if (lista.length) {
      bloques.push(
        <ul key={`ul-${bloques.length}`} className="list-disc space-y-1 pl-5">
          {lista.map((item, indice) => (
            <li key={`${indice}-${item}`}>{textoEnLinea(item)}</li>
          ))}
        </ul>,
      );
      lista = [];
    }
  };

  texto.split(/\r?\n/).forEach((linea) => {
    const contenido = linea.trim();
    if (!contenido) {
      cerrarParrafo();
      cerrarLista();
      return;
    }

    const encabezado = contenido.match(/^#{1,3}\s+(.+)$/);
    if (encabezado) {
      cerrarParrafo();
      cerrarLista();
      bloques.push(
        <h3 key={`h-${bloques.length}`} className="pt-2 text-base font-bold text-ink">
          {textoEnLinea(encabezado[1])}
        </h3>,
      );
      return;
    }

    const elementoLista = contenido.match(/^[-*]\s+(.+)$/);
    if (elementoLista) {
      cerrarParrafo();
      lista.push(elementoLista[1]);
      return;
    }

    cerrarLista();
    parrafo.push(contenido);
  });

  cerrarParrafo();
  cerrarLista();
  return bloques;
}

export default function Burbuja({ mensaje }) {
  const esUsuario = mensaje.rol === "usuario";
  const [copiado, setCopiado] = useState(false);
  const entidades = Array.isArray(mensaje.entidades) ? mensaje.entidades : [];
  const texto = typeof mensaje.texto === "string" ? mensaje.texto : "";
  const error = typeof mensaje.error === "string" ? mensaje.error : "";
  const errorRed = typeof mensaje.errorRed === "string" ? mensaje.errorRed : "";
  const cypher = typeof mensaje.cypher === "string" ? mensaje.cypher : "";
  const fase = typeof mensaje.fase === "string" ? mensaje.fase : "";
  const progreso = typeof mensaje.progreso === "string" ? mensaje.progreso : "";
  const etiquetaFase = ETIQUETAS_FASE[fase] || "Analizando tu consulta…";
  const textoVisible = texto;
  const detalle = error ? detalleError(error) : null;
  const tieneContenidoStreaming = Boolean(
    texto || cypher || error || errorRed || progreso || entidades.length,
  );

  const copiar = async () => {
    if (!textoVisible) return;
    await navigator.clipboard?.writeText(textoVisible);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1400);
  };

  const hora = mensaje.creado
    ? new Intl.DateTimeFormat("es-PE", { hour: "2-digit", minute: "2-digit" }).format(mensaje.creado)
    : null;

  if (mensaje.cargando || (mensaje.streaming && !tieneContenidoStreaming)) {
    return (
      <div className="flex animate-fade-in items-center gap-3 text-muted">
        <img src="/logo-ulima.png" alt="" className="h-6 w-6 animate-girar object-contain" />
        <p className="text-sm font-medium">{mensaje.cargando ? "Preparando tu respuesta…" : etiquetaFase}</p>
      </div>
    );
  }

  if (esUsuario) {
    return (
      <div className="flex w-full animate-fade-in justify-end">
        <div className="max-w-[70%] rounded-[16px] rounded-br-[4px] bg-ulima px-4 py-3 text-[15px] leading-relaxed text-white shadow-sm">
          <p className="whitespace-pre-wrap">{texto}</p>
          {hora ? <time className="mt-1.5 block text-right text-[11px] text-white/70">{hora}</time> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full animate-fade-in justify-start gap-3">
      <BotAvatar />
      <article className="min-w-0 flex-1">
        {mensaje.streaming && (progreso || fase) ? (
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-muted" role="status">
            <span className="h-2 w-2 animate-pulse rounded-full bg-ulima" aria-hidden="true" />
            {progreso || etiquetaFase}
          </div>
        ) : null}
        {textoVisible || mensaje.streaming ? (
          <div className="space-y-3 text-[15.5px] leading-[1.65] text-ink">
            {renderRespuesta(textoVisible)}
            {mensaje.streaming ? (
              <span className="ml-0.5 inline-block animate-pulse text-ulima">▋</span>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <div className="mt-4 rounded-[10px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
            {detalle.text}
          </div>
        ) : null}

        {errorRed ? (
          <div className="mt-4 rounded-[10px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
            Error de conexión/API: {errorRed}
          </div>
        ) : null}

        <PanelRazonamiento
          cypher={cypher}
          entidades={entidades}
          error={error}
          errorRed={errorRed}
        />

        <div className="mt-3 flex items-center gap-2">
          {textoVisible ? (
            <button
              type="button"
              onClick={copiar}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-muted transition hover:bg-ash hover:text-ink focus:outline-none focus:ring-2 focus:ring-ulima/30"
              aria-label="Copiar respuesta"
            >
              {copiado ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
              {copiado ? "Copiado" : "Copiar"}
            </button>
          ) : null}
          {hora ? <time className="ml-auto text-[11px] text-muted">{hora}</time> : null}
        </div>
      </article>
    </div>
  );
}
