/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./app/**/*.{js,jsx}", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ulima: "#F26A21",
        ink: "#1f2933",
        ash: "#f5f6f8",
        line: "#e5e7eb",
        muted: "#64748b",
        paper: "#ffffff",
      },
      fontFamily: {
        display: ["Source Sans 3", "Avenir Next", "sans-serif"],
        body: ["Source Sans 3", "Avenir Next", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        panel: "0 18px 50px rgba(31, 41, 51, 0.10)",
      },
    },
  },
  plugins: [],
};
