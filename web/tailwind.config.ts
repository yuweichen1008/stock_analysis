import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:       "#0d0d14",
        surface:  "#1a1a2e",
        border:   "#2e2e50",
        muted:    "#8888aa",
        accent:   "#448aff",
        fear:     "#ef4444",
        greed:    "#22c55e",
        neutral:  "#6b7280",
      },
    },
  },
  plugins: [],
};

export default config;
