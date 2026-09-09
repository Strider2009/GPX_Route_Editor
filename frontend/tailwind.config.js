/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // Mirrors the CSS custom properties in index.css so utilities and plain
      // CSS stay in step.
      colors: {
        brand: {
          DEFAULT: "#e6006e",
          dark: "#c00059",
          tint: "#fde5f0",
        },
        teal: {
          DEFAULT: "#009d90",
          dark: "#00776e",
          deep: "#00443f",
          tint: "#e0f4f2",
        },
        bar: "#1c1c1c",
        ink: {
          DEFAULT: "#1c1c1c",
          muted: "#5f6368",
          faint: "#9aa0a6",
        },
        page: "#f9f9f9",
        surface: "#ffffff",
        line: "#e4e5e7",
      },
      fontFamily: {
        sans: ["Roboto", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [],
};
