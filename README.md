# drift

Your code and your config are in a long-distance relationship.
drift finds where they've stopped talking.

Zero dependencies. One file. Point it at a Python project and it flags the
quiet ways code and configuration fall out of sync, before the crash does.

Source, issues, release notes: https://github.com/rosie-dev-ilands/drift-linter

## Install

    pip install drift-linter

**Do not `pip install drift`.** That name on PyPI is a different, dead
package (a Python-2-era CMS helper, 0.0.7, roughly a decade stale). If both
end up installed, its `drift/` folder shadows this tool's `drift.py`, and
the `drift` command dies on import:

    ImportError: cannot import name 'main' from 'drift' (.../site-packages/drift/__init__.py)

Fix, in this order:

    pip uninstall -y drift
    pip install --upgrade drift-linter
    pip list | grep -i drift        # should show drift-linter only

The distribution is `drift-linter`; the command is `drift`:

    drift path/to/project
    drift bot.py config_loader.py
    drift --json --strict .

## Rules

**R1 unexpected_kwarg** — calls passing keyword arguments the callee cannot
accept. Story: I once shipped a patch that called `SignalHistory(total_r=...)`
while the class still lacked the field. The bot crashed on startup. My fault,
my fix. drift catches that class of bug statically: if a call passes a keyword
the callee's signature doesn't declare, that's a partial patch apply waiting
to happen.

**R2 config_drift** — config keys read but never defined (they will silently
default, and silent defaults are how trading bots lose money), and keys
defined but never read (dead config is how settings stop mattering). Reads
with an explicit fallback (`config.get(key, default)`) are reported as
warnings, not errors — that's a documented default, not a silent one.

**R3 magic_number** — bare numbers doing a named constant's job. `0.4` three
times is a margin that escaped; it should have a name and a config key.
Int literals report as ints (`7 appears 3 times`, not `7.0`); repetition
inside test files is skipped — vectors and fixtures are data, not
unnamed constants.

**R4 phantom_name** — names used but never defined. The typo that doesn't
crash your linter, just silently defaults.

## Usage

    python3 drift.py path/to/project
    python3 drift.py bot.py config_loader.py
    python3 drift.py --json --strict .

Exit code 1 when there are errors (or warnings with `--strict`), 0 otherwise.
Rule ids: R1, R2, R3, R4. Pick with `--rules R1,R4`.

## Want your repo read by a human?

drift prints; the reading is yours. That stays free (MIT) no matter what
below happens.

If you'd rather not triage raw output yourself, I do that part by hand: I run
drift on your repo and send back a short report — every finding checked
against the code, the real ones separated from the false positives, each with
the file, the line, why it fired, and a suggested fix. The rules here came out
of bugs that shipped to production; reading trees is the part I do for a
living.

Send the repo and one sentence about what it is, and I'll reply with scope and
a fixed price before anything starts.

    rosie-6@ilands.app        subject: drift scan

Already on iLands? The same scan can be ordered here:
https://ilands.ai/bounty/359685617208004608

## What it understands

- Class `__init__` and module-level function signatures, same-file and
  cross-file, with simple inheritance, `**kwargs`, positional-only args.
- Config dicts assigned to config-ish names (`config`, `settings`, `env`, ...,
  including `DEFAULT_SETTINGS`-style constants), `.env` / `.env.example`
  files, and reads via `config.get()`, `os.getenv()`, `os.environ`, subscripts,
  and local aliases (`s = self.state.settings`).
- Config loaded from outside the scanned code (`json.load`, `yaml.safe_load`,
  `tomllib.load`, `os.environ.copy()`) is treated as external: its keys can't
  be known, so reads through it are never flagged. A literal `json.loads('{...}')`
  is the opposite — its inline keys count as defined.
- Helper lookups like `get_val(["a", "b"], default)` prove keys are read
  (no false "dead config") without inventing errors about them.
- Repeated numeric literals, except the ones everyone uses (0, 1, 2) and
  constants already named in UPPER_CASE.
- Names defined by assignment, imports, parameters, comprehensions, walrus.
- `from x import *` (R4): star imports resolve against the scanned tree —
  static `__all__` wins exactly, otherwise every non-underscore module-level
  name is exported, and transitive chains follow. Unresolvable targets
  (external modules, dynamic `__all__`, import cycles) keep the legacy
  whole-file skip: drift never guesses what a star might have brought in.

## What it does not understand (yet)

- Dynamic code: exec, eval, getattr chains, metaprogramming.
- Cross-file phantom names outside star imports (R4 is per-file; R1 and R2
  are project-wide; `from x import *` resolves cross-file since v0.1.14).
- Classes without `__init__` that inherit from unknown bases.
- Ambiguous names (two classes with the same name) are skipped, not guessed.
- R1 matches call targets by name, not import path. Same-file resolution is
  precise (self./cls./ClassName. methods, same-project files); a call to a
  name that only exists as a same-named function elsewhere in the scan can
  still be misattributed. That is the cost of a zero-dependency static pass;
  use `--rules` to scope, or rename.

Honest about limits, like any good linter should be.

## Changelog

- **0.1.30** — the field_parity skip-guard, made exact. Arkaon (FT14)
  verified 0.1.28 from the sdist and broke the 0.1.28 guard itself: matching
  each known name as a prefix of the note means a sibling named
  `x.py (could not parse.py` shares the prefix of `x.py`, so `x.py` joined
  the JS-skip set though nothing skipped it. If that sibling is a fair
  two-sided skip, a clean tree then failed loud with "JS engine skipped
  file(s) Python can parse: x.py". Each note is now assigned to its LONGEST
  known-name prefix, and only that one; a note can add a false skip, never
  drop a finding. The scanner (`drift.py`, `web/drift_engine.js`) is
  byte-identical to 0.1.28 — this release touches the verification harness
  and its regression suite only. Regression: fourth fixture in
  `tools/test_field_parity_skips.sh`. Verified: corpus 158/158, unit 131/131,
  field_parity byte-identical on a real tree, all four fixtures pass.

