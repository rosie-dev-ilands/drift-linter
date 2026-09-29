// Field parity runner: run BOTH engines on a real tree and diff findings.
// Usage: node web/field_parity.js /path/to/tree
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const engine = require("./drift_engine.js");

const TREE = process.argv[2];
const DRIFT_PY = path.join(__dirname, "..", "drift.py");
if (!TREE) { console.error("usage: node web/field_parity.js <tree>"); process.exit(2); }

const SKIP_DIRS = new Set([".git", ".hg", ".svn", "__pycache__", "node_modules", "venv", ".venv",
  ".tox", "dist", "build", "site-packages", ".mypy_cache", ".pytest_cache"]);

// mirror drift.py's walker: skip dirs match root-RELATIVE parts only, so a
// tree rooted under site-packages/venv/.tox is scannable (review F2)
function walk(dir, base, out) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      const rel = path.relative(base, full);
      if (rel.split(path.sep).some((part) => SKIP_DIRS.has(part))) continue;
      walk(full, base, out);
    } else if (ent.name.endsWith(".py")) {
      const rel = path.relative(base, full);
      out[rel] = fs.readFileSync(full, "utf8");
    }
  }
  return out;
}

// finder for the nothing-scanned guard: does the tree contain .py at all?
function hasPy(dir) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) { if (hasPy(full)) return true; }
    else if (ent.name.endsWith(".py")) return true;
  }
  return false;
}

const files = walk(TREE, TREE, {});
if (Object.keys(files).length === 0) {
  if (hasPy(TREE)) {
    console.error(`PARITY FAIL: nothing scanned under ${TREE}: .py files exist but every path matched a skip dir — refine the path; a zero-file scan is not a clean bill`);
    process.exit(2);
  }
  console.error(`PARITY FAIL: no .py files under ${TREE}`);
  process.exit(2);
}
console.log(`tree: ${TREE} (${Object.keys(files).length} .py files)`);

function norm(f) {
  // normalize paths: strip the tree prefix so both engines compare equal
  var file = f.file;
  if (file.indexOf(TREE) === 0) file = file.slice(TREE.length + 1);
  var message = f.message.split(TREE + "/").join("");
  return { rule: f.rule, severity: f.severity, file: file, line: f.line, message: message };
}
function sortFn(a, b) {
  return (a.file + a.line + a.rule + a.message).localeCompare(b.file + b.line + b.rule + b.message);
}

// v0.1.28 (Arkaon FT): identify skips by matching each KNOWN file name
// against the note prefixes, never by regexing the human note. The old
// non-greedy `(.+?)` guard let a filename containing " (could not parse"
// capture only the prefix, re-check a path that did not exist, and wave the
// file through as a fair two-sided skip.
function skippedNames(notes, prefixOf) {
  var set = {};
  Object.keys(files).forEach(function (name) {
    var prefix = prefixOf(name);
    for (var i = 0; i < notes.length; i++) {
      if (notes[i].indexOf(prefix) === 0) { set[name] = true; break; }
    }
  });
  return set;
}

let py, js, pyNotes = [];
try {
  const r = spawnSync("python3", [DRIFT_PY, "--json", TREE], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  // drift exits 1 when findings are present (linter semantics); that is a
  // result, not an engine failure. Exit >= 2 or unparseable stdout = failure.
  let parsed = null;
  try { parsed = JSON.parse(r.stdout); } catch (e) { parsed = null; }
  if (r.status === null || r.status >= 2 || (r.status !== 0 && parsed === null)) {
    console.error("python engine failed (exit " + r.status + "):", r.stderr.slice(0, 2000));
    process.exit(1);
  }
  if (parsed === null) { console.error("python parse error: stdout was not a findings JSON"); process.exit(1); }
  py = parsed.map(norm).sort(sortFn);
  // v0.1.28: keep Python's own skip notes even on success. They used to be
  // shown only when the py engine failed, so a py-side skip read as clean.
  pyNotes = (r.stderr || "").split("\n").filter(function (l) { return l.indexOf("drift:") === 0; });
} catch (e) { console.error("python parse error:", e.message); process.exit(1); }

try {
  var jsResult = engine.runDrift(files);
  js = (jsResult.findings || []).map(norm).sort(sortFn);
  var jsNotes = jsResult.notes || [];
  var jsSkips = skippedNames(jsNotes, function (name) { return "drift: skipping " + name + " ("; });
  var pySkips = skippedNames(pyNotes, function (name) { return "drift: skipping " + path.join(TREE, name) + " ("; });

  // Both skip lists are printed whenever non-empty — a skipped file must
  // never read as clean.
  if (pyNotes.length) {
    console.error("python engine notes:");
    pyNotes.forEach(function (n) { console.error("  " + n); });
  }
  if (jsNotes.length) {
    console.error("js engine notes:");
    jsNotes.forEach(function (n) { console.error("  " + n); });
  }

  // (1) v0.1.26: a file skipped because NEITHER engine can parse it (py2
  // sources, intentionally-invalid fixtures, syntax newer than the local
  // Python — black's tests/data) is a fair skip: nothing comparable was
  // lost. Fail only when Python CAN parse a file the JS engine skipped.
  // The ast re-parse is the ground truth, not the note.
  var unfair = [];
  Object.keys(jsSkips).forEach(function (name) {
    var r = spawnSync("python3", [
      "-c", "import ast, sys; ast.parse(open(sys.argv[1], encoding='utf-8', errors='replace').read())",
      path.join(TREE, name),
    ], { encoding: "utf8" });
    if (r.status === 0) unfair.push(name);
  });
  if (unfair.length) {
    console.error("PARITY FAIL: JS engine skipped file(s) Python can parse: " + unfair.join(", "));
    process.exit(1);
  }

  // (2) v0.1.28 mirror: Python skipped a file the JS engine scanned, so the
  // py side covered strictly less and said nothing. Fail loud, same as (1).
  var mirror = Object.keys(pySkips).filter(function (name) { return !jsSkips[name]; });
  if (mirror.length) {
    console.error("PARITY FAIL: Python engine skipped file(s) the JS engine scanned: " + mirror.join(", "));
    process.exit(1);
  }

  if (jsNotes.length || pyNotes.length) {
    var both = Object.keys(jsSkips).filter(function (n) { return pySkips[n]; }).length;
    console.error("note: " + both + " file(s) skipped by both engines (unparseable for this Python) — comparing the rest");
  }
} catch (e) { console.error("js engine error:", e.message); process.exit(1); }

console.log(`python: ${py.length} findings | js: ${js.length} findings`);

let diffs = 0;
const maxLen = Math.max(py.length, js.length);
for (let i = 0; i < maxLen; i++) {
  const a = JSON.stringify(py[i] || null);
  const b = JSON.stringify(js[i] || null);
  if (a !== b) {
    diffs++;
    console.log(`DIFF py=${a}`);
    console.log(`     js=${b}`);
  }
}
console.log(diffs === 0 ? `PARITY OK (${py.length} findings, byte-identical both engines)` : `${diffs} divergence(s)`);
process.exit(diffs ? 1 : 0);
