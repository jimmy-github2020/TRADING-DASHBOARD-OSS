import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const roots = ["app", "config"];
const extensions = new Set([".css", ".json", ".ts", ".tsx"]);
const mojibakePattern = /(?:Ã|Â|â|è|é|å|ç|æ|ä|ã|ð|�)/;
const offenders = [];

function extensionOf(path) {
  const match = path.match(/\.[^.]+$/);
  return match?.[0] ?? "";
}

function scan(path) {
  const stat = statSync(path);
  if (stat.isDirectory()) {
    for (const entry of readdirSync(path)) {
      scan(join(path, entry));
    }
    return;
  }

  if (!extensions.has(extensionOf(path))) return;

  const text = readFileSync(path, "utf8");
  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    if (mojibakePattern.test(line)) {
      offenders.push(`${relative(process.cwd(), path)}:${index + 1}: ${line.trim()}`);
    }
  });
}

for (const root of roots) {
  scan(join(process.cwd(), root));
}

if (offenders.length > 0) {
  console.error("Potential mojibake found:");
  console.error(offenders.join("\n"));
  process.exit(1);
}

console.log("Encoding check passed.");