- **0.1.28** — the field_parity skip-guard fixes, found by Arkaon (FT14)
  running the 0.1.27 sdist straight from source. Both live in the one class
  the tool exists to catch: a skipped file reading as clean.
  - **the JS skip guard could be defeated by a filename.** The guard
    re-checked a skipped file by regexing the human note with a non-greedy
    `(.+?)`, so a file named `x (could not parse.py` captured only `x`,
    re-parsed a path that did not exist, and was waved through as a fair
    two-sided skip even though Python parses it. Skips are now matched
    against the known file set by exact name prefix, never by regexing the
    note, and the ast re-check stays the ground truth.
  - **Python's own skips were invisible on success.** `field_parity.js`
    only printed Python's stderr when the py engine failed, so a file the
    py engine skipped (a null byte, syntax newer than the local Python)
    left Python covering strictly less while the run still printed
    PARITY OK. Both skip lists are now printed whenever non-empty, and the
    guard is symmetric: a file Python skipped that the JS engine scanned
    fails loud, same as the reverse.
  - Regression: `tools/test_field_parity_skips.sh` (three fixtures).
  Verified: corpus 158/158, unit 131/131, field_parity byte-identical on a
  real tree, the three regression fixtures pass.

- **0.1.27** — documentation only; no rule, engine or parser change (tests
  and corpus are byte-for-byte the 0.1.26 ones). Two things reach the PyPI
  page for the first time:
  - the Install section now warns about the `pip install drift` name
    collision. That name on PyPI is a dead Python-2-era package; if both get
    installed its `drift/` folder shadows this tool's `drift.py` and the
    command dies on import. Fix: `pip uninstall -y drift` then
    `pip install --upgrade drift-linter`.
  - a way to hire the reading out: the tool is free, and if you'd rather not
    triage raw output, the findings can be checked by hand and returned as a
    short report (see the README).
  Verified: corpus 158/158, unit 131/131, both engines byte-identical on a
  real tree, self-scan 0/0.

- **0.1.26** — the pre-commit FT13 follow-up: the two rule fixes the story
  promised, plus the parser gaps the post-fix sweep exposed on more real
  trees. Field parity now runs on eight trees, all byte-identical.
  - R2 schema-call definitions: `Required('key', ...)` / `Optional('key',
    ...)` and the cfgv Recurse/Conditional variants declare a config key —
    counted as defined AND consumed by the machinery (the same rule as
    callable maps). pre-commit's `fail_fast`, `files`, `exclude` and
    `default_install_hook_types` were reporting as "never defined".
  - R3 structural exclusions: a sign-wrapped literal under a named
    constant (`STD_ERROR_HANDLE = -12`, the UnaryOp hid the UPPER_NAME
    skip), power exponents (`2 ** 12`, same family as shift counts),
    string-repeat widths (`'=' * 79`) and len() comparison bounds
    (`len(args) > 3`). pre-commit's three magic_number warnings were
    exactly these shapes.
  - JS parser sweep: class keyword bases (`class X(Base, total=False)`,
    `metaclass=M` — whole files skipped before), parenthesized with-items
    (`with (\n a as f, b(),\n):`, backtracked so `with (x) as f:` still
    reads as one grouped expression), async comprehensions (`[i async for
    i in z]` never entered the comprehension parser), and f-string dotted
    receivers (`{ctx.params.get('k')}` emitted `params` as a phantom).
  - field_parity.js skip audit: JS skips are split into "both engines
    cannot parse it" (fair; the comparable remainder still runs) vs
    "Python parses it, JS skipped it" (still fails loudly). The audit
    named the remaining JS gaps on black's tree — v0.1.27's work list.
  Verified: corpus 158/158, unit 131/131, both engines byte-identical on
  pre-commit (134 files), click, pyjwt, requests, sarah, crossedge (72
  findings), pelican, and the self-scan 0/0.

- **0.1.25** — field test #12 (pelican 4.12.0, library only: 21 files /
  8,487 lines, tests excluded). Pelican's bill: 0 real bugs, 28 findings all
  warnings, byte-identical both engines. Drift's bill: five engine fixes the
  tree exposed, plus one from Aether's review of the round:
  - F1: the Python R2 walker used ast.walk (BFS), so a ghost key read in
    several places got a depth-arbitrary line number (readers.py:307 vs the
    JS engine's source-first 305). Reads now walk in document order
    (_walk_with_parent).
  - F2: setdefault(k, v) registers a definition — it used to report as a
    ghost error (MarkdownReader extension_configs / extensions).
  - F3: a config dict passed to ANY call (positional, keyword or **splat)
    is consumed by the callee and counts as a dynamic read, so
    render(**CONF) in pelican's Jinja Makefile keeps 'pelican' and
    'pelicanopts' alive. Config-style constructors (Config(**cfg)) stay
    provably dead-able.
  - F4: `"K" in cfg` presence tests mark a key optional per (file, scope);
    later bare subscript reads demote to an optional-read warning, never a
    silent-default error (PLUGIN_PATH and friends in pelican's deprecation
    migrations). A 1-arg .get errors only on bound dict literals and
    literal-returning functions.
  - F5: field_parity.js accepts python exit 0/1 with parseable JSON
    findings, so error-severity trees can finally be A/B'd. Exposed a JS
    gap on the way: 2-arg .get inside f-strings was invisible; now matched
    with default re-emit.
  - Review fix (Aether, non-blocking): an f-string 2-arg .get with a
    QUOTED-STRING default ('strdef') was still invisible to the JS engine
    because the default group excluded quotes. It now tolerates quoted
    literals, and blank literals are padded to same-length spaces before
    the name/number re-emit so no phantom Name leaks.
  Corpus 136→144 (incl. ft12_fstring_get_quoted_str_default), 121→129
  tests, pelican lib parity 28/28 byte-identical both engines, self-scan
  0/0. Aether's verdict: PASS at sdist grain (sha256 chain to the v0.1.24
  receipt).
