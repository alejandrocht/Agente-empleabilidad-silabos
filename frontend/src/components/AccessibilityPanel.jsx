"use client";

import { useEffect, useState } from "react";
import {
  Accessibility,
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  AudioLines,
  BookOpen,
  CircleDashed,
  Droplets,
  Ear,
  Eye,
  EyeOff,
  FileText,
  Focus,
  Hand,
  ImageOff,
  Keyboard,
  Link2,
  Moon,
  MousePointer2,
  RotateCcw,
  ScanLine,
  Sun,
  Type,
  Underline,
  VolumeX,
  X,
  ZapOff,
  ZoomIn,
} from "lucide-react";

const STORAGE_KEY = "ciar-accessibility-settings";
const COLOR_OPTIONS = ["#087fb8", "#7953a6", "#d33333", "#d97717", "#249ba7", "#4c7c2e", "#ffffff", "#000000"];

const DEFAULT_SETTINGS = {
  contentScale: 100,
  fontSize: 16,
  lineHeight: "default",
  letterSpacing: "default",
  readableFont: false,
  emphasizeTitles: false,
  underlineLinks: false,
  magnifier: false,
  alignment: "default",
  contrast: "default",
  saturation: "default",
  textColor: "",
  titleColor: "",
  backgroundColor: "",
  muteSounds: false,
  hideImages: false,
  readingMode: false,
  readingGuide: false,
  stopAnimations: false,
  readingMask: false,
  hoverHighlight: false,
  focusHighlight: false,
  cursor: "default",
  keyboardNavigation: false,
  screenReader: false,
};

const PROFILES = [
  { id: "seizures", label: "Seguridad ante convulsiones", description: "Reduce el movimiento y los desencadenantes visuales", Icon: ZapOff, changes: { stopAnimations: true } },
  { id: "lowVision", label: "Soporte para baja visión", description: "Mejora claridad y contraste", Icon: Eye, changes: { contentScale: 110, fontSize: 18, readableFont: true, contrast: "high", focusHighlight: true } },
  { id: "adhd", label: "Amigable con el TDAH", description: "Apoya la concentración y reduce distracciones", Icon: ScanLine, changes: { stopAnimations: true, readingMode: true, readingGuide: true } },
  { id: "cognitive", label: "Apoyo a la lectura y cognitivo", description: "Simplifica la lectura y la navegación", Icon: Focus, changes: { readableFont: true, emphasizeTitles: true, lineHeight: "relaxed" } },
  { id: "keyboard", label: "Navegación por teclado", description: "Resalta los controles navegables", Icon: Keyboard, changes: { keyboardNavigation: true, focusHighlight: true } },
  { id: "screenReader", label: "Compatibilidad con lector de pantalla", description: "Optimiza los anuncios y el enfoque", Icon: AudioLines, changes: { screenReader: true, keyboardNavigation: true } },
  { id: "seniors", label: "Personas mayores", description: "Mejora la visibilidad y el confort de lectura", Icon: Ear, changes: { contentScale: 110, fontSize: 18, readableFont: true, lineHeight: "relaxed", contrast: "high" } },
];

function getSavedSettings() {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function profileIsEnabled(settings, changes) {
  return Object.entries(changes).every(([key, value]) => settings[key] === value);
}

function A11yCard({ Icon, label, active, onClick, children }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`a11y-card ${active ? "a11y-card-active" : ""}`}
    >
      <Icon aria-hidden="true" size={29} strokeWidth={2.15} />
      <span>{label}</span>
      {children}
    </button>
  );
}

function SteppedControl({ Icon, label, value, onDecrease, onIncrease }) {
  return (
    <div className="a11y-stepped-control">
      <p><Icon aria-hidden="true" size={25} />{label}</p>
      <div>
        <button type="button" onClick={onDecrease} aria-label={`Reducir ${label}`}>⌄</button>
        <output aria-live="polite">{value}</output>
        <button type="button" onClick={onIncrease} aria-label={`Aumentar ${label}`}>⌃</button>
      </div>
    </div>
  );
}

function ColorControl({ label, value, onChange }) {
  return (
    <div className="a11y-color-control">
      <p>{label}</p>
      <div role="group" aria-label={label}>
        {COLOR_OPTIONS.map((color) => (
          <button
            type="button"
            key={color}
            aria-label={`Usar color ${color}`}
            aria-pressed={value === color}
            className={value === color ? "selected" : ""}
            style={{ backgroundColor: color }}
            onClick={() => onChange(value === color ? "" : color)}
          />
        ))}
      </div>
      <button type="button" className="a11y-cancel" onClick={() => onChange("")}>Restablecer</button>
    </div>
  );
}

