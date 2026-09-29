// Bulk parity sweep: tricky match-statement snippets, Python vs JS, byte-identical?
const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const engine = require("./drift_engine.js");

const SNIPPETS = {
  or_literals: `def f(x):
    match x:
        case 1 | 2 | 3:
            return "small"
        case _:
            return None
`,
  negative_literals: `def f(x):
    match x:
        case -1:
            return "neg"
        case -1.5:
            return "negf"
`,
  str_bytes_none: `def f(x):
    match x:
        case "go":
            return 1
        case b"raw":
            return 2
        case None:
            return 3
        case True:
            return 4
`,
  nested_seq_mapping: `def f(x):
    match x:
        case [a, [b, c]]:
            return a, b, c
        case {"a": {"b": d}}:
            return d
`,
  guard_with_capture: `class Point:
    pass
Point = Point()
def f(p):
    match p:
        case Point(x=px, y=py) if px > 0:
            return px + py
`,
  value_or_pattern: `class Color:
    pass
Color = Color()
def f(c):
    match c:
        case Color.RED | Color.BLUE:
            return "color"
`,
  as_wraps_or: `def f(x):
    match x:
        case (a | b) as whole:
            return whole
`,
  class_with_as: `class Point:
    pass
Point = Point()
def f(p):
    match p:
        case Point() as origin:
            return origin
`,
  rest_only: `def f(x):
    match x:
        case [*rest]:
            return rest
`,
  mixed_keys: `class Color:
    pass
Color = Color()
def f(m):
    match m:
        case {1: a, "k": b, Color.RED: c}:
            return a, b, c
`,
  nested_match: `def f(x):
    match x:
        case [y]:
            match y:
                case z:
                    return z
`,
  soft_keyword_def: `def match(x):
    return x
def case():
    return 1
print(match(case()))
`,
  soft_keyword_loop: `items = [1]
for case in items:
    print(case)
match = 5
print(match)
`,
  kwd_or_pattern: `class Point:
    pass
Point = Point()
def f(p):
    match p:
        case Point(x=a | b):
            return a, b
`,
  or_mappings_common: `def f(m):
    match m:
        case {"a": x} | {"b": x}:
            return x
`,
  hex_underscore: `def f(x):
    match x:
        case 0x10:
            return 1
        case 1_000:
            return 2
`,
  positional_and_kwd: `class Point:
    pass
Point = Point()
def f(p):
    match p:
        case Point(x, y=py):
            return x, py
`,
  guard_isinstance: `def f(x):
    match x:
        case int() as n if isinstance(n, int) and n > 0:
            return n
`,
  subject_undefined: `def f():
    match undefined_var:
        case 1:
            return 1
`,
  as_single_name: `def f(x):
    match x:
        case y as z:
            return z
`,
  trailing_commas: `def f(x):
    match x:
        case [a, b,]:
            return a
        case {"k": v,}:
            return v
        case Point(p,):
            return p
`,
};

function norm(f) {
  return {
    rule: f.rule, severity: f.severity,
    line: f.line,
    message: f.message.replace(/\/tmp\/drift-parity-[^/]+\//g, ""),
  };
}

function runPython(src) {
  const td = fs.mkdtempSync(path.join(os.tmpdir(), "drift-parity-"));
  fs.writeFileSync(path.join(td, "a.py"), src);
  const r = spawnSync("python3", ["/workspace/drift/drift.py", "--json", td], { encoding: "utf8" });
  fs.rmSync(td, { recursive: true, force: true });
  if (r.status !== 0 && !r.stdout.trim()) return { error: r.stderr.split("\n")[0] };
  try { return JSON.parse(r.stdout).map(norm); } catch (e) { return { error: r.stderr.split("\n")[0] }; }
}

let pass = 0, fail = 0;
for (const [name, src] of Object.entries(SNIPPETS)) {
  const py = runPython(src);
  let js;
  try { js = engine.runDrift({ "a.py": src }).findings.map(norm); }
  catch (e) { js = { error: e.message }; }
  const same = JSON.stringify(py) === JSON.stringify(js);
  if (same) { pass++; console.log("ok   " + name); }
  else {
    fail++;
    console.log("FAIL " + name);
    console.log("  python: " + JSON.stringify(py));
    console.log("  js    : " + JSON.stringify(js));
  }
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