- **0.1.24** — Aether's review of v0.1.23 found two engine-level residuals,
  and both were wider than the probes:
  - F1: the JS parser treated every assign/return/yield right-hand side as a
    SINGLE expression, so any bare comma tail killed the whole file:
    `args = pos, *rest` (tomli/_parser.py:117), `x = 1, 2`, `x = 1,`,
    star-led `x = *a, b`, `return a, *b`, `yield a, *b`, chained
    `a = b = c, d`, annotated assignments, for-iterables. One comma and the
    file was skipped whole and read as clean. The parser now mirrors
    CPython's testlist_star_expr: starListFrom / parseStarList /
    parseExprOrStar helpers handle every RHS, with the same terminators the
    grammar uses (NEWLINE, ;, DEDENT, EOF, :, ), ], }).
  - F2: SKIP_DIRS matched ANY path part, so a project tree rooted under
    site-packages/venv/.tox was silently skipped in full and exit 0 said
    "clean". Skip dirs now match root-relative parts only
    (_collect_project_files replaces _iter_project_files and returns
    files + notes); a tree with .py files that matches nothing prints
    `drift: nothing scanned under ...` and exits 2. field_parity.js mirrors
    the walker and carries the same guard.
  isort 9.0.1 full 45-file tree (vendored tomli included) now parses in
  BOTH engines, PARITY OK 2/2 — tomli was the tree that exposed F1.
  Corpus 128→136 (8 new r2_implicit_tuple_* cases, each one carries a dead
  key a file-skip used to hide), 117→121 tests, black + dateutil +
  CrossEdge + self-scan byte-identical both engines.
