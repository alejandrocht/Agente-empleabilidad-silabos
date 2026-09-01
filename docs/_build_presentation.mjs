import fs from "node:fs/promises";
import path from "node:path";
import zlib from "node:zlib";

const OUT = path.resolve("docs/PRESENTACION_TECNICA_CIAR.pptx");
const W = 1280;
const H = 720;
const EMU = 9525;

const C = {
  orange: "FF5117",
  black: "111111",
  gray: "97999B",
  ink: "202124",
  white: "FAFAFA",
  paper: "F1F1F3",
  line: "E4E4E7",
  cyan: "00C5D6",
  amber: "FFA000",
  green: "00C78B",
  red: "D83A2E",
};

const esc = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&apos;");

const px = (value) => Math.round(value * EMU);
const attr = (name, value) => `${name}="${esc(value)}"`;

function xfrm(x, y, w, h) {
  return `<a:xfrm><a:off ${attr("x", px(x))} ${attr("y", px(y))}/><a:ext ${attr("cx", px(w))} ${attr("cy", px(h))}/></a:xfrm>`;
}

function fillXml(fill = "none") {
  if (fill === "none") return "<a:noFill/>";
  return `<a:solidFill><a:srgbClr ${attr("val", fill)}/></a:solidFill>`;
}

function lineXml(line = "none", width = 1) {
  if (line === "none") return "<a:ln><a:noFill/></a:ln>";
  return `<a:ln ${attr("w", Math.max(1, Math.round(width * 9525)))}>${fillXml(line)}</a:ln>`;
}

let shapeId = 1;
function shape({ x, y, w, h, fill = "none", line = "none", radius = false, name = "Shape" }) {
  const id = ++shapeId;
  const geom = radius ? "roundRect" : "rect";
  return `<p:sp><p:nvSpPr><p:cNvPr ${attr("id", id)} ${attr("name", name)}/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>${xfrm(x, y, w, h)}<a:prstGeom ${attr("prst", geom)}><a:avLst/></a:prstGeom>${fillXml(fill)}${lineXml(line)}</p:spPr></p:sp>`;
}

function textBox({ x, y, w, h, text = "", paragraphs, color = C.ink, size = 18, bold = false, font = "Roboto", align = "l", margin = 0, valign = "mid", italic = false, name = "Text" }) {
  const id = ++shapeId;
  const lines = paragraphs ?? String(text).split("\n").map((line) => ({ text: line }));
  const ps = lines.map((p) => {
    const pObj = typeof p === "string" ? { text: p } : p;
    const pText = pObj.text ?? "";
    const pColor = pObj.color ?? color;
    const pSize = pObj.size ?? size;
    const pBold = pObj.bold ?? bold;
    const pItalic = pObj.italic ?? italic;
    const bullet = pObj.bullet ? `<a:buChar ${attr("char", "•")}/>` : "<a:buNone/>";
    const level = pObj.level ?? 0;
    return `<a:p><a:pPr ${attr("algn", pObj.align ?? align)} ${attr("lvl", level)}>${bullet}</a:pPr><a:r><a:rPr ${attr("lang", "es-PE")} ${attr("sz", Math.round(pSize * 100))} ${attr("b", pBold ? 1 : 0)} ${attr("i", pItalic ? 1 : 0)}><a:solidFill><a:srgbClr ${attr("val", pColor)}/></a:solidFill><a:latin ${attr("typeface", pObj.font ?? font)}/></a:rPr><a:t>${esc(pText)}</a:t></a:r><a:endParaRPr ${attr("lang", "es-PE")} ${attr("sz", Math.round(pSize * 100))}/></a:p>`;
  }).join("");
  return `<p:sp><p:nvSpPr><p:cNvPr ${attr("id", id)} ${attr("name", name)}/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>${xfrm(x, y, w, h)}<a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr ${attr("lIns", margin)} ${attr("tIns", margin)} ${attr("rIns", margin)} ${attr("bIns", margin)} ${attr("anchor", valign)}/><a:lstStyle/>${ps}</p:txBody></p:sp>`;
}

function line(x1, y1, x2, y2, color = C.line, width = 1) {
  const id = ++shapeId;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length = Math.sqrt(dx * dx + dy * dy);
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;
  return `<p:sp><p:nvSpPr><p:cNvPr ${attr("id", id)} ${attr("name", "Rule")}/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm rot="${Math.round(angle * 60000)}"><a:off ${attr("x", px(x1))} ${attr("y", px(y1))}/><a:ext ${attr("cx", px(length))} ${attr("cy", px(width))}/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln ${attr("w", Math.max(1, Math.round(width * 9525)))}>${fillXml(color)}</a:ln></p:spPr></p:sp>`;
}

