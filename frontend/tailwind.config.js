/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./app/**/*.{js,jsx}", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta institucional Universidad de Lima.
        ulima: "#FF5117",
        institucional: {
          naranja: "#FF5117",
          negro: "#000000",
          gris: "#97999B",
        },
        secundario: {
          turquesa: "#00C5D6",
          naranja: "#FFA000",
          verde: "#00C78B",
          gris: "#C3C8C8",
          beige: "#DAC9B5",
          rosa: "#F3BBCE",
        },
        ink: "#26201B",
        ash: "#F4EFE9",
        fondo: "#FAF8F5",
        line: "#EAE2D9",
        muted: "#7A6F66",
        paper: "#ffffff",
        nodo: {
          empresa: "#3D7A9E",
          herramienta: "#2E8C7F",
          puesto: "#8A6FB8",
        },
      },
      fontFamily: {
        display: ["Roboto", "Helvetica Neue", "sans-serif"],
        body: ["Roboto", "Helvetica Neue", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel: "0 20px 50px rgba(38, 32, 27, 0.10)",
        input: "0 8px 30px rgba(38, 32, 27, 0.07)",
      },
    },
  },
  plugins: [],
};
