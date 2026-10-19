// Regenerates types/api.d.ts from the FastAPI app's OpenAPI schema.
// Usage: npm run gen:api   (needs api/.venv with the app installed)
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const apiDir = join(here, "..", "..", "api");
const python =
  process.platform === "win32" ? join(apiDir, ".venv", "Scripts", "python.exe") : join(apiDir, ".venv", "bin", "python");

const schema = execFileSync(python, ["-c", "import json; from app.main import app; print(json.dumps(app.openapi()))"], {
  cwd: apiDir,
  encoding: "utf-8",
});

const out = join(here, "..", "types");
mkdirSync(out, { recursive: true });
writeFileSync(join(out, "openapi.json"), schema);
execFileSync(process.execPath, [join(here, "..", "node_modules", "openapi-typescript", "bin", "cli.js"), join(out, "openapi.json"), "-o", join(out, "api.d.ts")], {
  stdio: "inherit",
});
