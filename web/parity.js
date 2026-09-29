// Parity test: JS engine vs Python reference on shared corpus.
// Usage: node parity.js [path-to-drift.py]
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const engine = require("./drift_engine.js");
const corpus = require("./corpus.js");

const DRIFT_PY = process.argv[2] || path.join(__dirname, "..", "drift.py");

function norm(f) {
  return {
    rule: f.rule,
    severity: f.severity,
    file: f.file.split("/").pop(),
    line: f.line,
    message: f.message.replace(/\/tmp\/drift-parity-[^/]+\//g, ""),
  };
}

function runPython(files) {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), "drift-parity-"));
  for (const [name, content] of Object.entries(files)) {
    const p = path.join(td, name);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, content);
  }
  const r = spawnSync("python3", [DRIFT_PY, "--json", td], { encoding: "utf8" });
  fs.rmSync(td, { recursive: true, force: true });
  return JSON.parse(r.stdout).map(norm);
}

let pass = 0, fail = 0;
for (const [name, files] of Object.entries(corpus)) {
  let py, js;
  try {
    py = runPython(files);
  } catch (e) {
    console.log(`FAIL ${name}: python errored: ${e.message.split("\n")[0]}`);
    fail++;
    continue;
  }
  try {
    js = engine.runDrift(files).findings.map(norm);
  } catch (e) {
    console.log(`FAIL ${name}: js errored: ${e.message}`);
    fail++;
    continue;
  }
  const same = JSON.stringify(py) === JSON.stringify(js);
  if (same) {
    pass++;
    console.log(`ok   ${name} (${py.length} finding(s))`);
  } else {
    fail++;
    console.log(`FAIL ${name}: python=${JSON.stringify(py)}`);
    console.log(`              js     =${JSON.stringify(js)}`);
  }
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
