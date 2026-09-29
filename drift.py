#!/usr/bin/env python3
"""drift — find where your code and your config have drifted apart.

Zero dependencies, Python 3.8+. Point it at a project and it looks for the
quiet ways code and configuration fall out of sync:

  R1 unexpected_kwarg  calls passing keyword args the callee cannot accept
  R2 config_drift      config keys read but never defined, defined but never read
  R3 magic_number      bare numbers doing a job a named constant should do
  R4 phantom_name      names used but never defined (typos that silently default)

Every rule comes from a bug I actually shipped or fixed. See README.md.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

VERSION = "0.1.30"

SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", "venv", ".venv",
    ".tox", "dist", "build", "site-packages", ".mypy_cache", ".pytest_cache",
}

CONFIG_NAMES = {"config", "conf", "settings", "cfg", "env", "defaults", "options", "getters", "setters"}


def _is_config_name(name: str) -> bool:
    """True when a variable name refers to a config object.

    Matches the exact CONFIG_NAMES set (settings, cfg, ...) and UPPER_CASE
    constants built from a config word (DEFAULT_SETTINGS, APP_CONFIG, ...) so
    module-level default dicts count as config sources too.
    """
    low = name.lower()
    if low in CONFIG_NAMES:
        return True
    if UPPER_NAME_RE.match(name) and CONFIG_NAMES.intersection(re.split(r"[^a-z0-9]+", low)):
        return True
    return False

MAGIC_MIN_COUNT = 3
# Structural digits excluded from R3 (0/1/2/-1 as int or float): loop
# indices, flags, off-by-one neighbors — every linter's built-in noise.
_MAGIC_STRUCTURAL_INTS = (0, 1, 2, -1)
_MAGIC_STRUCTURAL_FLOATS = (0.0, 1.0, 2.0, -1.0)

# Schema-call families whose first string argument names a config key
# (cfgv: Required / Optional / Conditional* plus the Recurse variants).
# A key a schema declares is defined AND consumed by the machinery, same
# as a callable map's keys — see _check_r2 (pre-commit FT13).
_SCHEMA_KEY_CALLS = frozenset((
    "Required", "Optional", "RequiredRecurse", "OptionalRecurse",
    "ConditionalRequired", "ConditionalOptional",
))

# --rules accepts both the R1..R4 codes and the descriptive names.
RULE_ALIASES = {
    "R1": "unexpected_kwarg",
    "R2": "config_drift",
    "R3": "magic_number",
    "R4": "phantom_name",
}
ENV_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
UPPER_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

# Every name the interpreter itself provides, so `except FileNotFoundError` and
# friends are never mistaken for a typo. Built from the running interpreter
# (not a hand-typed list — that's how FileNotFoundError got missed in v0.1).
try:
    import builtins as _builtins
    BUILTINS = frozenset(dir(_builtins))
except Exception:  # pragma: no cover - defensive fallback
    BUILTINS = frozenset("""abs aiter all anext any ascii bin bool breakpoint bytearray bytes
