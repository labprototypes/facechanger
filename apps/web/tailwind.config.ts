import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        text: "var(--text)",
        surface: "var(--surface)",
        surface2: "var(--surface-2)",
        border: "var(--border)",
        accent: "var(--accent)",
        accentHover: "var(--accent-hover)",
        accentPress: "var(--accent-press)",
      },
      borderRadius: {
        lg: "12px",
        xl: "16px",
      },
      boxShadow: {
        card: "0 2px 10px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [require('@tailwindcss/forms')]
};
export default config;