function dot(x, y, r, fill) {
  const id = ++shapeId;
  return `<p:sp><p:nvSpPr><p:cNvPr ${attr("id", id)} ${attr("name", "Dot")}/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>${xfrm(x - r, y - r, r * 2, r * 2)}<a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>${fillXml(fill)}<a:ln><a:noFill/></a:ln></p:spPr></p:sp>`;
}

function label(text, x, y, color = C.orange) {
  return textBox({ x, y, w: 240, h: 20, text: text.toUpperCase(), color, size: 11, bold: true, font: "IBM Plex Mono", valign: "mid" });
}

function title(text, subtitle = "") {
  const pieces = [textBox({ x: 72, y: 56, w: 1100, h: 54, text, color: C.black, size: 34, bold: true, font: "Roboto", valign: "mid", name: "Slide title" })];
  if (subtitle) pieces.push(textBox({ x: 74, y: 113, w: 980, h: 26, text: subtitle, color: C.gray, size: 15, font: "Roboto", valign: "mid" }));
  pieces.push(line(72, 150, 1208, 150, C.line, 1));
  return pieces.join("");
}

function footer(source) {
  return [
    line(72, 681, 1208, 681, C.line, 1),
    textBox({ x: 72, y: 688, w: 860, h: 15, text: `CIAR · estado técnico · 26.08.2026 · ${source}`, color: C.gray, size: 9, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 1130, y: 688, w: 78, h: 15, text: "ULIMA", color: C.orange, size: 10, bold: true, font: "Roboto", align: "r", valign: "mid" }),
  ].join("");
}

function slideBg() { return shape({ x: 0, y: 0, w: W, h: H, fill: C.white, line: "none", name: "Background" }); }

function card({ x, y, w, h, accent, kicker, heading, body, bodyColor = C.ink }) {
  return [
    shape({ x, y, w, h, fill: C.paper, line: "none", radius: true, name: "Card" }),
    shape({ x, y, w: 6, h, fill: accent, line: "none", name: "Accent" }),
    textBox({ x: x + 22, y: y + 18, w: w - 42, h: 17, text: kicker.toUpperCase(), color: accent, size: 11, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: x + 22, y: y + 43, w: w - 42, h: 33, text: heading, color: C.black, size: 21, bold: true, font: "Roboto", valign: "mid" }),
    textBox({ x: x + 22, y: y + 86, w: w - 42, h: h - 103, text: body, color: bodyColor, size: 15, font: "Roboto", valign: "top" }),
  ].join("");
}

function node({ x, y, w, h, text, accent = C.orange, dark = false }) {
  return [
    shape({ x, y, w, h, fill: dark ? C.black : C.paper, line: "none", radius: true, name: "Architecture node" }),
    shape({ x, y, w: 5, h, fill: accent, line: "none", name: "Node accent" }),
    textBox({ x: x + 14, y: y + 2, w: w - 22, h: h - 4, text, color: dark ? C.white : C.black, size: 14, bold: true, font: "Roboto", valign: "mid" }),
  ].join("");
}

function arrow(x1, y1, x2, y2, color = C.gray) {
  return [line(x1, y1, x2, y2, color, 2), dot(x2, y2, 4, color)].join("");
}

function slide1() {
  return [
    slideBg(),
    shape({ x: 0, y: 0, w: 18, h: H, fill: C.orange, line: "none" }),
    textBox({ x: 72, y: 82, w: 300, h: 28, text: "CIAR / ULIMA", color: C.orange, size: 15, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 72, y: 178, w: 950, h: 92, text: "Estado técnico\nactual", color: C.black, size: 48, bold: true, font: "Roboto", valign: "top" }),
    textBox({ x: 76, y: 306, w: 720, h: 58, text: "Agente de empleabilidad, dashboard y normalización curricular", color: C.ink, size: 24, font: "Lusitana", valign: "top" }),
    line(76, 422, 480, 422, C.orange, 4),
    textBox({ x: 76, y: 446, w: 560, h: 30, text: "Informe y presentación técnica", color: C.gray, size: 18, font: "Roboto", valign: "mid" }),
    textBox({ x: 76, y: 498, w: 560, h: 27, text: "Corte de evidencia · 26 de agosto de 2026", color: C.gray, size: 15, font: "IBM Plex Mono", valign: "mid" }),
    shape({ x: 892, y: 164, w: 278, h: 278, fill: C.black, line: "none", radius: true }),
    textBox({ x: 930, y: 196, w: 200, h: 52, text: "12", color: C.orange, size: 45, bold: true, font: "Roboto", align: "c", valign: "mid" }),
    textBox({ x: 930, y: 258, w: 200, h: 26, text: "nodos lógicos", color: C.white, size: 16, font: "Roboto", align: "c", valign: "mid" }),
    line(942, 319, 1120, 319, C.gray, 1),
    textBox({ x: 930, y: 342, w: 200, h: 48, text: "606", color: C.white, size: 36, bold: true, font: "Roboto", align: "c", valign: "mid" }),
    textBox({ x: 930, y: 398, w: 200, h: 20, text: "tests backend passed", color: C.gray, size: 13, font: "Roboto", align: "c", valign: "mid" }),
    footer("fuente: código y verificaciones locales"),
  ].join("");
}

