"use client";

import BotAvatar from "./components/BotAvatar";
import ChatWindow from "./components/ChatWindow";
import Sidebar from "./components/Sidebar";
import { useConversaciones } from "./hooks/useConversaciones";

export default function App() {
  const conversaciones = useConversaciones();

  return (
    <main className="app-bg min-h-screen text-ink">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <Sidebar {...conversaciones} />
        <section className="flex min-h-screen flex-1 flex-col">
          <header className="border-b border-line bg-white px-5 py-4">
            <div className="mx-auto flex w-full max-w-5xl items-center gap-3">
              <BotAvatar />
              <div>
                <h1 className="text-2xl font-extrabold tracking-tight">Agente Ciar</h1>
                <p className="text-sm text-muted">Consulta académica y empleabilidad con Neo4j</p>
              </div>
            </div>
          </header>
          <ChatWindow
            conversacion={conversaciones.activa}
            agregarMensaje={conversaciones.agregarMensaje}
          />
        </section>
      </div>
    </main>
  );
}
