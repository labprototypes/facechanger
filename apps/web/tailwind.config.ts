import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#f2f2f2",
        text: "#000000",
        surface: "#ffffff",
        accent: "#B8FF01",
      },
    },
  },
  plugins: [],
};
export default config;