function slide2() {
  return [
    slideBg(), title("La base funcional está lista; el siguiente salto es productizar", "Lectura ejecutiva del estado del repositorio"),
    textBox({ x: 74, y: 181, w: 720, h: 55, text: "CIAR ya tiene un núcleo consultable, controlado y probado en local. La brecha principal está en la operación real, no en añadir más complejidad al grafo.", color: C.black, size: 25, bold: true, font: "Lusitana", valign: "top" }),
    card({ x: 74, y: 302, w: 350, h: 210, accent: C.green, kicker: "Núcleo", heading: "Controlado", body: "Schema vivo, generación parametrizada, resolución de entidades, guardia final y gateway Neo4j READ." }),
    card({ x: 465, y: 302, w: 350, h: 210, accent: C.cyan, kicker: "Producto", heading: "Parcial", body: "Dashboard y normalizador tienen contratos claros; 7 datasets están activos y 5 permanecen diferidos." }),
    card({ x: 856, y: 302, w: 350, h: 210, accent: C.amber, kicker: "Operación", heading: "Pendiente", body: "Falta aceptación end-to-end con servicios reales, auth, rate limiting, CI/CD y pruebas de resiliencia." }),
    footer("fuente: constructor.py, servidor.py, PLAN_DASHBOARD_TENDENCIAS.md"),
  ].join("");
}