callable chr classmethod compile complex delattr dict dir divmod enumerate eval exec filter
float format frozenset getattr globals hasattr hash help hex id input int isinstance
issubclass iter len list locals map max memoryview min next object oct open ord pow print
property range repr reversed round set setattr slice sorted staticmethod str sum super tuple
type vars zip BaseException Exception ArithmeticError AssertionError AttributeError
BufferError EOFError FloatingPointError GeneratorExit ImportError ModuleNotFoundError
IndexError KeyError KeyboardInterrupt LookupError MemoryError NameError NotImplementedError
OSError OverflowError RecursionError ReferenceError RuntimeError StopAsyncIteration
StopIteration SyntaxError SystemError SystemExit TabError TimeoutError TypeError
UnboundLocalError UnicodeDecodeError UnicodeEncodeError UnicodeError UnicodeTranslateError
ValueError ZeroDivisionError exit quit copyright credits license Ellipsis NotImplemented
FileNotFoundError FileExistsError PermissionError IsADirectoryError NotADirectoryError
FileExistsError InterruptedError BlockingIOError ChildProcessError ConnectionError
BrokenPipeError ConnectionAbortedError ConnectionRefusedError ConnectionResetError
ProcessLookupError TimeoutError UnicodeEncodeError UnicodeTranslateError Warning
UserWarning DeprecationWarning PendingDeprecationWarning RuntimeWarning
FutureWarning ImportWarning UnicodeWarning BytesWarning ResourceWarning
SyntaxWarning NameWarning RecursionWarning StopAsyncIteration GeneratorExit
SystemExit KeyboardInterrupt BaseExceptionGroup ExceptionGroup
bytearray bytes classmethod staticmethod property dict set frozenset list tuple str""".split())

# py2 builtins that py3 still provides on some platforms (WindowsError is an
# OSError alias on Windows) and that compat code references deliberately in
# platform-guarded branches. pyflakes treats these as known names; so does
# drift — a deliberate compat name is not a typo (field test #8: dateutil's
# `except WindowsError:` in tz/win.py and tz/tz.py flagged as phantom).
KNOWN_COMPAT_NAMES = frozenset({"WindowsError"})


@dataclass
class Finding:
    rule: str
    severity: str  # error | warning
    file: str
    line: int
    message: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class _Sig:
    params: Set[str] = field(default_factory=set)
    has_var_kw: bool = False
    location: Optional[Tuple[str, int]] = None
    bases: List[str] = field(default_factory=list)


ENV_DOC_NAMES = {".env", ".env.example"}

# Names Sphinx injects into docs/conf.py before exec'ing it. Without these,
# every conf.py that touches `tags` looks like a NameError (streamlink field test).
SPHINX_CONF_GLOBALS = {"tags"}


def _collect_project_files(paths: List[str]) -> Tuple[List[Path], List[str]]:
    """Walk inputs, applying SKIP_DIRS to root-relative path parts only.

    Returns (files, notes). Matching used to test every absolute path part,
    so scanning a tree rooted under a dir literally named site-packages /
    venv / .tox silently zero-scanned and reported a clean bill (review F2).
    A directory whose Python files were ALL consumed by skip dirs gets a
    loud note: a scan that reads zero files must never report clean.
    """
    files: List[Path] = []
    notes: List[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file():
            if p.suffix == ".py" or p.name in ENV_DOC_NAMES:
                files.append(p)
        elif p.is_dir():
            present = 0
            chosen: List[Path] = []
            for f in sorted(p.rglob("*")):
                if not f.is_file():
                    continue
                if f.suffix != ".py" and f.name not in ENV_DOC_NAMES:
                    continue
                present += 1
                rel = f.relative_to(p)
                if any(part in SKIP_DIRS for part in rel.parts):
                    continue
                chosen.append(f)
            if present and not chosen:
                notes.append(
                    f"drift: nothing scanned under {p}: {present} Python file(s) "
                    f"found but every path matched a skip dir "
                    f"(site-packages/venv/.tox/dist/...). Refine the path; "
                    f"a zero-file scan is not a clean bill."
                )
            files.extend(chosen)
    return files, notes


def _parse(p: Path) -> Optional[ast.Module]:
    try:
        return ast.parse(p.read_text(encoding="utf-8", errors="replace"), filename=str(p))
    except SyntaxError:
        return None


def _sig_from_args(a: ast.arguments) -> _Sig:
    params = {x.arg for x in a.args} | {x.arg for x in a.kwonlyargs}
    return _Sig(params=params, has_var_kw=a.kwarg is not None)


def _init_sig(cls_node: ast.ClassDef) -> Optional[_Sig]:
    for n in cls_node.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__init__":
            return _sig_from_args(n.args)
    return None


def _recv_name(node) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _add_target_names(node, into: Set[str]) -> None:
    if isinstance(node, ast.Name):
        into.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for e in node.elts:
            _add_target_names(e, into)
    elif isinstance(node, ast.Starred):
        _add_target_names(node.value, into)


def _add_match_names(node, into: Set[str]) -> None:
    """Collect names bound by a `match` pattern.

    `case host, *_ if ...` binds `host`; `case [a] as whole` binds both.
    For `case a | b:` only names bound by EVERY alternative are definitely
    bound (Python lets you write it, then raises at use if the other branch
    matched) — so use the intersection.
    """
    if isinstance(node, ast.MatchAs):
        # `case [a] as whole:` — recurse into the wrapped pattern, then bind
        # the `as` name. Older/newer ASTs differ (pattern vs patterns); both
        # handled (v0.1.6).
        for p in getattr(node, "patterns", None) or []:
            _add_match_names(p, into)
        if getattr(node, "pattern", None) is not None:
            _add_match_names(node.pattern, into)
        if node.name:
            into.add(node.name)
    elif isinstance(node, ast.MatchStar):
        if node.name:
            into.add(node.name)
    elif isinstance(node, ast.MatchMapping):
        # AST shape differs across versions: newer keeps keys separate and
        # `patterns` flat (a dict pattern crashed here before v0.1.6); older
        # packs (key, pattern) pairs. Keys are never bindings either way.
        for p in node.patterns:
            if isinstance(p, tuple):
                _add_match_names(p[1], into)
            else:
                _add_match_names(p, into)
        if node.rest:
            into.add(node.rest)
    elif isinstance(node, ast.MatchSequence):
        for p in node.patterns:
            _add_match_names(p, into)
    elif isinstance(node, ast.MatchOr):
        per: List[Set[str]] = []
        for p in node.patterns:
            s: Set[str] = set()
            _add_match_names(p, s)
            per.append(s)
        if per:
            common = set(per[0])
            for s in per[1:]:
                common &= s
            into |= common
    elif isinstance(node, ast.MatchClass):
        for p in node.patterns:
            _add_match_names(p, into)
        for p in node.kwd_patterns:
            _add_match_names(p, into)


def _walk_with_parent(tree):
    stack = [(tree, None)]
    while stack:
        node, parent = stack.pop()
        yield node, parent
        for child in reversed(list(ast.iter_child_nodes(node))):
            stack.append((child, node))


def _normalize_rules(spec: str) -> Optional[List[str]]:
    """Normalize a --rules spec to R-codes; None if any token is unknown.

    Accepts case-insensitive codes (R3) and descriptive names (magic_number).
    Empty tokens are skipped; an all-empty spec means all rules.
    """
    out: List[str] = []
    for tok in spec.split(","):
        t = tok.strip()
        if not t:
            continue
        up = t.upper()
        if up in RULE_ALIASES:
            out.append(up)
            continue
        for code, name in RULE_ALIASES.items():
            if name.upper() == up:
                out.append(code)
                break
        else:
            return None
    return out or list(RULE_ALIASES)


def analyze(paths: List[str], rules: str = "R1,R2,R3,R4") -> Tuple[List[Finding], List[str]]:
    """Run drift over paths. Returns (findings, notes)."""
    normalized = _normalize_rules(rules)
    if normalized is None:
        raise ValueError(
            f"unknown rule in {rules!r}; valid: "
            + ", ".join(f"{c} ({n})" for c, n in RULE_ALIASES.items())
        )
    wanted = set(normalized)
    findings: List[Finding] = []

    files, collect_notes = _collect_project_files(paths)
    notes: List[str] = list(collect_notes)

    trees: Dict[Path, ast.Module] = {}
    for p in files:
        if p.suffix != ".py":
            continue
        t = _parse(p)
        if t is None:
            notes.append(f"drift: skipping {p} (could not parse)")
            continue
        trees[p] = t

    class_sigs: Dict[str, _Sig] = {}
    func_sigs: Dict[str, _Sig] = {}
    class_methods: Dict[str, Dict[str, _Sig]] = {}
    class_bases: Dict[str, List[str]] = {}
    ambiguous: Set[str] = set()
    # Per-file structures for import-aware R1 resolution (v0.1.4).
    file_funcs: Dict[Path, Dict[str, _Sig]] = {}
    file_classes: Dict[Path, Dict[str, _Sig]] = {}
    # local name -> (import level, module, real name); module None for `from . import x`
    file_imports: Dict[Path, Dict[str, Tuple[int, Optional[str], str]]] = {}
    star_files: Set[Path] = set()
    fixture_defs: Set[Tuple[Path, str]] = set()  # @pytest.fixture-decorated module-level funcs
    roots = [Path(x) for x in paths if Path(x).is_dir()]

    for p, t in trees.items():
        for node in ast.walk(t):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    file_imports.setdefault(p, {})[local] = (0, alias.name, "")
            elif isinstance(node, ast.ImportFrom):
                if any(a.name == "*" for a in node.names):
                    star_files.add(p)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    file_imports.setdefault(p, {})[local] = (node.level, node.module, alias.name)

    for p, t in trees.items():
        file_funcs[p] = {}
        file_classes[p] = {}
        for n in t.body:
            if isinstance(n, ast.ClassDef):
                class_bases[n.name] = [b.id for b in n.bases if isinstance(b, ast.Name)]
                methods: Dict[str, _Sig] = {}
                for sub in n.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        ms = _sig_from_args(sub.args)
                        ms.location = (str(p), sub.lineno)
                        methods[sub.name] = ms
                if n.name in class_methods:
                    ambiguous.add(n.name)
                else:
                    class_methods[n.name] = methods
                s = _init_sig(n)
                if s is not None:
                    s.location = (str(p), n.lineno)
                    s.bases = [b.id for b in n.bases if isinstance(b, ast.Name)]
                    file_classes[p][n.name] = s
                    if n.name in class_sigs:
                        ambiguous.add(n.name)
                    else:
                        class_sigs[n.name] = s
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                s = _sig_from_args(n.args)
                s.location = (str(p), n.lineno)
                file_funcs[p][n.name] = s
                if any(_is_fixture_decorator(d) for d in n.decorator_list):
                    fixture_defs.add((p, n.name))
                if n.name in func_sigs:
                    ambiguous.add(n.name)
                else:
                    func_sigs[n.name] = s

    for name, s in class_sigs.items():
        for base in s.bases:
            if base in class_sigs and base != name and base not in ambiguous:
                s.params |= class_sigs[base].params
                s.has_var_kw = s.has_var_kw or class_sigs[base].has_var_kw

    # Inherit method signatures through class bases so self.<method>(...) calls
    # on a subclass resolve against methods defined on its parent.
    for name, methods in class_methods.items():
        for base in class_bases.get(name, []):
            if base in class_methods and base != name and base not in ambiguous:
                for mname, msig in class_methods[base].items():
                    if mname not in methods:
                        methods[mname] = msig

    if "R1" in wanted:
        _check_r1(trees, class_sigs, func_sigs, class_methods, ambiguous, findings,
                  file_funcs, file_classes, file_imports, star_files, fixture_defs, roots)
    if "R2" in wanted:
        _check_r2(trees, files, findings)
    if "R3" in wanted:
        _check_r3(trees, findings)
    if "R4" in wanted:
        _check_r4(trees, findings, roots)

    findings.sort(key=lambda f: (f.file, f.line, f.rule, f.message))
    return findings, notes


# ---------------------------------------------------------------- R1

def _is_fixture_decorator(d) -> bool:
    """True when a decorator node is `@fixture` / `@pytest.fixture(...)`."""
    f = d.func if isinstance(d, ast.Call) else d
    if isinstance(f, ast.Name):
        return f.id == "fixture"
    if isinstance(f, ast.Attribute):
        return f.attr == "fixture"
    return False


def _find_module_file(level: int, module: Optional[str], p: Path,
                      roots: List[Path], trees) -> Optional[Path]:
    """Locate the scanned file for a module (relative or absolute).

    Returns None when the module is external (not under the scanned roots) —
    callers must then SKIP the check instead of guessing at a same-named
    function elsewhere in the project (v0.1.4: import-aware resolution).
    The imported symbol itself is looked up in that file's module-level defs.
    """
    if level > 0:
        d = p.parent
        for _ in range(level - 1):
            d = d.parent
        parts = module.split(".") if module else []
        base = d.joinpath(*parts)
        for c in (base.with_suffix(".py"), base / "__init__.py"):
            if c in trees:
                return c
        return None
    parts = module.split(".")
    for root in roots:
        base = root.joinpath(*parts)
        for c in (base.with_suffix(".py"), base / "__init__.py"):
            if c in trees:
                return c
    return None


def _check_r1(trees, class_sigs, func_sigs, class_methods, ambiguous, findings,
              file_funcs, file_classes, file_imports, star_files, fixture_defs, roots) -> None:
    for p, t in trees.items():
        parent_map = {child: parent for child, parent in _walk_with_parent(t)}

        def enclosing_class(node) -> Optional[str]:
            par = parent_map.get(node)
            while par is not None:
                if isinstance(par, ast.ClassDef):
                    return par.name
                par = parent_map.get(par)
            return None

        def is_fixture(sig, name) -> bool:
            return sig.location is not None and (Path(sig.location[0]), name) in fixture_defs

        for node in ast.walk(t):
            if not isinstance(node, ast.Call):
                continue
            sig = None
            # A self./cls. call resolves against the enclosing class's own
            # method first — a same-named module-level function is a different
            # callee and must not shadow it (v0.1.3 fix).
            if (isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in ("self", "cls")):
                cls_name = enclosing_class(node)
                if cls_name is not None and cls_name not in ambiguous:
                    sig = class_methods.get(cls_name, {}).get(node.func.attr)
            if sig is None and isinstance(node.func, ast.Attribute):
                # ClassName.method(...) is resolvable; any other receiver
                # (unittest.main, obj.x) cannot be resolved statically — never
                # guess against module-level functions, that only manufactures
                # false positives (v0.1.3 fix).
                recv = node.func.value
                if isinstance(recv, ast.Name) and recv.id in class_methods and recv.id not in ambiguous:
                    sig = class_methods[recv.id].get(node.func.attr)
                else:
                    continue
            if sig is None:
                if not isinstance(node.func, ast.Name):
                    continue
                target = node.func.id
                if not target or target in ambiguous:
                    continue
                imp = file_imports.get(p, {}).get(target)
                if imp is not None:
                    level, module, real = imp
                    if not real:
                        continue  # `import x` binds a module, not a callable
                    mfile = _find_module_file(level, module, p, roots, trees)
                    if mfile is None:
                        continue  # external library — cannot verify, never guess
                    if real in file_funcs.get(mfile, {}):
                        sig = file_funcs[mfile][real]
                    elif real in file_classes.get(mfile, {}):
                        sig = file_classes[mfile][real]
                    else:
                        continue  # re-exported/star-imported — cannot verify
                elif target in file_funcs.get(p, {}):
                    sig = file_funcs[p][target]
                elif target in file_classes.get(p, {}):
                    sig = file_classes[p][target]
                else:
                    sig = class_sigs.get(target) or func_sigs.get(target)
                    if sig is not None and is_fixture(sig, target):
                        # pytest fixtures are injected by name, never called —
                        # a direct call to that name is a different callee
                        # (usually the fixture's returned closure).
                        continue
            if sig is None:
                continue
            call_name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                if kw.arg not in sig.params and not sig.has_var_kw:
                    where = f"{sig.location[0]}:{sig.location[1]}" if sig.location else "unknown location"
                    findings.append(Finding(
                        "unexpected_kwarg", "error", str(p), node.lineno,
                        f"{call_name}() called with unexpected keyword '{kw.arg}' "
                        f"(callee at {where} does not accept it; partial patch apply?)",
                    ))


# ---------------------------------------------------------------- R2

def _config_source(node):
    """Classify a config-producing call.

    Returns "external" when the values come from outside the scanned code
    (a JSON/YAML/TOML file or the process environment), ("inline", keys) when
    a json.loads literal defines the keys right here, or None when the call
    is not a config loader at all.
    """
    if not isinstance(node, ast.Call):
        return None
    f = node.func
    loader = None
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        m = f.value.id
        if m == "json" and f.attr in ("load", "loads"):
            loader = "json"
        elif m == "yaml" and f.attr in ("load", "safe_load", "full_load"):
            loader = "yaml"
        elif m == "tomllib" and f.attr == "load":
            loader = "toml"
    elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute):
        if f.value.attr == "environ" and f.attr == "copy":
            return "external"  # dict(os.environ) / os.environ.copy()
    elif isinstance(f, ast.Name) and f.id == "dict":
        if node.args and isinstance(node.args[0], ast.Attribute) and node.args[0].attr == "environ":
            return "external"
    if loader is None:
        return None
    # A literal string argument means the config is defined inline in code.
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        try:
            data = json.loads(node.args[0].value)
        except Exception:
            return None
        if isinstance(data, dict):
            keys = {k for k in data if isinstance(k, str)}
            return ("inline", keys) if keys else None
        return None
    return "external"


def _is_env_payload(d) -> bool:
    """True when a dict literal merges the process environment
    ({**os.environ, "LANG": "C.UTF-8"}). That builds a child-process env
    payload, not internal config — the keys are environment data (isort
    field test #11: LANG in such a payload was flagged dead config).
    Environment payloads are data, not config (Sarah's data rule)."""
    if not isinstance(d, ast.Dict):
        return False
    for k, v in zip(d.keys, d.values):
        if k is not None:  # a **unpack slot (star-unpack keys are None)
            continue
        if isinstance(v, ast.Name) and v.id == "environ":
            return True
        if (isinstance(v, ast.Attribute) and v.attr == "environ"
                and isinstance(v.value, ast.Name) and v.value.id == "os"):
            return True
    return False


def _check_r2(trees, files, findings) -> None:
    defined_locs: Dict[str, List[Tuple[str, int]]] = {}
    read_locs: Dict[str, List[Tuple[str, int]]] = {}
    chain_read_locs: Dict[str, List[Tuple[str, int]]] = {}  # reads through X.attr receivers
    soft_read_locs: Dict[str, List[Tuple[str, int]]] = {}  # .get(k, default): explicit fallback
    optional_read_locs: Dict[str, List[Tuple[str, int]]] = {}  # reads of keys this scope treats as optional (presence-tested / fallback-read)
    list_read_locs: Dict[str, List[Tuple[str, int]]] = {}  # get_val([k1, k2], d) style helpers
    attr_read_locs: Dict[str, List[Tuple[str, int]]] = {}  # config.attr reads: proof-of-life only
    ext_read_locs: Dict[str, List[Tuple[str, int]]] = {}
    env_read_locs: Dict[str, List[Tuple[str, int]]] = {}
    env_doc: Set[str] = set()
    has_env_doc = False
    # v0.1.23: a dynamic-keyed read (CONFIG_SECTIONS[name], cfg.get(expr))
    # can hit ANY key of that dict, so none of its keys is provably dead.
    # dict_def_keys maps (file, def-name) -> keys defined in dict literals
    # under that name; dyn_read_names holds which def-names got a dynamic
    # read (isort FT11: 5 CONFIG_SECTIONS keys flagged dead while every
    # read at settings.py:317/756/796 used a variable key).
    dict_def_keys: Dict[Tuple[str, str], Set[str]] = {}
    dyn_read_names: Set[Tuple[str, str]] = set()
    # Names bound to a FULLY KNOWN key set in-file: a dict literal, an inline
    # json.loads('{...}'), or a literal-returning function (FT12). Only for
    # these is a missing key a PROVABLE ghost — subscript/update/setdefault
    # writes never enumerate the dict, so they don't count (pelican's
    # `settings` param is written via subscripts; its contract stays external).
    dict_literal_names: Set[Tuple[str, str]] = set()
    # Functions whose body is a bare `return {dict literal}` (pyjwt field
    # test: PyJWS/PyJWT build `self.options = self._get_default_options()`
    # from such a method). Their keys define config — without this, every
    # read through self.options was flagged read-but-never-defined.
    literal_returners: Dict[str, Set[str]] = {}
    for _p in files:
        if _p.suffix != ".py":
            continue
        if (_p.name.startswith("test") or _p.name.endswith("_test.py")
                or _p.name == "conftest.py" or "tests" in _p.parts):
            continue
        _t = trees.get(_p)
        if _t is None:
            continue
        for _node in ast.walk(_t):
            if not isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = _node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]  # docstring
            if len(body) != 1 or not isinstance(body[0], ast.Return):
                continue
            ret = body[0].value
            if not isinstance(ret, ast.Dict):
                continue
            keys: Set[str] = set()
            ok = True
            for k in ret.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
                else:
                    ok = False
                    break
            for v in ret.values:
                if isinstance(v, (ast.Call, ast.Subscript)):
                    ok = False  # derived dict, not a defaults literal
                    break
            if ok and keys:
                literal_returners.setdefault(_node.name, set()).update(keys)
    # Config aliases and externally-loaded config names, scoped per
    # (file, enclosing function) so a loop variable reusing the same name in
    # another function is never mistaken for a config object.
    aliases: Dict[Tuple[str, Optional[int]], Set[str]] = {}
    ext_names: Dict[Tuple[str, Optional[int]], Set[str]] = {}
    # Names assigned from a non-config call in a scope (e.g. `options =
    # fetch_thing()`) — a plain local dict, NOT a config object, even though
    # the name looks config-ish (streamlink mdstrm.py field-test FP).
    plain_vars: Dict[Tuple[str, Optional[int]], Set[str]] = {}
    # Keys this (file, scope) treats as optional: presence-tested (`k in
    # cfg`) or fallback-read (.get(k[, default])). Bare reads of such keys
    # demote to warnings — absence is handled, never a silent-default error
    # (pelican migrations + optional settings, FT12).
    optional_keys: Dict[Tuple[str, Optional[int]], Set[str]] = {}

    def cfg_target(tgt) -> bool:
        # config-ish assignment target: config-named bare name OR a
        # config-named attribute (`self.options = ...`, pyjwt style).
        if isinstance(tgt, ast.Name):
            return _is_config_name(tgt.id)
        if isinstance(tgt, ast.Attribute):
            return _is_config_name(tgt.attr)
        return False

    def dyn_def_name(tgt) -> Optional[str]:
        """Receiver/target -> the name its dict-literal defs register under:
        bare Name (CONFIG_SECTIONS) or the attribute name for self.options /
        X.config-style targets (v0.1.23). Ties dynamic reads to the defs
        they could hit."""
        if isinstance(tgt, ast.Name):
            return tgt.id
        if isinstance(tgt, ast.Attribute):
            return tgt.attr
        return None

    def add_literal_returner_defs(node_value, tgts, fkey, lineno) -> bool:
        """When a call resolves to a literal-returning function and at least
        one target is config-ish, register the literal's keys as definitions.
        Returns True when defs were added (the call is a config source, so
        the target must not be marked plain_vars)."""
        if not isinstance(node_value, ast.Call):
            return False
        f = node_value.func
        name = (f.id if isinstance(f, ast.Name)
                else f.attr if isinstance(f, ast.Attribute) else "")
        keys = literal_returners.get(name)
        if not keys:
            return False
        hit = False
        for tgt in tgts:
            if cfg_target(tgt):
                hit = True
                for k in keys:
                    add_def(k, fkey, lineno)
                dn = dyn_def_name(tgt)
                if dn:
                    dict_def_keys.setdefault((fkey, dn), set()).update(keys)
                    dict_literal_names.add((fkey, dn))
        return hit

    def norm(k: str) -> str:
        # Config keys are routinely normalized between dash and underscore
        # forms (streamlink Options: "Option names are normalized by replacing
        # '_' with '-'"; argparse dests do the reverse). Treat them as one key.
        return k.replace("_", "-")

    def add_def(k: str, fkey: str, lineno: int) -> None:
        defined_locs.setdefault(k, []).append((fkey, lineno))

    def add_read(k: str, fkey: str, lineno: int, bucket: Dict[str, List[Tuple[str, int]]]) -> None:
        bucket.setdefault(k, []).append((fkey, lineno))

    def scope_key(node) -> Optional[int]:
        # nearest enclosing function id (None for module/class level)
        p = parent_map.get(node)
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return id(p)
            p = parent_map.get(p)
        return None

    def shadowed(node, name: str) -> bool:
        # True when `name` is bound by an enclosing comprehension target
        # (e.g. `for s in signals`), so `s['type']` there is NOT a config read.
        p = parent_map.get(node)
        while p is not None:
            if isinstance(p, ast.comprehension):
                names: Set[str] = set()
                _add_target_names(p.target, names)
                if name in names:
                    return True
            elif isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                return False
            p = parent_map.get(p)
        return False

    def is_cfg(recv: str, node) -> bool:
        key = (fkey, scope_key(node))
        if recv in aliases.get(key, set()) and not shadowed(node, recv):
            return True
        return (_is_config_name(recv)
                and recv not in plain_vars.get(key, set())
                and not shadowed(node, recv))

    def receiver_root(node) -> Optional[str]:
        # Root of a receiver chain: `settings` -> settings, `env.config` -> env,
        # `self.state.settings` -> self, `lexer.options` -> lexer.
        n = node
        while isinstance(n, ast.Attribute):
            n = n.value
        if isinstance(n, ast.Name):
            return n.id
        return None

    def self_is_cfg(node) -> bool:
        # Bare `self` is a config receiver only inside a config class: a
        # config-named class (Config, Settings, ...) or a class carrying a
        # DEFAULTS-style dict (httpie field-test: Config.default_options is
        # read through self['default_options'], which was counted dead).
        p = parent_map.get(node)
        while p is not None:
            if isinstance(p, ast.ClassDef):
                if _is_config_name(p.name):
                    return True
                for sub in p.body:
                    if isinstance(sub, (ast.Assign, ast.AnnAssign)):
                        if not isinstance(sub.value, ast.Dict):
                            continue
                        tgts = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                        if any(isinstance(t, ast.Name) and _is_config_name(t.id) for t in tgts):
                            return True
                return False
            p = parent_map.get(p)
        return False

    def recv_cfg(recv_node, node) -> bool:
        """True when a receiver node refers to a config object.

        Bare name: config-ish or an alias of one (is_cfg). Attribute chain
        (X.config, self.state.settings, lexer.options): the chain ROOT must
        be config-ish, or self/cls with a config-ish TAIL. `lexer.options` is
        a pygments lexer option dict, not the app config (httpie field test).
        """
        if isinstance(recv_node, ast.Name):
            if recv_node.id in ("self", "cls"):
                return self_is_cfg(recv_node)
            return is_cfg(recv_node.id, node)
        if isinstance(recv_node, ast.Attribute):
            root = receiver_root(recv_node)
            if root is None:
                return False
            if root in ("self", "cls"):
                return is_cfg(_recv_name(recv_node), node)
            return is_cfg(root, node)
        return False

    def binding_source_is_configy(expr, node) -> bool:
        """Mirror of the Assign/Call configy test for with/for binding
        sources: a config-y callee (`Config()`, `make_options()`) or a
        config-ish receiver (`for x in self.options`) keeps the bound name's
        config-ness; anything else demotes it to a plain local (v0.1.11)."""
        if isinstance(expr, ast.Call):
            f = expr.func
            callee = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            callee_low = callee.lower()
            return (callee_low in CONFIG_NAMES
                    or any(callee_low.endswith(w) for w in CONFIG_NAMES))
        if isinstance(expr, (ast.Name, ast.Attribute)):
            return recv_cfg(expr, node)
        return False

    for p in files:
        if p.suffix != ".py":
            if p.name in ENV_DOC_NAMES:
                has_env_doc = True
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    m = ENV_KEY_RE.match(line)
                    if m:
                        env_doc.add(m.group(1))
            continue
        t = trees.get(p)
        if t is None:
            continue
        if (p.name.startswith("test") or p.name.endswith("_test.py") or p.name == "conftest.py"
                or "tests" in p.parts):
            # R2 skips test files: they deliberately read missing keys and
            # assert dead config — both look like drift to R2 but aren't.
            continue
        fkey = str(p)
        parent_map = {child: parent for child, parent in _walk_with_parent(t)}
        # Document-order walk (v0.1.25, pelican FT12): ast.walk is
        # breadth-first, so with several reads of one ghost key the engine
        # reported a depth-arbitrary line while the JS engine reported the
        # source-first read. Parity needs the same (file, line) either way.
        for node, _parent in _walk_with_parent(t):
            skey = (fkey, scope_key(node))
            if isinstance(node, ast.Assign):
                env_payload = isinstance(node.value, ast.Dict) and _is_env_payload(node.value)
                if env_payload:
                    # {**os.environ, "LANG": ...} builds a child-process env
                    # payload: data, not config (isort FT11: LANG flagged dead).
                    # Demote the target so later env.get(...) reads never
                    # register as config reads either.
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and _is_config_name(tgt.id):
                            plain_vars.setdefault(skey, set()).add(tgt.id)
                if isinstance(node.value, ast.Dict) and not env_payload:
                    # Handler map: {key: callable} — getter/setter dispatch tables
                    # (streamlink _MAP_GETTERS/_MAP_SETTERS). Keys are wired:
                    # defined and consumed by the machinery, so they count as
                    # both defined and read.
                    callable_map = bool(node.value.keys) and all(
                        isinstance(v, (ast.Name, ast.Attribute, ast.Call)) for v in node.value.values
                    )
                    for tgt in node.targets:
                        if cfg_target(tgt):
                            dn = dyn_def_name(tgt)
                            for k in node.value.keys:
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    add_def(k.value, fkey, node.lineno)
                                    if dn:
                                        dict_def_keys.setdefault((fkey, dn), set()).add(k.value)
                                        dict_literal_names.add((fkey, dn))
                                    if callable_map:
                                        add_read(k.value, fkey, node.lineno, read_locs)
                for tgt in node.targets:
                    if (isinstance(tgt, ast.Subscript)
                            and isinstance(tgt.slice, ast.Constant)
                            and isinstance(tgt.slice.value, str)):
                        if recv_cfg(tgt.value, node):
                            add_def(tgt.slice.value, fkey, node.lineno)
                            dn = dyn_def_name(tgt.value)
                            if dn:
                                dict_def_keys.setdefault((fkey, dn), set()).add(tgt.slice.value)
                src = _config_source(node.value)
                if src is not None and not env_payload:
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name) and _is_config_name(tgt.id):
                            if src == "external":
                                ext_names.setdefault(skey, set()).add(tgt.id)
                            elif src[0] == "inline":
                                for k in src[1]:
                                    add_def(k, fkey, node.lineno)
                                dict_def_keys.setdefault((fkey, tgt.id), set()).update(src[1])
                                dict_literal_names.add((fkey, tgt.id))
                elif isinstance(node.value, (ast.Name, ast.Attribute)):
                    src_name = receiver_root(node.value)
                    if src_name and recv_cfg(node.value, node):
                        # alias: settings = cfg — inherit config-ness (and external-ness)
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name):
                                aliases.setdefault(skey, set()).add(tgt.id)
                                plain_vars.get(skey, set()).discard(tgt.id)
                                if src_name in ext_names.get(skey, set()):
                                    ext_names.setdefault(skey, set()).add(tgt.id)
                elif isinstance(node.value, ast.Call):
                    lit_hit = add_literal_returner_defs(node.value, node.targets, fkey, node.lineno)
                    # `options = fetch(...)` — a plain local dict. Only calls
                    # whose callee is itself config-ish (Options, Settings, ...)
                    # keep config-ness; those are handled above.
                    f = node.value.func
                    callee = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                    callee_low = callee.lower()
                    configy = (callee_low in CONFIG_NAMES
                               or any(callee_low.endswith(w) for w in CONFIG_NAMES))
                    # dict(cfg) / dict(cfg.items()) copies are still config
                    dict_copy_cfg = False
                    if callee == "dict" and node.value.args and isinstance(node.value.args[0], (ast.Name, ast.Attribute)):
                        src_name = receiver_root(node.value.args[0])
                        if src_name and recv_cfg(node.value.args[0], node):
                            configy = True
                            dict_copy_cfg = True
                    if not configy and not lit_hit:
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name) and _is_config_name(tgt.id):
                                plain_vars.setdefault(skey, set()).add(tgt.id)
                    elif dict_copy_cfg:
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name):
                                aliases.setdefault(skey, set()).add(tgt.id)
                                plain_vars.get(skey, set()).discard(tgt.id)
                                if src_name in ext_names.get(skey, set()):
                                    ext_names.setdefault(skey, set()).add(tgt.id)
            elif isinstance(node, ast.AnnAssign):
                env_payload = isinstance(node.value, ast.Dict) and _is_env_payload(node.value)
                if env_payload:
                    if isinstance(node.target, ast.Name) and _is_config_name(node.target.id):
                        plain_vars.setdefault(skey, set()).add(node.target.id)
                if isinstance(node.value, ast.Dict) and not env_payload:
                    callable_map = bool(node.value.keys) and all(
                        isinstance(v, (ast.Name, ast.Attribute, ast.Call)) for v in node.value.values
                    )
                    if cfg_target(node.target):
                        dn = dyn_def_name(node.target)
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                add_def(k.value, fkey, node.lineno)
                                if dn:
                                    dict_def_keys.setdefault((fkey, dn), set()).add(k.value)
                                    dict_literal_names.add((fkey, dn))
                                if callable_map:
                                    add_read(k.value, fkey, node.lineno, read_locs)
                if isinstance(node.value, ast.Call):
                    add_literal_returner_defs(node.value, [node.target], fkey, node.lineno)
                if (node.value is not None and isinstance(node.target, ast.Name)
                        and _is_config_name(node.target.id) and not env_payload):
                    src = _config_source(node.value)
                    if src == "external":
                        ext_names.setdefault(skey, set()).add(node.target.id)
                    elif src is not None and src[0] == "inline":
                        for k in src[1]:
                            add_def(k, fkey, node.lineno)
                        dict_def_keys.setdefault((fkey, node.target.id), set()).update(src[1])
                        dict_literal_names.add((fkey, node.target.id))
            elif isinstance(node, ast.Call):
                f = node.func
                # Config definitions that are not assignments (v0.1.4):
                #   - dict literal passed to a config-ish constructor or
                #     super().__init__({...})  (streamlink options.py)
                #   - @pluginargument("key", ...) decorators (streamlink plugins)
                callee = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
                callee_low = callee.lower()
                # A config dict handed to a call is consumed by the callee —
                # renderer, builder, merge — so no key of it is provably dead
                # (pelican_quickstart CONF -> Jinja templates, FT12).
                # Exception: a config-y constructor (Config(**cfg)) is the DEF
                # side of the contract — its keys become the object's config
                # surface and can still be provably dead.
                _callee_configy = (callee_low in CONFIG_NAMES
                                   or any(callee_low.endswith(w) for w in CONFIG_NAMES))
                if not _callee_configy:
                    for _arg in list(node.args) + [kw.value for kw in node.keywords if kw.arg is None]:
                        if _arg is not None and recv_cfg(_arg, node):
                            dn = dyn_def_name(_arg)
                            if dn:
                                dyn_read_names.add((fkey, dn))
                if node.args and isinstance(node.args[0], ast.Dict):
                    is_super_init = (isinstance(f, ast.Attribute) and f.attr == "__init__"
                                     and isinstance(f.value, ast.Call)
                                     and isinstance(f.value.func, ast.Name)
                                     and f.value.func.id == "super")
                    configy = (is_super_init
                               or callee_low in CONFIG_NAMES
                               or any(callee_low.endswith(w) for w in CONFIG_NAMES))
                    if configy and not _is_env_payload(node.args[0]):
                        for k in node.args[0].keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                add_def(k.value, fkey, node.lineno)
                if callee == "pluginargument":
                    key = None
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        key = node.args[0].value
                    else:
                        for kw in node.keywords:
                            if (kw.arg in ("name", "argument_name")
                                    and isinstance(kw.value, ast.Constant)
                                    and isinstance(kw.value.value, str)):
                                key = kw.value.value
                                break
                    if key:
                        add_def(key, fkey, node.lineno)
                if callee in _SCHEMA_KEY_CALLS:
                    # Schema-call definitions (cfgv family, pre-commit FT13):
                    # Required('key', ...) / Optional('key', ...) declare a
                    # named config key. The schema IS the external contract
                    # for user config, so the key counts as defined AND read
                    # (same 'wired by the machinery' rule as callable maps):
                    # no ghost error, no dead warning on a live schema key.
                    if (node.args and isinstance(node.args[0], ast.Constant)
                            and isinstance(node.args[0].value, str)):
                        add_def(node.args[0].value, fkey, node.lineno)
                        add_read(node.args[0].value, fkey, node.lineno, read_locs)
                if isinstance(f, ast.Attribute) and f.attr in ("get", "getenv", "get_option"):
                    recv_node = f.value
                    if f.attr == "get":
                        if recv_cfg(recv_node, node):
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                k = node.args[0].value
                                if isinstance(recv_node, ast.Attribute) or (
                                        isinstance(recv_node, ast.Name)
                                        and recv_node.id in ("self", "cls")):
                                    add_read(k, fkey, node.lineno, chain_read_locs)
                                elif receiver_root(recv_node) in ext_names.get(skey, set()):
                                    add_read(k, fkey, node.lineno, ext_read_locs)
                                elif len(node.args) >= 2:
                                    # .get(k, default): explicit fallback —
                                    # the key is optional for this code.
                                    optional_keys.setdefault((fkey, scope_key(node)), set()).add(k)
                                    add_read(k, fkey, node.lineno, soft_read_locs)
                                else:
                                    # .get(k) falls back to None. When the
                                    # receiver is bound to a FULLY KNOWN key
                                    # set in-file (dict literal / inline /
                                    # literal returner), a missing key is a
                                    # provable ghost (error); on an external
                                    # receiver (param, instance) the key may
                                    # be user-set, so only a fallback warning
                                    # is honest (pelican
                                    # AUTORELOAD_IGNORE_CACHE, FT12).
                                    dn0 = dyn_def_name(recv_node)
                                    if dn0 and (fkey, dn0) in dict_literal_names:
                                        add_read(k, fkey, node.lineno, read_locs)
                                    else:
                                        optional_keys.setdefault((fkey, scope_key(node)), set()).add(k)
                                        add_read(k, fkey, node.lineno, soft_read_locs)
                            elif node.args:
                                # cfg.get(expr) — dynamic key, any member
                                # could be read (isort FT11:317).
                                dn = dyn_def_name(recv_node)
                                if dn:
                                    dyn_read_names.add((fkey, dn))
                    elif f.attr == "getenv":
                        if _recv_name(recv_node) in ("os", "environ"):
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                env_read_locs.setdefault(node.args[0].value, []).append((fkey, node.lineno))
                    else:  # get_option — the method name declares an option read
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            k = node.args[0].value
                            if _recv_name(recv_node) in ext_names.get(skey, set()):
                                add_read(k, fkey, node.lineno, ext_read_locs)
                            elif len(node.args) >= 2:
                                optional_keys.setdefault((fkey, scope_key(node)), set()).add(k)
                                add_read(k, fkey, node.lineno, soft_read_locs)
                            else:
                                dn0 = dyn_def_name(recv_node)
                                if dn0 and (fkey, dn0) in dict_literal_names:
                                    add_read(k, fkey, node.lineno, read_locs)
                                else:
                                    optional_keys.setdefault((fkey, scope_key(node)), set()).add(k)
                                    add_read(k, fkey, node.lineno, soft_read_locs)
                elif isinstance(f, ast.Attribute) and f.attr == "setdefault" and recv_cfg(f.value, node):
                    # setdefault(key, default) DEFINES the key when missing — a
                    # definition, not just a read. Without this, config built by
                    # setdefault reads as ghost keys (pelican MarkdownReader's
                    # MARKDOWN section, FT12).
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        add_def(node.args[0].value, fkey, node.lineno)
                        dn = dyn_def_name(f.value)
                        if dn:
                            dict_def_keys.setdefault((fkey, dn), set()).add(node.args[0].value)
                    if (len(node.args) > 1 and isinstance(node.args[1], ast.Dict)
                            and not _is_env_payload(node.args[1])):
                        for k in node.args[1].keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                add_def(k.value, fkey, node.lineno)
                                dn = dyn_def_name(f.value)
                                if dn:
                                    dict_def_keys.setdefault((fkey, dn), set()).add(k.value)
                elif isinstance(f, ast.Attribute) and f.attr in ("set", "set_option", "update"):
                    recv_node = f.value
                    if f.attr == "set_option" or recv_cfg(recv_node, node):
                        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                            add_def(node.args[0].value, fkey, node.lineno)
                            dn = dyn_def_name(recv_node)
                            if dn:
                                dict_def_keys.setdefault((fkey, dn), set()).add(node.args[0].value)
                        elif node.args and isinstance(node.args[0], ast.Dict) and not _is_env_payload(node.args[0]):
                            for k in node.args[0].keys:
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    add_def(k.value, fkey, node.lineno)
                                    dn = dyn_def_name(recv_node)
                                    if dn:
                                        dict_def_keys.setdefault((fkey, dn), set()).add(k.value)
                elif isinstance(f, ast.Name) and f.id == "getenv":
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        env_read_locs.setdefault(node.args[0].value, []).append((fkey, node.lineno))
                elif (isinstance(f, ast.Name) and "get" in f.id.lower()
                        and node.args and isinstance(node.args[0], ast.List)):
                    # helper-style lookup: get_val(["a", "b"], default) — proves the
                    # keys are read (kills false dead-config), but never errors on
                    # them since their source may be external.
                    for elt in node.args[0].elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            add_read(elt.value, fkey, node.lineno, list_read_locs)
            elif isinstance(node, ast.Attribute):
                # Attribute READ on a config receiver: `config.alert_threshold`
                # reads key 'alert_threshold'. Class-style config
                # (Config(**cfg)) used to look 100% dead to R2 — the walk had
                # no Attribute branch, so only .get() and subscript reads
                # registered (kanlaon_watch field case, v0.1.22). Reads land
                # in their own bucket: they kill dead-key findings but never
                # generate read-but-never-defined errors, because an unknown
                # attribute raises AttributeError (loud) rather than silently
                # defaulting, and method/property names are indistinguishable
                # statically.
                if isinstance(node.ctx, ast.Load) and recv_cfg(node.value, node):
                    add_read(node.attr, fkey, node.lineno, attr_read_locs)
            elif isinstance(node, ast.Subscript):
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    recv_node = node.value
                    if isinstance(recv_node, ast.Name) and recv_node.id == "environ":
                        env_read_locs.setdefault(node.slice.value, []).append((fkey, node.lineno))
                    elif recv_cfg(recv_node, node):
                        if isinstance(recv_node, ast.Attribute) or (
                                isinstance(recv_node, ast.Name)
                                and recv_node.id in ("self", "cls")):
                            add_read(node.slice.value, fkey, node.lineno, chain_read_locs)
                        else:
                            if node.slice.value in optional_keys.get((fkey, scope_key(node)), set()):
                                add_read(node.slice.value, fkey, node.lineno, optional_read_locs)
                            else:
                                bucket = ext_read_locs if receiver_root(recv_node) in ext_names.get(skey, set()) else read_locs
                                add_read(node.slice.value, fkey, node.lineno, bucket)
                elif not isinstance(node.slice, ast.Slice) and recv_cfg(node.value, node):
                    # Dynamic-keyed subscript on a config object
                    # (CONFIG_SECTIONS[config_file_name]): the key could be
                    # any member, so no key of that dict is provably dead
                    # (isort FT11: 5 CONFIG_SECTIONS keys flagged dead while
                    # every read used a variable key).
                    dn = dyn_def_name(node.value)
                    if dn:
                        dyn_read_names.add((fkey, dn))
            elif isinstance(node, ast.Compare) and isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                # `if "KEY" in settings:` — a presence test. The code handles
                # absence, so KEY is optional/external by contract; later bare
                # reads of it must not claim a silent default (pelican
                # deprecated-setting migrations, FT12).
                for _op, _comp in zip(node.ops, node.comparators):
                    if isinstance(_op, (ast.In, ast.NotIn)) and recv_cfg(_comp, node):
                        optional_keys.setdefault((fkey, scope_key(node)), set()).add(node.left.value)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                # `with foo() as x:` / `async with foo() as x:` bind x as a
                # plain local. A config-ISH bound name (options, config, ...)
                # is not a config receiver afterwards — aiohttp sessions and
                # file handles were flagged as config reads (v0.1.11). Only a
                # config-y constructor (`with Config() as config:`) keeps
                # config-ness, mirroring the Assign/Call rule.
                for item in node.items:
                    if item.optional_vars is None:
                        continue
                    if not binding_source_is_configy(item.context_expr, node):
                        names: Set[str] = set()
                        _add_target_names(item.optional_vars, names)
                        for n in names:
                            plain_vars.setdefault(skey, set()).add(n)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                # Loop targets are ELEMENTS of the iterable, not the config
                # object itself. A config-ISH loop variable is a plain local
                # unless the iterable is itself config-ish (v0.1.11).
                if not binding_source_is_configy(node.iter, node):
                    names: Set[str] = set()
                    _add_target_names(node.target, names)
                    for n in names:
                        plain_vars.setdefault(skey, set()).add(n)
            elif isinstance(node, ast.ExceptHandler):
                # `except X as e:` — the bound name is an exception object,
                # never a config receiver (v0.1.11).
                if node.name:
                    plain_vars.setdefault(skey, set()).add(node.name)


    if not any((defined_locs, read_locs, chain_read_locs, soft_read_locs,
                optional_read_locs, list_read_locs, ext_read_locs,
                attr_read_locs, env_read_locs)):
        return  # no in-repo config surface to drift from (FT12: soft/optional/
                # chain-only files still get their warnings)

    # Dash/underscore forms are the same key; findings keep the key as written.
    def normset(m: Dict[str, List[Tuple[str, int]]]) -> Set[str]:
        return {norm(k) for k in m}

    defined_n = normset(defined_locs)
    read_n = normset(read_locs)
    chain_n = normset(chain_read_locs)
    soft_n = normset(soft_read_locs)
    list_n = normset(list_read_locs)
    ext_n = normset(ext_read_locs)
    attr_n = normset(attr_read_locs)
    optional_n = normset(optional_read_locs)
    # v0.1.23: keys of a dict that has any dynamic-keyed read are not
    # provably dead (the dynamic read could hit any of them). Union the
    # literal keys registered under those def-names.
    dyn_covered_n = {norm(k) for (fk, dn), keys in dict_def_keys.items()
                     if (fk, dn) in dyn_read_names for k in keys}

    for k in sorted(k for k in read_locs if norm(k) not in defined_n and k not in env_doc):
        p, ln = read_locs[k][0]
        findings.append(Finding(
            "config_drift", "error", p, ln,
            f"config key '{k}' is read but never defined anywhere. It will silently default.",
        ))
    for k in sorted(k for k in chain_read_locs if norm(k) not in defined_n and k not in env_doc):
        p, ln = chain_read_locs[k][0]
        findings.append(Finding(
            "config_drift", "warning", p, ln,
            f"config key '{k}' is read through a config object whose key contract "
            f"is external (obj.config.get(...), self.get(...)) and never defined in "
            f"code — likely a user-set or externally documented key; verify the spelling.",
        ))
    for k in sorted(k for k in soft_read_locs if norm(k) not in defined_n and k not in env_doc):
        p, ln = soft_read_locs[k][0]
        findings.append(Finding(
            "config_drift", "warning", p, ln,
            f"config key '{k}' is read only with a fallback default and never defined "
            f"in code — the default always applies unless the key is set externally.",
        ))
    for k in sorted(k for k in optional_read_locs
                    if norm(k) not in defined_n and k not in env_doc
                    and k not in soft_read_locs):
        # keys already soft-flagged emit under the fallback message only —
        # one warning per key, the more specific one (FT12 readers.py
        # DEFAULT_DATE is .get-guarded AND subscript-read at the same line).
        p, ln = optional_read_locs[k][0]
        findings.append(Finding(
            "config_drift", "warning", p, ln,
            f"config key '{k}' is read where the code treats it as optional "
            f"(presence test or fallback read) but never defined in code — it only "
            f"exists when set externally; verify the spelling.",
        ))
    for k in sorted(k for k in defined_locs
                    if norm(k) not in read_n and norm(k) not in chain_n
                    and norm(k) not in soft_n and norm(k) not in optional_n
                    and norm(k) not in list_n and norm(k) not in ext_n
                    and norm(k) not in attr_n
                    and norm(k) not in dyn_covered_n
                    and k not in env_read_locs):
        p, ln = defined_locs[k][0]
        findings.append(Finding(
            "config_drift", "warning", p, ln,
            f"config key '{k}' is defined but never read. Dead config.",
        ))
    if has_env_doc:
        for k in sorted(set(env_read_locs) - set(env_doc)):
            p, ln = env_read_locs[k][0]
            findings.append(Finding(
                "config_drift", "warning", p, ln,
                f"env var '{k}' is read but not documented in .env/.env.example. "
                f"Either it is set externally (fine) or the name is a typo — check.",
            ))


