import "./globals.css";

export const metadata = {
  title: "Agente CIAR",
  description: "Interfaz web para consultar el agente CIAR sobre Neo4j.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