function slide3() {
  return [
    slideBg(), title("Dos planos, una frontera de datos", "La consulta está aislada de la curación y publicación"),
    textBox({ x: 75, y: 180, w: 230, h: 22, text: "PLANO DE CONSULTA", color: C.orange, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    node({ x: 74, y: 232, w: 180, h: 56, text: "Next.js / React", accent: C.orange }),
    node({ x: 304, y: 232, w: 180, h: 56, text: "FastAPI", accent: C.orange }),
    node({ x: 534, y: 232, w: 180, h: 56, text: "LangGraph", accent: C.orange, dark: true }),
    node({ x: 764, y: 232, w: 180, h: 56, text: "OpenAI", accent: C.cyan }),
    node({ x: 994, y: 232, w: 190, h: 56, text: "Neo4j · READ", accent: C.green, dark: true }),
    arrow(254, 260, 304, 260), arrow(484, 260, 534, 260), arrow(714, 260, 764, 260), arrow(944, 260, 994, 260),
    line(74, 330, 1204, 330, C.line, 1),
    textBox({ x: 75, y: 362, w: 280, h: 22, text: "PLANO DE CURACIÓN", color: C.cyan, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    node({ x: 74, y: 416, w: 190, h: 56, text: "Carga documental", accent: C.cyan }),
    node({ x: 320, y: 416, w: 190, h: 56, text: "Normalizador", accent: C.cyan }),
    node({ x: 566, y: 416, w: 190, h: 56, text: "Evidencia + revisión", accent: C.amber }),
    node({ x: 812, y: 416, w: 190, h: 56, text: "Release gate", accent: C.amber, dark: true }),
    node({ x: 1058, y: 416, w: 126, h: 56, text: "Import", accent: C.green, dark: true }),
    arrow(264, 444, 320, 444, C.cyan), arrow(510, 444, 566, 444, C.cyan), arrow(756, 444, 812, 444, C.amber), arrow(1002, 444, 1058, 444, C.green),
    textBox({ x: 74, y: 555, w: 1100, h: 44, text: "La escritura no comparte el camino de consulta: requiere artefactos, decisión humana y credenciales NEO4J_INGEST_*.", color: C.ink, size: 18, font: "Lusitana", valign: "mid" }),
    footer("fuente: servidor.py, constructor.py, normalizador y neo4j_importacion.py"),
  ].join("");
}

function slide4() {
  return [
    slideBg(), title("El agente vigente es un flujo directo de 12 nodos lógicos", "El routing decide el tipo de respuesta antes de consultar el grafo"),
    textBox({ x: 74, y: 181, w: 1120, h: 32, text: "Entrada → dos puertas de seguridad → routing determinista → ruta conversacional o Cypher → memoria corta", color: C.black, size: 22, bold: true, font: "Lusitana", valign: "mid" }),
    node({ x: 74, y: 270, w: 165, h: 52, text: "Pregunta", accent: C.orange }),
    node({ x: 268, y: 270, w: 165, h: 52, text: "Prompt guards ×2", accent: C.red }),
    node({ x: 462, y: 270, w: 165, h: 52, text: "Orquestador", accent: C.orange, dark: true }),
    node({ x: 696, y: 226, w: 180, h: 52, text: "Conversación", accent: C.cyan }),
    node({ x: 696, y: 314, w: 180, h: 52, text: "Cypher", accent: C.green }),
    node({ x: 935, y: 314, w: 180, h: 52, text: "Respuesta", accent: C.green, dark: true }),
    node({ x: 935, y: 226, w: 180, h: 52, text: "Respuesta directa", accent: C.cyan, dark: true }),
    node({ x: 1146, y: 270, w: 72, h: 52, text: "Memoria", accent: C.amber }),
    arrow(239, 296, 268, 296), arrow(433, 296, 462, 296), arrow(627, 296, 696, 252), arrow(627, 296, 696, 340), arrow(876, 252, 935, 252, C.cyan), arrow(876, 340, 935, 340, C.green), arrow(1115, 252, 1146, 296), arrow(1115, 340, 1146, 296),
    textBox({ x: 75, y: 450, w: 500, h: 98, text: "No es el antiguo camino de 20 plantillas + planificador.\n\nEsos módulos aparecen en documentación o tests históricos, pero no se registran en el constructor activo.", color: C.ink, size: 17, font: "Roboto", valign: "top" }),
    card({ x: 690, y: 452, w: 485, h: 102, accent: C.amber, kicker: "Estado", heading: "Memoria corta local", body: "TTL 30 min · 4 turnos/scope · sin checkpointer durable." }),
    footer("fuente: agente/grafo/constructor.py, orquestador.py, memoria_corta.py"),
  ].join("");
}

function slide5() {
  return [
    slideBg(), title("La confianza se construye en cadena, no en un único prompt", "Cada etapa reduce el espacio de comportamiento permitido"),
    textBox({ x: 75, y: 181, w: 1130, h: 33, text: "Una pregunta de datos solo alcanza Neo4j cuando supera cinco controles encadenados.", color: C.black, size: 23, bold: true, font: "Lusitana", valign: "mid" }),
    ...[
      ["01", "Schema vivo", "Neo4j define etiquetas, propiedades y relaciones; el snapshot se cachea con TTL."],
      ["02", "Generación", "OpenAI devuelve Cypher estructurado y parametrizado, con hasta dos intentos."],
      ["03", "Entidades", "Se validan IDs canónicos, cardinalidad y reconciliación de valores confiables."],
      ["04", "Guardia final", "Fail-closed: sin escrituras, sin procedimientos, sin retornos completos, límite 1–100."],
      ["05", "Gateway READ", "EXPLAIN + ejecución con RoutingControl.READ, warnings revisados y respuesta normalizada."],
    ].map(([n, h, b], i) => {
      const y = 266 + i * 72;
      return [
        dot(102, y + 25, 24, i === 4 ? C.green : C.orange),
        textBox({ x: 82, y: y + 7, w: 40, h: 30, text: n, color: C.white, size: 12, bold: true, font: "IBM Plex Mono", align: "c", valign: "mid" }),
        textBox({ x: 150, y, w: 230, h: 30, text: h, color: C.black, size: 19, bold: true, font: "Roboto", valign: "mid" }),
        textBox({ x: 390, y, w: 760, h: 46, text: b, color: C.ink, size: 16, font: "Roboto", valign: "mid" }),
        i < 4 ? line(102, y + 50, 102, y + 72, C.line, 2) : "",
      ].join("");
    }),
    textBox({ x: 75, y: 637, w: 1100, h: 26, text: "Hito relevante: el commit 4c24bc0 reemplazó etiquetas hardcodeadas por schema vivo.", color: C.orange, size: 14, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    footer("fuente: neo4j_schema.py, construye_cypher.py, cypher_guard.py, utils/db.py"),
  ].join("");
}

function slide6() {
  return [
    slideBg(), title("El dashboard ya tiene un núcleo útil y mantiene límites semánticos", "7 datasets activos; 5 diferidos sin fabricar resultados"),
    textBox({ x: 74, y: 183, w: 520, h: 30, text: "ACTIVOS", color: C.green, size: 13, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    ["Tendencia de ofertas", "Demanda por carrera", "Industrias por carrera", "Conocimientos demandados", "Cobertura curricular", "Brechas de demanda alta", "Empresas y conocimientos"].map((t, i) => {
      const x = 74 + (i % 2) * 270;
      const y = 235 + Math.floor(i / 2) * 55;
      return [dot(x + 8, y + 14, 5, C.green), textBox({ x: x + 24, y, w: 235, h: 28, text: t, color: C.ink, size: 15, font: "Roboto", valign: "mid" })].join("");
    }).join(""),
    textBox({ x: 74, y: 451, w: 520, h: 28, text: "DIFERIDOS", color: C.amber, size: 13, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 74, y: 492, w: 520, h: 90, text: "Vigencia · correspondencia curso-oferta · diferenciadores de empresas · liderazgo · funciones por tipo de empresa", color: C.ink, size: 16, font: "Roboto", valign: "top" }),
    shape({ x: 690, y: 202, w: 500, h: 376, fill: C.black, line: "none", radius: true }),
    textBox({ x: 724, y: 236, w: 420, h: 30, text: "QUÉ MIDE", color: C.cyan, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 724, y: 278, w: 410, h: 92, text: "Publicaciones laborales, empresas publicadoras, industrias, requisitos declarados y cobertura curricular declarada.", color: C.white, size: 21, font: "Lusitana", valign: "top" }),
    line(724, 399, 1146, 399, C.gray, 1),
    textBox({ x: 724, y: 424, w: 420, h: 24, text: "QUÉ NO MIDE", color: C.orange, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 724, y: 461, w: 420, h: 76, text: "No prueba contratación, empleo efectivo, dominio del estudiante, tamaño empresarial ni causalidad.", color: C.white, size: 18, font: "Roboto", valign: "top" }),
    footer("fuente: PLAN_DASHBOARD_TENDENCIAS.md, dashboard/consultas.py, frontend/src/components/Dashboard.jsx"),
  ].join("");
}

function slide7() {
  return [
    slideBg(), title("El normalizador convierte documentos en evidencia publicable", "La publicación es un proceso con revisión y release gate"),
    textBox({ x: 74, y: 182, w: 1140, h: 30, text: "Fuente → extracción → análisis → evidencia → decisión → importación", color: C.black, size: 23, bold: true, font: "Lusitana", valign: "mid" }),
    node({ x: 74, y: 260, w: 150, h: 62, text: "XLSX / DOCX\nPDF / ZIP", accent: C.cyan }),
    node({ x: 260, y: 260, w: 150, h: 62, text: "Validación\nacotada", accent: C.cyan }),
    node({ x: 446, y: 260, w: 150, h: 62, text: "LLM + reglas\ndeterministas", accent: C.orange }),
    node({ x: 632, y: 260, w: 150, h: 62, text: "Evidencia +\nproveniencia", accent: C.green }),
    node({ x: 818, y: 260, w: 150, h: 62, text: "Pendientes +\ncuarentena", accent: C.amber }),
    node({ x: 1004, y: 260, w: 180, h: 62, text: "ALLOW_IMPORT", accent: C.green, dark: true }),
    arrow(224, 291, 260, 291, C.cyan), arrow(410, 291, 446, 291, C.cyan), arrow(596, 291, 632, 291, C.orange), arrow(782, 291, 818, 291, C.green), arrow(968, 291, 1004, 291, C.amber),
    textBox({ x: 74, y: 405, w: 500, h: 24, text: "SALIDAS CANÓNICAS", color: C.green, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 74, y: 444, w: 510, h: 115, text: "4 CSV: competencias, habilidades, herramientas y cobertura curricular.\n\nJSONL de evidencia, pendientes, decisiones, candidatos y release gate.", color: C.ink, size: 17, font: "Roboto", valign: "top" }),
    textBox({ x: 690, y: 405, w: 500, h: 24, text: "REGLAS DE PUBLICACIÓN", color: C.amber, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 690, y: 444, w: 500, h: 115, text: "Duplicado exacto: deduplicación determinista.\nSemántico/sospechoso: revisión humana.\nEmbeddings: opt-in, por carrera@periodo, solo sugerencias.", color: C.ink, size: 17, font: "Roboto", valign: "top" }),
    footer("fuente: normalizador, README backend, release_gate y neo4j_importacion.py"),
  ].join("");
}

function slide8() {
  return [
    slideBg(), title("La calidad analítica depende también de no sobreinterpretar el grafo", "El contrato semántico es parte de la arquitectura"),
    card({ x: 74, y: 208, w: 350, h: 300, accent: C.green, kicker: "Sí permite", heading: "Observar patrones", body: "• contar ofertas publicadas\n• rankear carreras, empresas e industrias\n• identificar requisitos declarados\n• comparar cobertura curricular declarada\n• responder sobre entidades y relaciones existentes" }),
    card({ x: 465, y: 208, w: 350, h: 300, accent: C.amber, kicker: "Requiere cuidado", heading: "Interpretar señales", body: "• una oferta puede dirigirse a varias carreras\n• los porcentajes no suman necesariamente 100 %\n• una tabla vacía puede ser falta de cobertura\n• un título publicado no es una función normalizada\n• la cobertura no mide profundidad" }),
    card({ x: 856, y: 208, w: 350, h: 300, accent: C.orange, kicker: "No permite", heading: "Afirmar causalidad", body: "• empleo efectivo o contratación\n• inserción de egresados\n• dominio personal del estudiante\n• tamaño empresarial\n• funciones laborales normalizadas\n• relaciones no presentes en Neo4j" }),
    textBox({ x: 75, y: 570, w: 1100, h: 42, text: "La ausencia de datos no se convierte automáticamente en cero. Cada vista debe conservar denominadores, disponibilidad y advertencias.", color: C.black, size: 20, bold: true, font: "Lusitana", valign: "mid" }),
    footer("fuente: PLAN_DASHBOARD_TENDENCIAS.md, QUERIES_EJEMPLO_NEO4J.md"),
  ].join("");
}

function slide9() {
  return [
    slideBg(), title("El avance por fases muestra un núcleo maduro y una última milla abierta", "Lectura acumulada del historial Git, plan y código vigente"),
    textBox({ x: 74, y: 181, w: 1140, h: 28, text: "COMPLETADO / IMPLEMENTADO", color: C.green, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    [["0", "Base y paquete activo"], ["1", "OpenAI por rol"], ["2", "Seguridad + observabilidad"], ["3", "Orquestación CIAR"], ["5", "Normalizador empleabilidad"]].map(([n, t], i) => {
      const x = 74 + i * 225;
      return [shape({ x, y: 230, w: 198, h: 88, fill: C.paper, line: "none", radius: true }), dot(x + 24, 254, 13, C.green), textBox({ x: x + 15, y: 242, w: 18, h: 22, text: n, color: C.white, size: 11, bold: true, font: "IBM Plex Mono", align: "c", valign: "mid" }), textBox({ x: x + 50, y: 242, w: 135, h: 44, text: t, color: C.black, size: 15, bold: true, font: "Roboto", valign: "mid" })].join("");
    }).join(""),
    textBox({ x: 74, y: 382, w: 1140, h: 28, text: "PARCIAL / EN PROGRESO", color: C.amber, size: 12, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    [["4", "Dashboard: 7 activos / 5 diferidos"], ["6", "Sílabos + revisión + embeddings"], ["7", "Importación con release gate"], ["8", "Productización y aceptación live"]].map(([n, t], i) => {
      const x = 74 + i * 280;
      return [shape({ x, y: 431, w: 252, h: 92, fill: "FFF4E6", line: "none", radius: true }), dot(x + 24, 456, 13, C.amber), textBox({ x: x + 15, y: 444, w: 18, h: 22, text: n, color: C.white, size: 11, bold: true, font: "IBM Plex Mono", align: "c", valign: "mid" }), textBox({ x: x + 50, y: 443, w: 184, h: 54, text: t, color: C.black, size: 15, bold: true, font: "Roboto", valign: "mid" })].join("");
    }).join(""),
    textBox({ x: 74, y: 585, w: 1140, h: 35, text: "El criterio de cierre es operacional: servicios reales, seguridad de frontera, despliegue reproducible y documentación reconciliada.", color: C.black, size: 19, bold: true, font: "Lusitana", valign: "mid" }),
    footer("fuente: historial Git hasta 4c24bc0, docs/plan_implementacion.md, código vigente"),
  ].join("");
}

function slide10() {
  return [
    slideBg(), title("La calidad local es alta; la aceptación con infraestructura real sigue pendiente", "Resultados reproducibles del corte técnico"),
    textBox({ x: 74, y: 185, w: 250, h: 28, text: "PASÓ", color: C.green, size: 13, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    card({ x: 74, y: 230, w: 240, h: 170, accent: C.green, kicker: "Backend", heading: "606 passed", body: "9 skips intencionales de módulos históricos retirados." }),
    card({ x: 340, y: 230, w: 240, h: 170, accent: C.green, kicker: "Frontend", heading: "54 tests", body: "10 archivos Vitest + build Next exitoso." }),
    card({ x: 606, y: 230, w: 240, h: 170, accent: C.green, kicker: "Tooling", heading: "Ruff OK", body: "Compilación Python también verificada." }),
    card({ x: 872, y: 230, w: 240, h: 170, accent: C.green, kicker: "Dependencias", heading: "0 vulns", body: "npm audit offline --omit=dev." }),
    textBox({ x: 74, y: 458, w: 250, h: 28, text: "AÚN NO CERRADO", color: C.amber, size: 13, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 74, y: 504, w: 1030, h: 64, text: "mypy: 3 errores pendientes · aceptación live Neo4j/OpenAI no ejecutada · no hay prueba registrada de carga, despliegue, recuperación ni e2e contra servicios externos", color: C.black, size: 23, bold: true, font: "Lusitana", valign: "top" }),
    footer("fuente: pytest, Ruff, mypy, compileall, npm run check, npm audit offline"),
  ].join("");
}

function slide11() {
  return [
    slideBg(), title("Tres frentes concentran el riesgo inmediato", "Prioridades técnicas para pasar de pre-productivo a operable"),
    card({ x: 74, y: 215, w: 350, h: 290, accent: C.red, kicker: "01 · Alta", heading: "Aceptar en vivo", body: "Ejecutar preguntas de aceptación contra Neo4j real; revisar schema, tiempos, warnings, errores y respuestas. Repetir con dashboard." }),
    card({ x: 465, y: 215, w: 350, h: 290, accent: C.orange, kicker: "02 · Alta", heading: "Proteger la frontera", body: "Definir autenticación, autorización, rate limiting, concurrencia, secretos y estrategia de identidad compartida." }),
    card({ x: 856, y: 215, w: 350, h: 290, accent: C.amber, kicker: "03 · Media", heading: "Reconciliar la historia", body: "Marcar como históricos los documentos de planner/20 plantillas/memoria durable y corregir referencias a rutas eliminadas." }),
    textBox({ x: 74, y: 567, w: 1130, h: 40, text: "La próxima iteración debe reducir incertidumbre operativa, no aumentar superficie funcional sin aceptación.", color: C.black, size: 21, bold: true, font: "Lusitana", valign: "mid" }),
    footer("fuente: informe técnico consolidado y evidencia del repositorio"),
  ].join("");
}

function slide12() {
  return [
    slideBg(),
    shape({ x: 0, y: 0, w: 18, h: H, fill: C.orange, line: "none" }),
    textBox({ x: 74, y: 78, w: 320, h: 25, text: "CIAR · CIERRE TÉCNICO", color: C.orange, size: 13, bold: true, font: "IBM Plex Mono", valign: "mid" }),
    textBox({ x: 74, y: 184, w: 930, h: 84, text: "Siguiente hito:\naceptación end-to-end", color: C.black, size: 43, bold: true, font: "Roboto", valign: "top" }),
    textBox({ x: 78, y: 322, w: 760, h: 50, text: "Con datos reales, controles de frontera y una documentación reconciliada con el código.", color: C.ink, size: 24, font: "Lusitana", valign: "top" }),
    line(78, 424, 500, 424, C.orange, 4),
    ["pregunta real contra Neo4j", "prueba de schema y guardia", "verificación de dashboard", "runbook de operación y rollback"].map((t, i) => {
      const y = 472 + i * 34;
      return [dot(89, y + 10, 5, C.green), textBox({ x: 108, y, w: 500, h: 22, text: t, color: C.ink, size: 16, font: "Roboto", valign: "mid" })].join("");
    }).join(""),
    shape({ x: 900, y: 188, w: 250, h: 250, fill: C.black, line: "none", radius: true }),
    textBox({ x: 932, y: 226, w: 186, h: 35, text: "CIAR", color: C.orange, size: 28, bold: true, font: "Roboto", align: "c", valign: "mid" }),
    textBox({ x: 932, y: 286, w: 186, h: 98, text: "consulta\ncuración\ncriterio", color: C.white, size: 25, bold: true, font: "Lusitana", align: "c", valign: "mid" }),
    footer("fuente: informe técnico consolidado"),
  ].join("");
}

const slideBodies = [slide1, slide2, slide3, slide4, slide5, slide6, slide7, slide8, slide9, slide10, slide11, slide12];

const NS = {
  a: "http://schemas.openxmlformats.org/drawingml/2006/main",
  p: "http://schemas.openxmlformats.org/presentationml/2006/main",
  r: "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
};

function xmlHeader(body, extra = "") { return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>${body}`; }

function slideXml(body) {
  return xmlHeader(`<p:sld xmlns:a="${NS.a}" xmlns:r="${NS.r}" xmlns:p="${NS.p}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>${xfrm(0, 0, W, H)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:grpSpPr>${body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`);
}

function presentationXml() {
  const ids = slideBodies.map((_, i) => `<p:sldId ${attr("id", 256 + i)} ${attr("r:id", `rId${i + 2}`)}/>`).join("");
  return xmlHeader(`<p:presentation xmlns:a="${NS.a}" xmlns:r="${NS.r}" xmlns:p="${NS.p}" ${attr("saveSubsetFonts", 1)}><p:sldMasterIdLst><p:sldMasterId ${attr("id", 2147483648)} ${attr("r:id", "rId1")}/></p:sldMasterIdLst><p:sldIdLst>${ids}</p:sldIdLst><p:sldSz ${attr("cx", 12192000)} ${attr("cy", 6858000)}/><p:notesSz ${attr("cx", 6858000)} ${attr("cy", 9144000)}/><p:defaultTextStyle><a:defPPr/><a:lvl1pPr marL="0" algn="l"/><a:lvl2pPr marL="0" algn="l"/><a:lvl3pPr marL="0" algn="l"/></p:defaultTextStyle></p:presentation>`);
}

const files = new Map();
function add(name, content) { files.set(name, Buffer.from(content, "utf8")); }

function addPackage() {
  add("[Content_Types].xml", xmlHeader(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/><Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/><Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>${slideBodies.map((_, i) => `<Override PartName="/ppt/slides/slide${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`).join("")}</Types>`));
  add("_rels/.rels", xmlHeader(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>`));
  add("ppt/presentation.xml", presentationXml());
  add("ppt/_rels/presentation.xml.rels", xmlHeader(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>${slideBodies.map((_, i) => `<Relationship Id="rId${i + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide${i + 1}.xml"/>`).join("")}</Relationships>`));
  add("ppt/slideMasters/slideMaster1.xml", xmlHeader(`<p:sldMaster xmlns:a="${NS.a}" xmlns:r="${NS.r}" xmlns:p="${NS.p}"><p:cSld name="CIAR"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>${xfrm(0, 0, W, H)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId ${attr("id", 1)} ${attr("r:id", "rId1")}/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>`));
  add("ppt/slideMasters/_rels/slideMaster1.xml.rels", xmlHeader(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>`));
  add("ppt/slideLayouts/slideLayout1.xml", xmlHeader(`<p:sldLayout xmlns:a="${NS.a}" xmlns:r="${NS.r}" xmlns:p="${NS.p}" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>${xfrm(0, 0, W, H)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>`));
  add("ppt/slideLayouts/_rels/slideLayout1.xml.rels", xmlHeader(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>`));
  add("ppt/theme/theme1.xml", xmlHeader(`<a:theme xmlns:a="${NS.a}" name="CIAR"><a:themeElements><a:clrScheme name="CIAR"><a:dk1><a:srgbClr val="111111"/></a:dk1><a:lt1><a:srgbClr val="FAFAFA"/></a:lt1><a:dk2><a:srgbClr val="202124"/></a:dk2><a:lt2><a:srgbClr val="F1F1F3"/></a:lt2><a:accent1><a:srgbClr val="FF5117"/></a:accent1><a:accent2><a:srgbClr val="00C5D6"/></a:accent2><a:accent3><a:srgbClr val="00C78B"/></a:accent3><a:accent4><a:srgbClr val="FFA000"/></a:accent4><a:accent5><a:srgbClr val="97999B"/></a:accent5><a:accent6><a:srgbClr val="E4E4E7"/></a:accent6><a:hlink><a:srgbClr val="00C5D6"/></a:hlink><a:folHlink><a:srgbClr val="FF5117"/></a:folHlink></a:clrScheme><a:fontScheme name="CIAR"><a:majorFont><a:latin typeface="Roboto"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Roboto"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="CIAR"><a:fillStyleLst><a:solidFill><a:srgbClr val="FAFAFA"/></a:solidFill></a:fillStyleLst><a:lnStyleLst><a:ln w="9525"><a:solidFill><a:srgbClr val="E4E4E7"/></a:solidFill></a:ln></a:lnStyleLst><a:effectStyleLst/><a:bgFillStyleLst/></a:fmtScheme></a:themeElements></a:theme>`));
  slideBodies.forEach((make, i) => {
    const body = make();
    add(`ppt/slides/slide${i + 1}.xml`, slideXml(body));
    add(`ppt/slides/_rels/slide${i + 1}.xml.rels`, xmlHeader(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/></Relationships>`));
  });
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function u16(value) { const b = Buffer.alloc(2); b.writeUInt16LE(value); return b; }
function u32(value) { const b = Buffer.alloc(4); b.writeUInt32LE(value >>> 0); return b; }

function zip(entries) {
  const list = entries instanceof Map ? [...entries] : entries;
  const local = [];
  const central = [];
  let offset = 0;
  for (const [name, raw] of list) {
    const data = zlib.deflateRawSync(raw, { level: 6 });
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(raw);
    const header = Buffer.concat([Buffer.from("PK\x03\x04", "binary"), u16(20), u16(0), u16(8), u16(0), u16(0), u32(crc), u32(data.length), u32(raw.length), u16(nameBuf.length), u16(0), nameBuf, data]);
    local.push(header);
    const dir = Buffer.concat([Buffer.from("PK\x01\x02", "binary"), u16(20), u16(20), u16(0), u16(8), u16(0), u16(0), u32(crc), u32(data.length), u32(raw.length), u16(nameBuf.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(offset), nameBuf]);
    central.push(dir);
    offset += header.length;
  }
  const centralData = Buffer.concat(central);
  const end = Buffer.concat([Buffer.from("PK\x05\x06", "binary"), u16(0), u16(0), u16(list.length), u16(list.length), u32(centralData.length), u32(offset), u16(0)]);
  return Buffer.concat([...local, centralData, end]);
}

addPackage();
await fs.writeFile(OUT, zip(files));
console.log(`Wrote ${OUT} (${files.size} parts, ${slideBodies.length} slides)`);