# ---------------------------------------------------------------- R3

# Statement/contract nodes that end the data-collection walk: a literal
# whose chain reaches one of these without touching a collection literal
# lives in logic, not in data.
_DATA_BOUNDARY = (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign,
                  ast.Return, ast.Raise, ast.Assert, ast.Delete, ast.If,
                  ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                  ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                  ast.arguments, ast.keyword, ast.Module)


def _in_data_collection(node, parent_map) -> bool:
    """True if the literal sits inside a collection literal (List/Tuple/Set)
    anywhere up the chain before a statement boundary. Values in a
    collection are data named by the collection — a date matrix, a port
    list, a fixture — so repetition there is a corpus, not a scattered
    constant (Sarah's verify_refactor.py: Jan 21 / Jun 21 / Dec 21 flagged
    as "21 appears 3 times" — three different dates sharing a digit, not
    one constant copied three times)."""
    up = parent_map.get(node)
    while up is not None:
        if isinstance(up, (ast.List, ast.Tuple, ast.Set)):
            return True
        if isinstance(up, _DATA_BOUNDARY):
            return False
        up = parent_map.get(up)
    return False


def _in_compare_container(node, parent_map) -> bool:
    """True if node's first non-container ancestor is a comparison. That is
    the version-check idiom: (3, 0, 2) <= (major, ...) and [1, 3, 4] <
    crypto_version_list are data, not magic constants."""
    up = node
    while True:
        nxt = parent_map.get(up)
        if nxt is None:
            return False
        if isinstance(nxt, (ast.Tuple, ast.List)):
            up = nxt
            continue
        return isinstance(nxt, ast.Compare)


