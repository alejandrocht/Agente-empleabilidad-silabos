"use client";

import { useState } from "react";
import ChatWindow from "./components/ChatWindow";
import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import { useConversaciones } from "./hooks/useConversaciones";

export default function App() {
  const conversaciones = useConversaciones();
  const [menuAbierto, setMenuAbierto] = useState(false);
  const [sidebarVisible, setSidebarVisible] = useState(true);

  const alternarMenu = () => {
    if (window.innerWidth >= 1024) {
      setSidebarVisible((valor) => !valor);
    } else {
      setMenuAbierto(true);
    }
  };

  return (
    <main className="app-bg h-[100dvh] overflow-hidden text-ink">
      <div className="flex h-full overflow-hidden">
        {menuAbierto ? (
          <button
            type="button"
            aria-label="Cerrar menú"
            className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[2px] lg:hidden"
            onClick={() => setMenuAbierto(false)}
          />
        ) : null}

        <Sidebar
          {...conversaciones}
          abierto={menuAbierto}
          visible={sidebarVisible}
          onCerrar={() => setMenuAbierto(false)}
          onAlternar={alternarMenu}
        />

        <section className="flex min-w-0 flex-1 flex-col">
          <Topbar
            conversacion={conversaciones.activa}
            onAbrirMenu={alternarMenu}
          />
          <ChatWindow
            conversacion={conversaciones.activa}
            agregarMensaje={conversaciones.agregarMensaje}
          />
        </section>
      </div>
    </main>
  );
}
