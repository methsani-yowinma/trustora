// Fails if any locale file is missing keys (or has extra keys) compared to en.json.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dir = join(import.meta.dirname, "..", "messages");

function flatten(obj, prefix = "") {
  return Object.entries(obj).flatMap(([key, value]) =>
    value && typeof value === "object" ? flatten(value, `${prefix}${key}.`) : [`${prefix}${key}`],
  );
}

const load = (file) => new Set(flatten(JSON.parse(readFileSync(join(dir, file), "utf8"))));
const reference = load("en.json");
let failed = false;

for (const file of readdirSync(dir).filter((f) => f.endsWith(".json") && f !== "en.json")) {
  const keys = load(file);
  const missing = [...reference].filter((k) => !keys.has(k));
  const extra = [...keys].filter((k) => !reference.has(k));
  if (missing.length || extra.length) {
    failed = true;
    console.error(`${file}: missing [${missing.join(", ")}] extra [${extra.join(", ")}]`);
  } else {
    console.log(`${file}: ${keys.size} keys match en.json`);
  }
}

process.exit(failed ? 1 : 0);