def _check_r3(trees, findings) -> None:
    # Families keyed by exact value, ints and integer-valued floats together
    # (7.0 == 7, so a refactor to float doesn't scatter the family). Each loc
    # carries its own display form: a uniform bucket reports `7` or `7.0` as
    # written, a mixed bucket reports both ("7 / 7.0 appears 45 times" —
    # dateutil field test #8: 44 int 7s + relativedelta's `days / 7.0` used
    # to print "7.0" at an int anchor). Ints key exactly: float() would
    # collapse 2**53 and 2**53+1 into one bucket.
    counts: Dict[Tuple[str, object], List[Tuple[str, int, str]]] = {}
    for p, t in trees.items():
        if (p.name.startswith("test") or p.name.endswith("_test.py")
                or p.name == "conftest.py" or "tests" in p.parts):
            # R3 skips test files like R2: tests deliberately repeat
            # literals as data (vectors, fixtures, key sizes) — repetition
            # there is a corpus, not an unnamed constant (pyjwt field test:
            # 65537 x6, 1024 x5, leeway 5 x3).
            continue
        parent_map = {child: parent for child, parent in _walk_with_parent(t)}
        for node, parent in _walk_with_parent(t):
            if not isinstance(node, ast.Constant):
                continue
            v = node.value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if parent is None:
                continue
            if _in_data_collection(node, parent_map):
                # literals nested in collection literals are data named by
                # the collection, not scattered magic (v0.1.13: date-matrix
                # field report — 21 x3 in a verification script was Jan 21,
                # Jun 21, Dec 21; three dates, one digit).
                continue
            if isinstance(parent, ast.Subscript) and parent.slice is node:
                continue
            if isinstance(parent, ast.Slice):
                # url[3:] slice bound — an indexing digit, not a magic constant
                continue
            if (isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.USub)):
                # -3 in x[-3] / x[-3:] — the sign is part of the index, not a
                # magic constant. CPython folds a bare -3 to Constant(-3) but
                # keeps UnaryOp(USub) inside subscripts/slices, so the digit
                # leaked into the magic tally (Aether review 2026-08-25: it
                # hit the shipped CLI, not just the browser engine).
                gp = parent_map.get(parent)
                if gp is not None and (
                        isinstance(gp, ast.Slice)
                        or (isinstance(gp, ast.Subscript) and gp.slice is parent)):
                    continue
            if isinstance(parent, ast.UnaryOp):
                # A sign wraps the literal; the STATEMENT parent still names
                # it. STD_ERROR_HANDLE = -12 — the bare 12 leaked into the
                # tally because UnaryOp, not the Assign, was the direct
                # parent (pre-commit FT13). Walk through unary +/- chains.
                up = parent_map.get(parent)
                while isinstance(up, ast.UnaryOp):
                    up = parent_map.get(up)
                if isinstance(up, (ast.Assign, ast.AnnAssign)):
                    tgts = up.targets if isinstance(up, ast.Assign) else [up.target]
                    if any(isinstance(t, ast.Name) and UPPER_NAME_RE.match(t.id)
                           for t in tgts):
                        continue
            if isinstance(parent, ast.Dict) and node in parent.keys:
                continue
            if isinstance(parent, ast.Dict) and any(v is node for v in parent.values):
                # dict values are data named by their key — the ANSI table
                # {"green": 32, ...} IS the named constant (click field test:
                # 30/32/36 from _ansi_colors were flagged AT the definition).
                continue
            if isinstance(parent, ast.keyword):
                # keyword-argument values are named by the keyword itself
                # (stacklevel=3, timeout=60) — the call site names them.
                continue
            if isinstance(parent, ast.arguments) and (
                    any(d is node for d in parent.defaults)
                    or any(d is node for d in parent.kw_defaults if d is not None)):
                # signature defaults are named by their parameter (width=36,
                # col_max=30) — a default is part of the named contract.
                continue
            if (isinstance(parent, ast.BinOp)
                    and isinstance(parent.op, (ast.LShift, ast.RShift))
                    and parent.right is node):
                # 1 << 32 bit-magnitude idiom — the shift count is the unit
                # (click field test: random.randrange(1 << 32) was flagged).
                continue
            if (isinstance(parent, ast.BinOp)
                    and isinstance(parent.op, ast.Pow)
                    and parent.right is node):
                # 2 ** 12 bit-magnitude idiom — the exponent is the unit,
                # same family as the shift counts above (pre-commit FT13:
                # max(min(..., 2 ** 17), 2 ** 12) flagged 12 x2).
                continue
            if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Mult):
                other = parent.right if parent.left is node else parent.left
                if isinstance(other, ast.Constant) and isinstance(other.value, str):
                    # '=' * 79 separator widths — the count sizes a
                    # presentation string; the string itself is the unit
                    # (pre-commit FT13: try_repo.py banners x3).
                    continue
            if isinstance(parent, (ast.Assign, ast.AnnAssign)):
                targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
                if any(isinstance(tgt, ast.Name) and UPPER_NAME_RE.match(tgt.id) for tgt in targets):
                    continue
            if isinstance(parent, ast.Tuple):
                # (3, 7) version tuples under a named constant are not magic
                up = parent_map.get(parent)
                while isinstance(up, ast.Tuple):
                    up = parent_map.get(up)
                if isinstance(up, ast.arguments):
                    # (1, 2) as a signature default is named by the param
                    continue
                if isinstance(up, (ast.Assign, ast.AnnAssign)):
                    tgts = up.targets if isinstance(up, ast.Assign) else [up.target]
                    if any(isinstance(t, ast.Name) and UPPER_NAME_RE.match(t.id) for t in tgts):
                        continue
            if _in_compare_container(node, parent_map):
                # (3, 0, 2) <= (major, minor, patch), [1, 3, 4] < ver_list:
                # tuples/lists in comparisons are version checks, not magic.
                if not isinstance(parent, ast.Compare):
                    continue
                # _ver[0] == 3 — comparing a literal against a subscript is
                # an index/version check, not a named constant's job.
                if any(isinstance(x, ast.Subscript)
                       for x in [parent.left] + list(parent.comparators)):
                    continue
                # 400 <= r.status_code < 500 — chained HTTP status ranges.
                op_names = [type(o).__name__ for o in parent.ops]
                if (len(op_names) >= 2
                        and all(o in ("Lt", "LtE", "Gt", "GtE") for o in op_names)
                        and 100 <= v <= 600 and v % 100 == 0
                        and float(v).is_integer()):
                    continue
                # len(args) > 3 / len(entry) > 3 — argument-count bounds are
                # structural: the guard states its own contract, it does not
                # scatter a constant (pre-commit FT13: hook_impl.py x2 +
                # languages/r.py x1).
                if any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                       and x.func.id == "len"
                       for x in [parent.left] + list(parent.comparators)):
                    continue
            if isinstance(v, int):
                if v in _MAGIC_STRUCTURAL_INTS:
                    continue
                key = ("int", v)   # exact: no float() collapse past 2**53
                disp = str(v)
            else:
                if v in _MAGIC_STRUCTURAL_FLOATS:
                    continue
                disp = repr(v)
                key = ("float", v)
                if v.is_integer() and abs(v) < 2**53:
                    key = ("int", int(v))   # 7.0 joins 7's family
            counts.setdefault(key, []).append((str(p), node.lineno, disp))
    for key, locs in sorted(counts.items(), key=lambda kv: kv[0][1]):
        if len(locs) >= MAGIC_MIN_COUNT:
            displays = {d for _, _, d in locs}
            shown = (" / ".join(sorted(displays)) if len(displays) > 1
                     else next(iter(displays)))
            samples = ", ".join(f"{f}:{l}" for f, l, _ in locs[:3])
            findings.append(Finding(
                "magic_number", "warning", locs[0][0], locs[0][1],
                f"{shown} appears {len(locs)} times ({samples}). Hardcoded value doing a named constant's job.",
            ))


