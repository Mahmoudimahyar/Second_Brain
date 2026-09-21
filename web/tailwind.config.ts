import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // shadcn defaults per V1.5-R2; custom brand reopens in V2.
      },
    },
  },
  plugins: [],
};

export default config;
