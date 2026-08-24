import { unlinkSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  plugins: [
    {
      name: "omit-uncompressed-incidents",
      closeBundle() {
        const p = resolve("dist/data/incidents.json");
        if (existsSync(p)) unlinkSync(p);
      },
    },
  ],
});