# ---------------------------------------------------------------- R4

# Cross-file star-import resolution (v0.1.14, both engines; R4 Phase B).
# Design: docs/r4-crossfile.md

def _literal_all(value) -> Optional[Set[str]]:
    """Exact names from a static __all__ literal, else None.

    Only list/tuple/set literals of str constants count. Anything else
    (computed, augmented, unpacked) makes the module unresolvable.
    """
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return None
    out: Set[str] = set()
    for elt in value.elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            return None
        out.add(elt.value)
    return out


def _bind_names(node, into: Set[str], star_out=None) -> None:
    """Add every name bound by `node` to `into`.

    Covers all binding forms R4 tracks. ImportFrom star imports are
    reported via star_out (a list of (level, module) tuples) instead of
    being added, so callers can resolve them against the scan tree.
    """
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for tgt in targets:
            _add_target_names(tgt, into)
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        # `async for x in ...:` binds x like a plain for (v0.1.4)
        _add_target_names(node.target, into)
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        # `async with foo() as x:` — the whole streamlink
        # webbrowser/nursery FP class was this one missing branch.
        for item in node.items:
            if item.optional_vars is not None:
                _add_target_names(item.optional_vars, into)
    elif isinstance(node, ast.Match):
        for case in node.cases:
            _add_match_names(case.pattern, into)
    elif isinstance(node, ast.ExceptHandler):
        if node.name:
            into.add(node.name)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        into.add(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            for grp in (a.posonlyargs, a.args, a.kwonlyargs):
                for x in grp:
                    into.add(x.arg)
            if a.vararg:
                into.add(a.vararg.arg)
            if a.kwarg:
                into.add(a.kwarg.arg)
    elif isinstance(node, ast.Lambda):
        a = node.args
        for grp in (a.posonlyargs, a.args, a.kwonlyargs):
            for x in grp:
                into.add(x.arg)
        if a.vararg:
            into.add(a.vararg.arg)
        if a.kwarg:
            into.add(a.kwarg.arg)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            into.add(alias.asname or alias.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name == "*":
                if star_out is not None:
                    star_out.append((node.level, node.module))
            else:
                into.add(alias.asname or alias.name)
    elif isinstance(node, ast.comprehension):
        _add_target_names(node.target, into)
    elif isinstance(node, ast.NamedExpr):
        _add_target_names(node.target, into)


def _module_exports(p: Path, t: ast.Module, trees, roots,
                    memo: Dict[Path, Optional[Set[str]]]) -> Optional[Set[str]]:
    """Names a `from <this file> import *` binds at runtime.

    CPython 3.11 probe-verified: static __all__ wins exactly; otherwise
    every module-level name not starting with '_' is exported, including
    plain `import x` names; and a relative from-import also exports the
    sibling submodule name (from .helpers import * binds `helpers` too).

    Star imports inside the module resolve recursively. Returns None when
    anything is unresolvable (dynamic __all__, unknown star target, import
    cycle) so callers keep the legacy whole-file skip.
    """
    if p in memo:
        return memo[p]
    memo[p] = None  # cycle guard: re-entry means a cycle -> unresolvable
    for node in t.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(tgt, ast.Name) and tgt.id == "__all__" for tgt in targets):
                memo[p] = _literal_all(node.value)
                return memo[p]
    exports: Set[str] = set()
    star_targets: List[Tuple[int, Optional[str]]] = []
    for node in t.body:
        _bind_names(node, exports, star_targets)
        if isinstance(node, ast.ImportFrom) and node.level > 0 and node.module:
            exports.add(node.module.split(".")[0])
    for level, module in star_targets:
        target = _find_module_file(level, module, p, roots, trees)
        if target is None or target not in trees:
            memo[p] = None
            return None
        sub = _module_exports(target, trees[target], trees, roots, memo)
        if sub is None:
            memo[p] = None
            return None
        exports |= sub
    exports = {n for n in exports if not n.startswith("_")}
    memo[p] = exports
    return exports


def _check_r4(trees, findings, roots) -> None:
    memo: Dict[Path, Optional[Set[str]]] = {}
    for p, t in trees.items():
        defined: Set[str] = set()
        loads: Dict[str, List[int]] = {}
        skip_file = False
        star_targets: List[Tuple[int, Optional[str]]] = []
        for node in ast.walk(t):
            _bind_names(node, defined, star_targets)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loads.setdefault(node.id, []).append(node.lineno)
        # Resolve star imports against the scanned tree. If every target
        # resolves, its exports are exactly what the star binds; if any
        # target is external or unresolvable, keep the legacy whole-file
        # skip (partial resolution could false-positive).
        for level, module in star_targets:
            target = _find_module_file(level, module, p, roots, trees)
            if target is None or target not in trees:
                skip_file = True
                break
            sub = _module_exports(target, trees[target], trees, roots, memo)
            if sub is None:
                skip_file = True
                break
            defined |= sub
        if skip_file:
            continue
        if p.name == "conf.py" and "docs" in p.parts:
            defined |= SPHINX_CONF_GLOBALS
        for name, lines in loads.items():
            if name in defined or name in BUILTINS or name in KNOWN_COMPAT_NAMES:
                continue
            if name.startswith("__") and name.endswith("__"):
                continue
            lines = sorted(lines)  # walk order is unspecified; source order is deterministic
            findings.append(Finding(
                "phantom_name", "error", str(p), lines[0],
                f"'{name}' is used but never defined in this file "
                f"(lines {', '.join(str(x) for x in lines[:4])}). A typo like this silently defaults.",
            ))


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="drift",
        description="Find where your code and your config have drifted apart.",
    )
    ap.add_argument("paths", nargs="+", metavar="PATH", help="Python files or directories to scan")
    ap.add_argument("--rules", default="R1,R2,R3,R4", help="comma-separated rules to run (default: all)")
    ap.add_argument("--json", action="store_true", help="emit findings as JSON")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    ap.add_argument("--quiet", action="store_true", help="only print findings, no summary")
    ap.add_argument("--version", action="version", version=f"drift {VERSION}")
    args = ap.parse_args(argv)

    rules = _normalize_rules(args.rules)
    if rules is None:
        ap.error(
            f"unknown rule in --rules {args.rules!r}; valid: "
            + ", ".join(f"{c} ({n})" for c, n in RULE_ALIASES.items())
        )

    findings, notes = analyze(args.paths, rules=",".join(rules))
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    failed = bool(errors) or (args.strict and bool(warnings))

    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        for f in findings:
            print(f"[{f.severity}] {f.rule}  {f.file}:{f.line}")
            print(f"    {f.message}")
        if not args.quiet:
            print(f"\ndrift {VERSION}: {len(findings)} finding(s) "
                  f"({len(errors)} error(s), {len(warnings)} warning(s))")

    for n in notes:
        print(n, file=sys.stderr)

    # a scan that read zero files is misconfiguration, not a clean bill
    # (review F2): exit 2 like the unknown-rule guard
    if any(n.startswith("drift: nothing scanned") for n in notes):
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