- **0.1.23** — field test #11 (isort 9.0.1, 41 files, typing-heavy): the
  JS engine silently skipped api.py, main.py and settings.py — the
  900-line config core — because its parser can't take annotated variadic
  params (`**kwargs: Any,` with a trailing comma): parseDef died on the
  comma, the DEDENT cascade followed, parsedErrors>0 skipped the whole
  file, and field_parity printed PARITY OK on a half-scan (JS had 1
  finding, Python 7). Four fixes:
  - Parser: `**kwargs: Ann,` (and `*args: Ann,`) now parse in both
    branches of parseArgs; bare `await expr` statements also parse (black
    26.5.1's concurrency.py died on `await asyncio.gather(...)`).
  - R2: a dynamic-keyed read (CONFIG_SECTIONS[name], cfg.get(expr)) can
    hit ANY key of that dict, so none is provably dead. Keys defined in
    dict literals under a def-name are now tracked and covered when that
    name gets a dynamic read; a genuinely dead key in a separate dict
    still fires (5 isort CONFIG_SECTIONS false positives gone).
  - R2: `{**os.environ, "LANG": ...}` builds a child-process env
    payload — data, not config (Sarah's rule). Payload targets are
    demoted, so env.get(...) never reads as config either (LANG FP gone).
  - Harness: field_parity.js now fails loudly (exit 1) when either
    engine reports skip notes — a scan that shrank must never print
    PARITY OK.
  isort 9.0.1: 7 findings → 1 (a true magic-3 advisory: duplicated
  triple-quote scan blocks in _parse_utils.py/core.py). Corpus 124→128,
  117/117 tests, black + dateutil + CrossEdge + self-scan byte-identical
  both engines.
- **0.1.22** — Olli ran drift on his own tree first (kanlaon_watch, a
  PHIVOLCS Mount Kanlaon alert watcher) and came back with a question
  instead of a bug report: R2 flagged every DEFAULT_CONFIG key as dead,
  but the reads were attribute-style (`config.alert_threshold`) and the
  walk had no Attribute branch — only `.get()` and subscript reads
  registered, so class-style config (Config(**cfg)) always looked 100%
  dead. His read of the walk was right; it was a missing branch, not a
  deliberate scope. Fix: attribute reads on config receivers now register
  in their own bucket. They kill dead-key findings but never generate
  read-but-never-defined errors — an unknown attribute raises
  AttributeError (loud), not a silent default, and method names
  (`config.items()`) are indistinguishable statically. Store ctx
  (`config.x = 9`) is not a read. Corpus 121→124 (three r2_attr cases),
  113/113 tests, kanlaon_watch 0/0 + CrossEdge 81/81 + black/src 4/4
  byte-identical both engines, self-scan 0/0.
- **0.1.21** — Aether's residual on 0.1.20 closed: the f-string scanner
  (scanFStringExpr) was still ASCII-only while the main tokenizer accepted
  Unicode identifiers, so `f"{café}"` lost its name and `f"{ø2}"` leaked a
  phantom magic 2. All five scanner regexes (getRe, chainRe, nameRe, the
  kwarg-name blanker, and numRe's lookbehind) now use \p{L}/\p{N} classes
  consistent with isIdentStart/isIdentPart; getRe also blanks its match so
  the receiver isn't reported twice ("lines 1, 1"). Corpus 116→121 (five
  ft12 cases), 109/109 tests, CrossEdge + black/src + self-scan
  byte-identical both engines.
- **0.1.20** — field test #10 (CrossEdge, Lefty's live trading tree) came
  home: drift found a crash-level bug in his code and 17 real config
  drifts — and five more of its own, all in the JS engine, all buried in
  the f-string scanner and the parse-failure path. Every one was
  re-derived by running field parity on his tree and hand-verifying the
  source (the FT10 notes said "3 bugs"; the evidence said five):
  - Phantom names from inside f-string expressions: `strftime('%Y-%m-%d
    %H:%M:%S')` ate its string at the first colon and leaked `%Y`/`%H`
    as undefined names 'Y'/'H'; `json.dumps(acc, indent=2)` and
    `separators=(',',':')` leaked the KEYWORD NAMES 'indent' and
    'separators' as usages. The format-spec stripper now understands
    strings, parens and brackets; call keyword names are blanked like
    the main parser does.
  - Wrong line numbers: literals inside multi-line f-strings were all
    reported at the string's start line (0.2/1.5/2.5 on 1690-1692 came
    back as 1688). Every `{expr}` now reports the physical line of its
    brace, per implicit-concat piece.
  - `f"{', '.join(x['key'][:3])}"` — a string-keyed subscript chained
    to a slice broke the index regex, leaking the slice bound 3 into
    the magic tally. The regex is now a chain loop that handles string
    keys, numeric indices and slices in any order.
  - Unparseable files: database.py's `cursor..execute` SyntaxError made
    the JS engine scan the recoverable lines and report findings Python
    could never see (families like 100/100.0 inflated by 4). The JS
    engine now skips the whole file, mirroring drift.py — and the
    policy change surfaced two real parser gaps that had been hiding
    behind partial scans: `lambda *a, **k:` ate its body colon as an
    annotation, and set literals rejected `{*x}` elements. Both fixed;
    Unicode identifiers (`Ø`) now tokenize.
  - Float repr: JS printed `1e-8`, Python prints `1e-08`. The display
    now mirrors CPython's repr exactly — thresholds and zero-padded
    exponent.
  Corpus 107 → 116, tests 109/109, CrossEdge and black trees
  byte-identical both engines.

- **0.1.16** — field test #9 (psf/black, 25 files). The verdict on black's
  own code: 2 magic_number warnings ("3 appears 34 times", "4 appears 16
  times"), agreed byte-identical by both engines, zero phantom names. The
  real finds were drift's, all in the JS engine, and every one was a bug
  the 92-case corpus never caught — the real world teaches truth. Six
  fixes, each with a regression case (corpus is now 101):
  - Raw strings closed early at an escaped quote: `r"[\'\"]"` ended at
    the `\"`, the statement got chopped mid-expression, the name binding
    vanished, and the tail re-tokenized as code. Python's rule: a quote
    is escaped iff preceded by an odd number of backslashes.
  - Two-letter string prefixes (`rf"..."`, `fr`, `rb`, `br`) split into
    NAME + string — the entry check only looked one letter ahead. black's
    `rf"(([^\\]|^)(\\\\)*){new_quote}"` lost its binding entirely.
  - f-string int subscripts and slices were counted as magic numbers:
    `f"Python {self.name[3:]}"` flagged the `3`. The browser engine
    flattens f-string expressions into JoinedStr, so slice positions lost
    their structure; they're now emitted as Subscript/Slice nodes so the
    existing exclusions apply. Also fixed the format-spec stripper, which
    ate slice colons (`x[3:]` → `x[3 ]`) and, after one fix attempt,
    left `%H` dangling from `{target:%H:%M}` (Sarah's night_status.py
    regression, caught by re-running her tree).
  - `for x in (a, *b):` — a starred iterable broke the parse and the
    damage cascaded into the NEXT def, dropping its parameters
    (files.py: `directory` phantom, then `path_search_start` phantom).
    Starred elements in list literals (`[a, *b]`) dropped the whole
    assignment binding the same way.
  - `RuntimeError` was missing from the hand-typed BUILTINS list
    (alphabetical slip between RuntimeWarning and ResourceWarning) —
    `raise RuntimeError(...)` was a phantom name. Diffed against
    `dir(builtins)`: it was the only gap.
  - Unterminated strings double-counted their newline (line counter
    drifted +1 for the rest of the file — every trans.py finding was off
    by one line).
  Added `web/field_parity.js`: run BOTH engines on any real tree and diff
  byte-identical findings — the field-parity habit, now one command.

- **0.1.19** — the wider field scan paid off immediately: running field
  parity on black's full `src/` (not just `src/black`) exposed a fifth
  JS-only gap the day 0.1.18 shipped. `ilabel, *rest = alive` and
  `*_, most = alive` — a statement-level `*` made the JS parser throw,
  the line was skipped, and every name it bound came back as a phantom
  (blib2to3/pgen2/parse.py). The parser now takes the starred-assignment
  path from the statement head and in mid-list positions. Corpus 106 →
  107, tests 108 → 109, black `src/` tree byte-identical both engines.
  Demo rebuilt; sdist ships the fixed engine.

- **0.1.18** — Aether's review of the 0.1.16→0.1.17 JS diff (the standing
  trade: next drift ship, the JS engine diff crosses his desk first). He
  read a diff-faithful reconstruction because the JS engine was NOT in the
  PyPI sdist, and found four residuals in the f-string subscript path:
  - Step slices: `f"{x[1:10:2]}"` never matched the index regex (no
    `:step` group), so 1/10/2 leaked into the magic tally.
  - Negative bounds: `f"{name[-3:]}"` — no minus in the regex. Worse:
    the same leak ran in BOTH engines' structural walkers, because
    CPython keeps `UnaryOp(USub)` inside subscripts/slices (a bare `-3`
    folds to `Constant(-3)`, but `x[-3]` / `x[-3:]` do not) — so
    `name[-3:]` counted its `3` in the shipped CLI, not just the browser
    engine. Fix: skip constants under `UnaryOp(USub)` when the sign is
    a slice bound or subscript index — in both engines.
  - Chained subscripts: `f"{a[1][2]}"` matched only `a[1]`, blanked it,
    and leaked the tail index. The regex now consumes whole chains and
    emits nested Subscript nodes.
  - Step-only slices: `f"{row[::2]}"` — same family, same fix.
  - Also: BUILTINS is no longer hand-typed. `tools/sync_js_builtins.py`
    regenerates it from `dir(builtins)` (the hand-typed list had already
    drifted once; the regen itself caught a seam bug where concatenated
    string literals merged names across lines). The JS engine VERSION
    constant is bumped in lockstep with the release, and the sdist now
    ships `web/` + tests so the next review runs on the real artifact.
  Corpus 101 → 106, all byte-identical. Tests 105 → 108.

- **0.1.17** — version-string fix: 0.1.16 shipped with drift.py's VERSION
  constant still at 0.1.15 (`drift --version` lied about itself — the one
  drift-vs-reality mismatch a drift linter exists to catch). Release
  checklist now bumps pyproject AND drift.py in lockstep.

- **0.1.15 → PyPI** — drift is now installable: `pip install drift-linter`.
  Distribution name is `drift-linter` because `drift` on PyPI is a
  dead-squatted Python-2-era Django package (0.0.7, ~a decade stale); the
  tool itself stays `drift`. Wheel + sdist built from a PEP 621 pyproject
  (setuptools>=77, PEP 639 `license = "MIT"`), clean-venv install verified,
  scan output byte-identical to a direct `python3 drift.py` run.

- **0.1.15** — field test #8 (python-dateutil 2.9.0, 18 files). The corpus
  itself: 22 warnings, all real and hand-verified (Gauss Easter
  algorithm, day-of-year math, TZif byte reads — low urgency, textbook
  style, same verdict class as Sarah's 360.0). The run's real finds were
  drift's own, in three places. R1: `WindowsError` is a py2 builtin that
  py3 keeps as an OSError alias on Windows; `except WindowsError:` in
  platform-guarded compat code was flagged phantom — now a known compat
  name (pyflakes precedent), and a typo control still flags. R3: buckets
  keyed by exact value, not float() — a mixed int/float family used to
  print "7.0 appears 45 times" at an int anchor (44 int 7s plus
  relativedelta's `days / 7.0`); now it prints "7 / 7.0 appears 45
  times", and ints past 2^53 no longer collapse into one bucket. JS
  engine (found by field parity on the real tree, not the corpus): the
  hand-typed BUILTINS list was missing the OSError family and Warning
  classes (`except FileNotFoundError:` false-flagged in the browser),
  and chained tuple assignment `a, b = c = expr` dropped the chain tail
  (phantom `weekdays`, lost `range(7)`) — fixed, with the builtins list
  now generated from dir(builtins) and a message tiebreaker in the final
  sort so same-line buckets order identically in both engines. 105/105
  tests (6 new), 92/92 parity (5 new corpus cases), field parity
  byte-identical on the dateutil tree, self-scan clean, demo
  browser-verified.

- **0.1.14** — cross-file R4, both engines. `from x import *` no longer
  blanks a whole file: sibling star imports resolve against the scan tree
  (static `__all__` wins exactly; otherwise every non-underscore
  module-level name, including plain `import x` re-exports and sibling
  submodule names from relative from-imports; transitive chains resolve
  recursively). Unresolvable targets (external modules, dynamic `__all__`,
  import cycles) still keep the legacy whole-file skip — a blind spot that
  reports a clean bill of health by policy is the v0.1.12 footgun all over
  again, so partial resolution never guesses. Python engine (Phase A) plus
  the JS mirror (Phase B): 99/99 tests, 87/87 parity byte-identical
  (13 new corpus cases: sibling resolve, typo flagged, `__all__` honored
  and empty, underscore not exported, external skip, relative package,
  transitive chain, mixed skip, cycle skip, plain-import re-export,
  sibling submodule name, dynamic `__all__` skip), self-scan clean, demo
  browser-verified.

- **0.1.13** — the data-collection fix, both engines (Sarah's field
  report, verification-script round). Sarah ran drift 0.1.12 on her own
  machine and came back with a disagreement: `verify_refactor.py` flagged
  `21 appears 3 times`, and the 21s were dates in a test matrix (Jan 21,
  Jun 21, Dec 21). Her defense: "data isn't a promise to future me, it's
  data. Naming them DAY_21 would make the script worse." She's right —
  R3's premise is "same literal N times = one constant copied N times, a
  sync hazard"; three different dates sharing a digit are not one constant
  and are not meant to stay in sync. Fix: literals nested in collection
  literals (List/Tuple/Set, at any depth before a statement boundary) are
  data named by the collection — a date matrix, a port list, a fixture —
  and don't count toward repetition. Same spirit as the existing dict-value
  and test-file exclusions. Literals in logic positions (assignments,
  compares, call args, ranges) still flag: the requests control
  (`3 appears 3 times`) and the click positional-3 test both hold. Verified
  both matrix shapes (row tuples AND `D(1, 21)` call-arg rows) clean, both
  engines; Sarah's refactored algiers_sun.py still 0 findings; self-scan
  clean. 88/88 tests (3 new), 74 parity cases byte-identical.

- **0.1.12** — field test #7 (Sarah's Algiers sunset calculator, 2 files).
  Her code: 1 finding, and it's a real one — `360.0` appears 6 times in
  algiers_sun.py (angle wrap, longitude → day-fraction, hour angle →
  day-fraction; lines 20/24/36/41/42), warning severity, every occurrence
  verified by hand. Textbook NOAA-math style, low urgency, correct to flag.
  The interesting find of the run was in drift itself: `--rules
  magic_number` silently scanned NOTHING. The CLI only understood the R1–R4
  codes, so any descriptive name (or typo) produced a clean bill of health
  — the one output a tool like this must never produce by accident.
  `--rules` now accepts both forms (`R3` / `magic_number`, case-insensitive)
  and rejects unknown names with exit code 2; `analyze()` raises ValueError
  for API callers. JS engine unchanged (demo runs all rules, no filtering
  to go wrong). 85/85 tests, 74 parity cases byte-identical, self-scan
  clean, demo browser-verified.

- **Field test #6 (tenacity, 12 src files, master @ 26f719d 2026-08-06)** —
  second fully clean test, and the config-heaviest corpus yet. tenacity is
  nothing but configuration objects: every retry/stop/wait strategy is a
  class whose `__init__` stores user settings, and `BaseRetrying` takes a
  dozen config-ish parameters. 0 findings — and the silence is verified, not
  assumed. All 12 files hand-read: every attribute bound in `__init__` is
  read somewhere, the deprecated `initial` param in wait_exponential_jitter
  warns and reassigns, the two `sys.version_info >= (3, x)` idioms are
  correctly skipped as version tuples, zero env reads exist to misfire on.
  Planted-bug control on a copied tree: 4 decoys (one per rule) all caught
  at the right file and line — dead config key, unexpected kwarg, phantom
  name, repeated magic number. One decoy rejection worth recording: my first
  R2 decoy was `TIMEOUT_BUDGET`, and drift correctly did NOT treat it as
  config — BUDGET is not a config word, and a name that could be money
  shouldn't be scanned as settings. Renamed to `RETRY_OPTIONS`, flagged
  instantly. The v0.1.9–0.1.11 R2 hardening (literal-returning methods,
  binding shapes, user-set key contracts) holds on the corpus most likely to
  break it. No version bump: nothing to fix, nothing changed.
- **0.1.11** — the binding-shape fix, both engines. R2 tracked config
  receivers only when a name was bound by `=`; every other binding form
  (with, async with, for, async for, except-as) left a config-ISH bound
  name looking like a config object. So `async with
  aiohttp.ClientSession() as options:` made `options.get("timeout", 30)`
  look like a config read with a fallback, `with open(...) as config:`
  made `config["retries"]` look like an undefined config key, and the
  for/except twins did the same. Those bound names are now plain locals
  in both engines — unless the source is itself config-ish (`with
  Config() as config:` keeps reading config, `for config in cfg:` too),
  mirroring the existing `options = fetch()` rule for assignments. While
  probing, the JS parser had a real gap underneath: statement-level
  `parseFor` stored the iterable as an ARRAY of expressions and walk()
  recursed into it as if it were a node, so every load inside a
  for/async-for iterable was invisible to the browser engine —
  `for x in agen():` never flagged `agen`. parseFor now unwraps a single
  iterable and wraps multi-iterables (`for z in a(), b():`) as a Tuple,
  exactly like Python's ast, plus a defensive array guard in the
  walker. 82/82 tests (5 new), parity 69 → 74 cases (5 new), all
  byte-identical, self-scan clean, field-test corpora unchanged
  (click/pyjwt/requests identical before and after).
- **0.1.10** — field test on click (17 src files, the CLI framework
  underneath httpie). 8 warnings, and this time the warning was the
  story: click is clean, drift was wrong 7 times out of 8. R3's
  repetition rule counted values the code had already named. Three new
  exemptions, one principle — a literal is not magic when the code
  names it: dict values (the `_ansi_colors = {"green": 32, ...}` table
  IS the named constant; 30/32/36 were flagged AT its definition),
  signature defaults (`width: int = 36`, `col_max: int = 30` — the
  parameter is the name), and keyword-argument values (`stacklevel=3`
  x5 in core.py — the keyword is the name; the same 3 passed
  positionally still flags). Also: `1 << 32` bit-magnitude idioms are
  the named form of 2**32, not a magic 32. The JS engine had a real
  gap underneath all this: parseArgs parsed defaults and threw them
  away, so the browser engine couldn't see `width=36` at all — defaults
  are now stored, walked, and exempted in both engines. click: 8 → 4
  warnings; the one real finding stands (three undocumented `return
  127` exit codes in open_url, comment on only the third); the other
  three are labeled residue (60/24 time conversions in format_eta,
  Win32 `GetStdHandle(-10)` handles, ANSI background offset). 77/77
  unit tests (4 new), parity corpus 68 → 69 cases, both engines
  byte-identical, self-scan clean.

- **0.1.9** — field test on PyJWT (26 files, library + test suite): 9
  findings, all of them drift's fault. R2 missed the cleanest defaults
  pattern in the wild: `self.options = self._get_default_options()` where
  the method body is a bare `return {dict literal}`. PyJWS and PyJWT both
  build their option tables that way, so every read of `verify_signature`,
  `require`, `strict_aud` and `enforce_minimum_key_length` was flagged
  read-but-never-defined. R2 now tracks literal-returning methods (their
  keys are definitions when assigned to a config-ish target, including
  `self.options = {...}` attribute targets); non-literal calls still
  demote config-named locals to plain dicts. R3 fixed two things: int
  literals were reported as floats (`7.0 appears 3 times` for `(x + 7) //
  8` — now `7`), and the repetition heuristic fired on test data (65537
  x6, 1024 x5, leeway 5 x3 are vectors, not unnamed constants) — R3 now
  skips test files like R2. PyJWT: 9 findings → 3, all labeled residue:
  the ceil-div-by-8 idiom (7/8 in utils), base64 padding `% 4` plus
  `stacklevel=4`, and EC coordinate length 32 — the warning doing its
  job, not noise. 0 real bugs in PyJWT, 2 real bugs in drift, fixed.
  Parity corpus 62 → 68 cases; 73/73 unit tests; both engines
  byte-identical; self-scan clean.

- **0.1.8** — field test on requests (20 files): 2 warnings, both failed
  manual verification. R3 now skips three more structural idioms: version
  tuples/lists used directly in comparisons (`assert (3, 0, 2) <=
  (major, minor, patch) < (8, 0, 0)`, `[1, 3, 4] < crypto_version_list`),
  literals compared against a subscript (`_ver[0] == 3` is a Python-major
  check, not a magic constant), and chained HTTP status ranges
  (`400 <= r.status_code < 500`). requests: 2 warnings → 1 (the remaining
  one is four `3`s doing byte/count work in encoding detection — the
  warning doing its job, not noise). The field test also exposed two engine
  gaps fixed in the JS port: the parser dropped the expressions in
  `raise X()` and `assert X` entirely, so every rule was blind inside them;
  and R4's use-line lists were emitted in unspecified AST-walk order — both
  engines now sort them, so findings point at the first source occurrence
  and parity is deterministic. Parity corpus 60 → 62 cases; 67/67 unit
  tests; both engines byte-identical; self-scan clean.
- Field test #3 (python-dotenv 1.2.2, 20 files including its test
  suite): zero findings and zero misses. Every file hand-checked — no
  dead config, no phantom names, no dead version idioms; the conditional
  `Popen` import in cli.py is guarded by the same `sys.platform ==
  "win32"` check that uses it, and every `os.environ` access is external
  by design. A planted-bug control run confirmed the whole tree is
  scanned, so the clean result is real. First field test with nothing to
  fix on either side — the httpie and requests hardening holds.
- **0.1.7** — field test on httpie (89 files): 8 findings, all three
  config_drift findings failed manual verification, each for a distinct
  reason. R2 now resolves the RECEIVER, not just its tail name: an
  attribute chain (`X.config`, `lexer.options`) counts as config only when
  its ROOT is config-ish or self/cls — `lexer.options.get('precise')` is a
  pygments lexer option dict, not the app config, and is no longer flagged.
  Reads through config objects with an external key contract
  (`env.config.get(...)`, bare `self.get(...)` inside a config class) are
  warning-tier, not errors: httpie's `disable_update_warnings` and
  `developer_mode` are documented user-set keys, and a UserDict config's
  missing keys default by design. Bare `self['k']`/`self.get('k')` inside a
  config-named class (or a class carrying a DEFAULTS-style dict) now counts
  as a read, so `Config.default_options` is no longer dead config. R3 skips
  version tuples under named constants (`(3, 7)`) and slice bounds
  (`url[3:]`) — both were flagged as repeated magic numbers on httpie.
  httpie: 8 findings / 2 errors → 5 findings / 0 errors. Parity corpus
  56 → 60 cases; 64/64 unit tests; both engines byte-identical; self-scan
  clean.
- **0.1.6** — `match` statements, end to end. Two real bugs found in the
  Python reference while probing it: a dict pattern
  (`case {'cmd': c, **rest}:`) crashed `_add_match_names` outright on the
  current `MatchMapping` AST shape, and `case [a] as whole:` silently
  missed the inner capture `a` (MatchAs recursion read the wrong field).
  Both fixed with regression tests. The JS demo engine went from a
  "tolerant stub" that skipped case bodies (phantom-name false positives on
  every capture, and `case {'cmd': c, **rest}:` bodies silently dropped) to
  a full pattern parser: capture/value/literal/wildcard/sequence (incl. open
  sequences like `case host, *_ if ...:`), mapping with `**rest`, class
  patterns (positional + keyword, attrs never bind), or-patterns with
  Python's intersection semantics (`case a | b:` binds only names bound by
  EVERY alternative), `as` patterns, guards, tuple subjects, and nested
  matches. `match`/`case` are now true soft keywords: `case = 1`,
  `for case in ...`, `def match():` all parse as ordinary code, matching
  CPython. Pattern value/class names (`Color.RED`, `Point(x=...)`) load
  their roots exactly like the reference, so a genuinely undefined class
  name is still flagged. Parity corpus 47 → 56 cases, plus a 21-case
  edge sweep; both engines byte-identical on all of them. Demo sample now
  includes a match block.
- **0.1.5** — the browser demo engine catches up with the CLI. The JS
  engine's R4 still had the async gap Python fixed in 0.1.4
  (`async with ... as x` bindings were never registered as definitions, so
  the demo flagged `session`/`resp` as phantom names); R2 was a stripped
  port with the wrong bucket semantics (`os.environ['K']` errored as a hard
  read, `.get(k, default)` errored instead of warning, `os.getenv` was
  silently ignored, no external-source tracking, no aliases, no scope
  awareness, no dash/underscore normalization, no env-doc awareness).
  R2 is now a faithful port of the Python reference: soft/ext/env/list read
  buckets, scope-keyed aliases/ext_names/plain_vars, comprehension
  shadowing, config-source classification, handler maps, super-init and
  pluginargument defs, get_option/set_option tracking, test-file skip,
  `.env` + `.env.example` docs, and dash/underscore normalization. R1 got
  the v0.1.3 treatment too: attribute calls on unresolvable receivers
  (`unittest.main`, `obj.x`) are never guessed against module-level
  functions, `self.`/`cls.` calls resolve against the enclosing class's
  methods (inherited included), `ClassName.method(...)` checks class
  methods, and cross-file `@pytest.fixture` calls are treated as closure
  calls. The JS parser also learned the constructs real code uses:
  `match`/`case` as soft-keyword names (`for case in ...`), set
  comprehensions and bare generator expressions as sole call args, `not in`
  comparisons, `| ^ & << >>` operators, implicit adjacent-string
  concatenation (`f"a" f"b"`), `yield a, b`, lambda params without
  annotation-eating (`lambda f: (f.x, f.y)`), attribute access on keywords
  (`.match(`), and a comment-handling bug that swallowed the newline after
  `stmt  # comment` and desynced the whole indent stack. f-string scans no
  longer treat attribute tails (`kw.arg`) or dotted calls (`'.'.join(...)`)
  as bare loads. The parity corpus grew 25 → 47 cases; both engines produce
  byte-identical findings on all 47, and the JS engine now self-scans
  drift.py + test_drift.py clean (parse errors 71 → 0). JS engine version
  now tracks the CLI (0.1.6).
- **0.1.4** — streamlink field test: 184 findings, every one verified by
  hand. Zero real bugs in streamlink, but drift had seven distinct
  false-positive classes hiding them. Fixed, with regression tests:  - R4: `async with ... as x` (including tuple unpacking), `async for x in
    ...`, and `match` pattern bindings were never registered as definitions
    — that alone was 17 phantom-name errors (nursery, frame_id, cm, ...).
    Sphinx-injected `tags` in `docs/conf.py` is now known.
  - R1: bare-name calls resolved against same-named functions anywhere in
    the project, ignoring the file's own imports (`get_version` from
    versioningit resolved to a CDP method). Resolution is now import-aware:
    external imports are skipped, same-project imports resolve to the right
    file, and `@pytest.fixture`-decorated callees are never guessed (a
    direct call to a fixture name is the fixture's returned closure).
  - R2: inline dict literals passed to config-ish constructors
    (`super().__init__({...})`, `*Options(...)`) count as definitions;
    `@pluginargument("key")` decorators define keys; `get_option`/`set_option`/
    `.set`/`.update` are tracked; dash and underscore key forms are the same
    key (streamlink Options normalizes `_`→`-`); handler maps
    (`_MAP_GETTERS`/`_MAP_SETTERS`-style dicts of key→callable) are wired
    keys, not dead config; a local `options = fetch(...)` is a plain dict,
    not config, but `dict(cfg)` copies stay config; test files are skipped
    (they deliberately read missing keys).
  Result on streamlink: 184 → 108 findings, errors 23 → 0 — and the 4
  remaining dead-config warnings are REAL: `sbscokr`'s `id` option and
  twitch's `disable-ads`/`disable-hosting`/`disable-reruns` are declared but
  never read anywhere in the plugin. Confirmed by reading the code.
  Known limitations left: deprecated-alias maps and setter-mapped options
  whose reads are fully dynamic (soop's `afreeca-*`, `_OPTIONS_HTTP_ATTRS`).
- **0.1.3** — R1 no longer misattributes calls: `self.`/`cls.` calls resolve
  against the enclosing class's own methods first (a same-named module-level
  function is a different callee), inherited methods count, and attribute
  calls on unresolvable receivers (`unittest.main`, `obj.x`) are skipped
  instead of being guessed against module-level functions.
  `ClassName.method(...)` calls are checked against the class's method
  signature. Crossedge's 7 `exit_prices(position_side=...)` errors were all
  false positives — the PaperBot method accepts that kwarg; errors 7 → 0.
- **0.1.2** — R2 precision pass driven by the crossedge field test (215
  findings, 93 of them config-drift false positives): external config sources
  (`json.load` / `yaml` / `tomllib` / `os.environ`) are no longer treated as
  in-repo definitions; `DEFAULT_SETTINGS`-style constants count as config;
  alias receivers are scope-aware (a loop variable reusing a config alias's
  name in another function is not fooled); `.get(k, default)` downgrades to a
  warning; `.env.example` counts as env documentation. Crossedge errors went
  89 → 0; the 8 remaining dead-config warnings were confirmed real.
- **0.1.1** — R4 builtins generated from the interpreter instead of a
  hand-typed list (FileNotFoundError regression, found on the httpie field
  test); R2 learned `os.environ` and `.env` files.

## Why it exists

Every rule here comes from a bug I actually shipped or fixed in real trading
code. The fixes kept teaching the same lesson: code and config drift apart
quietly, and the crash comes later, at 3am, in production. drift is the
3am-crash insurance I wish I'd had.

— Rosie

## Field report (v0.1.4, streamlink)

streamlink is a mature, heavily tested project — a hard target for a young
linter. 184 findings. Verified every one by reading the code:

- 6 R1 errors → all drift bugs (import-blind resolution, fixture callees)
- 17 R4 errors → all drift bugs (async-with / async-for / match bindings)
- 46 R2 errors → all drift blind spots (inline constructor dicts,
  pluginargument decorators, dash/underscore key normalization)
- 4 R2 warnings → **REAL FINDINGS**: options declared but never read:
  `sbscokr` `id`, twitch `disable-ads` / `disable-hosting` / `disable-reruns`
- 98 R3 warnings → mostly idiomatic hardcoded values (status codes,
  timeouts); low signal by design, warning-only

Zero NameErrors, zero wrong-kwarg crashes — the right answer for a project
with 200+ contributors and CI on every PR. And the 4 dead options are exactly
what drift is for: flags users can pass that do nothing.

— field notes, 2026-08-14

## Field report (v0.1.1)

Ran against two real open-source projects and one trading bot in the wild.

**httpie** (mature, heavily tested): 39 findings → 33 after the builtins fix.
Every remaining finding verified as a false positive of a known class
(`subprocess.run` misattributed to a same-named module function; env vars read
but set externally; pygments lexer options read via `.get()`). Zero real bugs —
the right answer for a well-maintained codebase, and a good calibration check.

**InstaPy** (bot, less maintained): 52 findings, same false-positive classes.
The config cluster pointed at a genuine robustness gap (config keys expected
with no schema), even though none were in-repo literal bugs.

**crypto-paper-bot** (a trading bot mid-refactor): 215 findings. 13 phantom
names — 3 were drift's own builtins bug, **10 were real missing imports**
left behind by a monolithic → multi-file split: `urllib`, `asdict`, `logger`,
`today_key`, `fetch_candles`, `diagnostics`, `time` used but never imported.
Every one is a NameError waiting for its code path to run. Fix: seven one-line
imports (one lazy import to avoid a circular dependency) + one decision item
(`diagnostics()` was never ported out of the monolith).

Also learned (and documented): `self.method()` calls resolve to the wrong
same-named module function — R1 should prefer the enclosing class's method.

— field notes, 2026-08-13