export default function AccessibilityPanel() {
  const [settings, setSettings] = useState(getSavedSettings);
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [showStatement, setShowStatement] = useState(false);
  const [guideY, setGuideY] = useState(0);
  const [maskY, setMaskY] = useState(0);
  const [announcement, setAnnouncement] = useState("");

  const update = (changes) => setSettings((current) => ({ ...current, ...changes }));
  const toggle = (key) => update({ [key]: !settings[key] });
  const setProfile = (profile) => {
    const enabled = profileIsEnabled(settings, profile.changes);
    update(enabled ? DEFAULT_SETTINGS : profile.changes);
    setAnnouncement(`${profile.label}: ${enabled ? "desactivado" : "activado"}.`);
  };

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    const classes = [
      "a11y-readable-font", "a11y-emphasize-titles", "a11y-underline-links", "a11y-magnifier",
      "a11y-align-center", "a11y-align-left", "a11y-align-right", "a11y-align-justify",
      "a11y-contrast-dark", "a11y-contrast-light", "a11y-contrast-high", "a11y-saturation-high",
      "a11y-saturation-low", "a11y-monochrome", "a11y-hide-images", "a11y-reading-mode",
      "a11y-stop-animations", "a11y-hover-highlight", "a11y-focus-highlight", "a11y-keyboard-nav",
      "a11y-cursor-black", "a11y-cursor-white",
    ];
    body.classList.remove(...classes);
    if (settings.readableFont) body.classList.add("a11y-readable-font");
    if (settings.emphasizeTitles) body.classList.add("a11y-emphasize-titles");
    if (settings.underlineLinks) body.classList.add("a11y-underline-links");
    if (settings.magnifier) body.classList.add("a11y-magnifier");
    if (settings.alignment !== "default") body.classList.add(`a11y-align-${settings.alignment}`);
    if (settings.contrast !== "default") body.classList.add(`a11y-contrast-${settings.contrast}`);
    if (settings.saturation !== "default") body.classList.add(`a11y-${settings.saturation === "mono" ? "monochrome" : `saturation-${settings.saturation}`}`);
    if (settings.hideImages) body.classList.add("a11y-hide-images");
    if (settings.readingMode) body.classList.add("a11y-reading-mode");
    if (settings.stopAnimations) body.classList.add("a11y-stop-animations");
    if (settings.hoverHighlight) body.classList.add("a11y-hover-highlight");
    if (settings.focusHighlight) body.classList.add("a11y-focus-highlight");
    if (settings.keyboardNavigation) body.classList.add("a11y-keyboard-nav");
    if (settings.cursor !== "default") body.classList.add(`a11y-cursor-${settings.cursor}`);

    root.style.fontSize = `${settings.fontSize}px`;
    root.style.setProperty("--a11y-content-scale", String(settings.contentScale / 100));
    root.style.setProperty("--a11y-line-height", settings.lineHeight === "compact" ? "1.25" : settings.lineHeight === "relaxed" ? "1.85" : "normal");
    root.style.setProperty("--a11y-letter-spacing", settings.letterSpacing === "compact" ? "-0.03em" : settings.letterSpacing === "wide" ? "0.09em" : "normal");
    root.style.setProperty("--a11y-text-color", settings.textColor || "inherit");
    root.style.setProperty("--a11y-title-color", settings.titleColor || "inherit");
    root.style.setProperty("--a11y-background-color", settings.backgroundColor || "");
    root.setAttribute("data-a11y-screen-reader", String(settings.screenReader));
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));

    document.querySelectorAll("audio, video").forEach((media) => { media.muted = settings.muteSounds; });
  }, [settings]);

  useEffect(() => {
    if (!settings.readingGuide && !settings.readingMask) return undefined;
    const updatePosition = (event) => {
      if (settings.readingGuide) setGuideY(event.clientY);
      if (settings.readingMask) setMaskY(event.clientY);
    };
    window.addEventListener("mousemove", updatePosition);
    return () => window.removeEventListener("mousemove", updatePosition);
  }, [settings.readingGuide, settings.readingMask]);

  const reset = () => {
    setSettings(DEFAULT_SETTINGS);
    setAnnouncement("Todos los ajustes de accesibilidad fueron restablecidos.");
  };

  const goTo = (target) => {
    const element = document.querySelector(target);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
    element?.focus?.();
    setAnnouncement(element ? "Destino de navegación abierto." : "Ese destino no está disponible en esta pantalla.");
  };

  if (hidden) {
    return <button type="button" className="a11y-restore" onClick={() => setHidden(false)}>Mostrar accesibilidad</button>;
  }

  return (
    <>
      <div className="a11y-live" role="status" aria-live="polite">{announcement}</div>
      {settings.readingGuide ? <div aria-hidden="true" className="a11y-reading-guide" style={{ top: guideY }} /> : null}
      {settings.readingMask ? <div aria-hidden="true" className="a11y-reading-mask" style={{ "--mask-y": `${maskY}px` }} /> : null}
      <button type="button" className="a11y-launcher" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-label="Abrir ajustes de accesibilidad">
        <Accessibility aria-hidden="true" size={31} strokeWidth={2.4} />
      </button>

      {open ? (
        <div className="a11y-overlay" role="presentation">
          <section className="a11y-panel" role="dialog" aria-modal="true" aria-labelledby="a11y-title">
            <header className="a11y-header">
              <button type="button" className="a11y-close" onClick={() => setOpen(false)} aria-label="Cerrar ajustes"><X size={24} /></button>
              <h2 id="a11y-title">Ajustes de accesibilidad</h2>
              <span className="a11y-language" aria-label="Idioma: español">🇪🇸&nbsp; ESPAÑOL⌄</span>
            </header>

            <div className="a11y-actions">
              <button type="button" onClick={reset}><RotateCcw size={18} />Reiniciar ajustes</button>
              <button type="button" onClick={() => setShowStatement(true)}><FileText size={18} />Declaración</button>
              <button type="button" onClick={() => { setHidden(true); setOpen(false); }}><EyeOff size={18} />Ocultar la interfaz</button>
            </div>

            <div className="a11y-panel-content">
              <div className="a11y-profiles a11y-section">
                <div className="a11y-intro"><h3>Personalice su experiencia de navegación</h3></div>
                {PROFILES.map((profile) => {
                  const enabled = profileIsEnabled(settings, profile.changes);
                  const Icon = profile.Icon;
                  return <div className="a11y-profile" key={profile.id}>
                    <button type="button" className={`a11y-switch ${enabled ? "on" : ""}`} aria-pressed={enabled} onClick={() => setProfile(profile)}><span>{enabled ? "Sí" : "No"}</span></button>
                    <div><h3>{profile.label}</h3><p>{profile.description}</p></div>
                    <Icon aria-hidden="true" size={27} />
                  </div>;
                })}
              </div>

              <section className="a11y-section" aria-labelledby="content-title"><h3 id="content-title" className="a11y-section-title">Ajustes de contenido</h3><div className="a11y-content-grid">
                <SteppedControl Icon={ZoomIn} label="Escalado de contenidos" value={settings.contentScale === 100 ? "Predeterminado" : `${settings.contentScale}%`} onDecrease={() => update({ contentScale: Math.max(90, settings.contentScale - 10) })} onIncrease={() => update({ contentScale: Math.min(130, settings.contentScale + 10) })} />
                <A11yCard Icon={Type} label="Fuente legible" active={settings.readableFont} onClick={() => toggle("readableFont")} /><A11yCard Icon={Underline} label="Resaltar títulos" active={settings.emphasizeTitles} onClick={() => toggle("emphasizeTitles")} /><A11yCard Icon={Link2} label="Resaltar enlaces" active={settings.underlineLinks} onClick={() => toggle("underlineLinks")} /><A11yCard Icon={ZoomIn} label="Lupa de texto" active={settings.magnifier} onClick={() => toggle("magnifier")} />
                <SteppedControl Icon={Type} label="Ajustar el tamaño de la fuente" value={settings.fontSize === 16 ? "Predeterminado" : `${settings.fontSize}px`} onDecrease={() => update({ fontSize: Math.max(14, settings.fontSize - 2) })} onIncrease={() => update({ fontSize: Math.min(22, settings.fontSize + 2) })} /><A11yCard Icon={AlignCenter} label="Alinear al centro" active={settings.alignment === "center"} onClick={() => update({ alignment: settings.alignment === "center" ? "default" : "center" })} />
                <SteppedControl Icon={AlignJustify} label="Ajustar la altura de la línea" value={settings.lineHeight === "default" ? "Predeterminado" : settings.lineHeight === "compact" ? "Compacta" : "Amplia"} onDecrease={() => update({ lineHeight: settings.lineHeight === "relaxed" ? "default" : "compact" })} onIncrease={() => update({ lineHeight: settings.lineHeight === "compact" ? "default" : "relaxed" })} /><A11yCard Icon={AlignLeft} label="Alinear a la izquierda" active={settings.alignment === "left"} onClick={() => update({ alignment: settings.alignment === "left" ? "default" : "left" })} />
                <SteppedControl Icon={AlignJustify} label="Ajustar el espacio entre letras" value={settings.letterSpacing === "default" ? "Predeterminado" : settings.letterSpacing === "compact" ? "Compacto" : "Amplio"} onDecrease={() => update({ letterSpacing: settings.letterSpacing === "wide" ? "default" : "compact" })} onIncrease={() => update({ letterSpacing: settings.letterSpacing === "compact" ? "default" : "wide" })} /><A11yCard Icon={AlignRight} label="Alinear a la derecha" active={settings.alignment === "right"} onClick={() => update({ alignment: settings.alignment === "right" ? "default" : "right" })} />
              </div></section>

              <section className="a11y-section" aria-labelledby="colors-title"><h3 id="colors-title" className="a11y-section-title">Ajustes de colores</h3><div className="a11y-colors-grid">
                <A11yCard Icon={Moon} label="Contraste oscuro" active={settings.contrast === "dark"} onClick={() => update({ contrast: settings.contrast === "dark" ? "default" : "dark" })} /><A11yCard Icon={Sun} label="Contraste claro" active={settings.contrast === "light"} onClick={() => update({ contrast: settings.contrast === "light" ? "default" : "light" })} /><A11yCard Icon={CircleDashed} label="Contraste alto" active={settings.contrast === "high"} onClick={() => update({ contrast: settings.contrast === "high" ? "default" : "high" })} />
                <A11yCard Icon={Droplets} label="Saturación alta" active={settings.saturation === "high"} onClick={() => update({ saturation: settings.saturation === "high" ? "default" : "high" })} /><ColorControl label="Ajustar el color del texto" value={settings.textColor} onChange={(textColor) => update({ textColor })} />
                <A11yCard Icon={Droplets} label="Monocromo" active={settings.saturation === "mono"} onClick={() => update({ saturation: settings.saturation === "mono" ? "default" : "mono" })} /><ColorControl label="Ajustar el color de los títulos" value={settings.titleColor} onChange={(titleColor) => update({ titleColor })} />
                <A11yCard Icon={Droplets} label="Saturación baja" active={settings.saturation === "low"} onClick={() => update({ saturation: settings.saturation === "low" ? "default" : "low" })} /><ColorControl label="Ajustar el color de fondo" value={settings.backgroundColor} onChange={(backgroundColor) => update({ backgroundColor })} />
              </div></section>

              <section className="a11y-section" aria-labelledby="orientation-title"><h3 id="orientation-title" className="a11y-section-title">Ajustes de orientación</h3><div className="a11y-orientation-grid">
                <A11yCard Icon={VolumeX} label="Silenciar los sonidos" active={settings.muteSounds} onClick={() => toggle("muteSounds")} /><A11yCard Icon={ImageOff} label="Ocultar imágenes" active={settings.hideImages} onClick={() => toggle("hideImages")} /><A11yCard Icon={BookOpen} label="Modo de lectura" active={settings.readingMode} onClick={() => toggle("readingMode")} /><A11yCard Icon={MousePointer2} label="Guía de lectura" active={settings.readingGuide} onClick={() => toggle("readingGuide")} />
                <div className="a11y-links"><p><Link2 size={24} />Enlaces útiles</p><div><button type="button" onClick={() => goTo("#main-content")}>Ir al contenido</button><button type="button" onClick={() => goTo("textarea")}>Ir a la consulta</button></div></div>
                <A11yCard Icon={ZapOff} label="Detener las animaciones" active={settings.stopAnimations} onClick={() => toggle("stopAnimations")} /><A11yCard Icon={ScanLine} label="Máscara de lectura" active={settings.readingMask} onClick={() => toggle("readingMask")} /><A11yCard Icon={Hand} label="Resaltar pasada del ratón" active={settings.hoverHighlight} onClick={() => toggle("hoverHighlight")} /><A11yCard Icon={Focus} label="Resaltar enfoque" active={settings.focusHighlight} onClick={() => toggle("focusHighlight")} /><A11yCard Icon={MousePointer2} label="Cursor negro grande" active={settings.cursor === "black"} onClick={() => update({ cursor: settings.cursor === "black" ? "default" : "black" })} /><A11yCard Icon={MousePointer2} label="Cursor blanco grande" active={settings.cursor === "white"} onClick={() => update({ cursor: settings.cursor === "white" ? "default" : "white" })} />
              </div></section>
            </div>
            <footer className="a11y-branding">Solución de accesibilidad web por <strong>accesiBe</strong><span>Más información ›</span></footer>
          </section>
        </div>
      ) : null}

      {showStatement ? <div className="a11y-overlay a11y-statement-overlay" role="presentation"><section className="a11y-statement" role="dialog" aria-modal="true" aria-labelledby="statement-title"><button type="button" className="a11y-close" onClick={() => setShowStatement(false)} aria-label="Cerrar declaración"><X size={22} /></button><FileText aria-hidden="true" size={30} /><h2 id="statement-title">Declaración de accesibilidad</h2><p>CIAR ofrece controles para adaptar la lectura, el contraste, la navegación por teclado y la orientación visual. Los ajustes se guardan solo en este navegador y pueden restablecerse en cualquier momento.</p><button type="button" className="a11y-primary" onClick={() => setShowStatement(false)}>Entendido</button></section></div> : null}
    </>
  );
}
