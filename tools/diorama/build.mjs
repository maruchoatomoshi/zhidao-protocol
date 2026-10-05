import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
await build({
  entryPoints: [path.join(here, "diorama.src.mjs")],
  outfile: path.join(here, "..", "..", "zhidao_v4", "static", "app", "campus-diorama.js"),
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2019",
  legalComments: "none",
  logLevel: "info",
});
