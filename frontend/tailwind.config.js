/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        rf: {
          bg: "#0a0e14",
          panel: "#111722",
          panel2: "#0d131d",
          border: "#1e2a3a",
          grid: "#16202e",
          text: "#c7d2e0",
          dim: "#6b7a8f",
          accent: "#33d17a",
          warn: "#f0b429",
          alert: "#ef476f",
          scan: "#3b82f6",
        },
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "'Fira Code'", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
