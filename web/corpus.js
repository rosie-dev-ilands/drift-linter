// Shared corpus for drift parity testing: JS engine vs Python reference.
// Each entry: { name: { filename: content } }
module.exports = {
  r1_unexpected_kwarg: {
    "a.py": "class SignalHistory:\n    def __init__(self, window, total=None):\n        pass\n",
    "b.py": "from a import SignalHistory\nsh = SignalHistory(total_r=5)\n",
  },
  r1_var_kwargs: {
    "a.py": "class Config:\n    def __init__(self, **kwargs):\n        pass\n",
    "b.py": "c = Config(anything=1)\n",
  },
  r1_declared_kwarg: {
    "a.py": "class Config:\n    def __init__(self, a, b=2):\n        pass\n",
    "b.py": "c = Config(a=1, b=3)\n",
  },
  r1_positional_only: {
    "a.py": "def f(a, /, b):\n    pass\n",
    "b.py": "f(a=1, b=2)\n",
  },
  r1_ambiguous: {
    "a.py": "class Same:\n    def __init__(self, x):\n        pass\n",
    "b.py": "class Same:\n    def __init__(self, y):\n        pass\n",
    "c.py": "s = Same(z=1)\n",
  },
  r1_same_file_and_inheritance: {
    "a.py": "class Base:\n    def __init__(self, alpha, **extra):\n        pass\n\nclass Child(Base):\n    def __init__(self, beta):\n        pass\n\nc = Child(alpha=1, beta=2, gamma=3)\nclass Lone:\n    def __init__(self, only):\n        pass\nLone(nope=1)\n",
  },
  r1_func_calls: {
    "a.py": "def greet(name, /, punctuation='!'):\n    return name + punctuation\n\ndef shout(*, loud=True):\n    pass\n\ngreet('x', punctuation='?')\nshout(loud=False)\nshout(quiet=True)\n",
  },
  r2_phantom_key: {
    "a.py": "config = {'api_key': 'x'}\nprint(config.get('missing_key'))\nprint(config.get('api_key'))\n",
  },
  r2_dead_key: {
    "a.py": "config = {'never_used': 1}\n",
  },
  r2_ok_when_used: {
    "a.py": "config = {'api_key': 'x'}\nprint(config.get('api_key'))\n",
  },
  r2_env_file: {
    ".env": "API_KEY=abc\n",
    "a.py": "import os\nk = os.getenv('API_KEY')\n",
  },
  r2_no_source: {
    "a.py": "import os\nk = os.getenv('NOPE')\n",
  },
  r2_subscript_and_environ: {
    "a.py": "import os\nsettings = {}\nsettings['host'] = 'localhost'\nsettings['port'] = 8080\nprint(os.environ['HOME'])\nprint(settings['host'])\nprint(settings['missing_port'])\n",
  },
  r2_annassign_and_names: {
    "a.py": "conf: dict = {'timeout': 5, 'retries': 3}\ncfg = {'only_defined': 1}\nprint(conf.get('timeout'))\nprint(conf.get('retries'))\nprint(conf.get('nope'))\n",
  },
  r3_repeated_literal: {
    "a.py": "x = 1.0\nz = 2.0\nif x > 0.4:\n    y = 0.4\nif z >= 0.4:\n    w = 0.4\n",
  },
  r3_named_constants: {
    "a.py": "x = 1.0\nz = 2.0\nMARGIN = 0.4\nif x > MARGIN:\n    y = MARGIN\nif z >= MARGIN:\n    w = MARGIN\n",
  },
  r3_exclusions: {
    "a.py": "d = {1: 'a', 2: 'b'}\nitems = [0, 1, 2, 3]\nx = items[1]\ny = items[2]\nz = -1\nFLAG = 7\nw = FLAG\n",
  },
  r3_ints_and_floats: {
    "a.py": "a = 8080\nb = 8080\nc = 8080\nd = 0.5\ne = 0.5\nf = 0.5\n",
  },
  r4_typo: {
    "a.py": "print(misspeled)\n",
  },
  r4_defined: {
    "a.py": "x = 1\nprint(x)\n",
  },
  r4_import_star: {
    "a.py": "from foo import *\nprint(whatever)\n",
  },
  r4_imports_params: {
    "a.py": "import os\n\ndef greet(name):\n    print('hi', name)\n\ngreet('rosie')\n",
  },
  clean_project: {
    "a.py": "import os\n\nCONFIG = {'PORT': 8080}\n\ndef start(port):\n    return os.getenv('PORT', port)\n\nstart(CONFIG['PORT'])\n",
  },
  gnarly_syntax: {
    "bot.py": `#!/usr/bin/env python3
"""Docstring with 'quotes' and "double" and \\\\ escapes."""

from __future__ import annotations
import asyncio, json, os, sys
from pathlib import Path
from typing import Dict, List, Optional

CONFIG = {
    'host': '0.0.0.0',
    'port': 8080,
    'timeout': 30,
}

RAW = r'C:\\path\\to\\nowhere'
BYTES = b'raw bytes'
F_STR = f"value={CONFIG['port']!r} and {2 + 3}"

async def fetch(url: str, *, timeout: Optional[float] = None) -> Dict:
    if timeout is None:
        timeout = 5.0
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as resp:
            return await resp.json()

def transform(items: List[int]) -> List[int]:
    out = [x * 2 for x in items if x > 0]
    squares = {x: x * x for x in items}
    uniq = {x for x in items}
    gen = (y for y in items if y % 2 == 0)
    return [n for pair in zip(out, gen) for n in pair]

def run_forever():
    tasks = []
    for i in range(10):
        tasks.append(fetch(f'http://example.com/{i}'))
    try:
        results = asyncio.run(asyncio.gather(*tasks))
    except (TimeoutError, OSError) as e:
        print(f'failed: {e}')
    else:
        print('all done', len(results))
    finally:
        print('cleanup')

def quirky():
    x = 0
    while x < 3:
        x += 1
        if x == 2:
            continue
    else:
        print('done')
    with open('f.txt') as fh, open('g.txt', 'w') as out:
        data = fh.read()
        out.write(data)
    match x:
        case 1:
            print('one')
        case _:
            print('other')

@decorator
def decorated(a, b=1, *args, **kwargs):
    return a + b

def walrus_zone(items):
    total = 0
    for it in items:
        if (n := len(it)) > 2:
            total += n
    return total

def typed_tuple() -> tuple[int, str]:
    return (1, 'a')

result = transform([1, -2, 3])
print(result, RAW, BYTES, F_STR)
`,
  },
  gnarly_no_findings: {
    "main.py": `import os

def handler(event, context=None):
    config = os.environ.get('TABLE')
    return config

def main():
    items = []
    for i in range(5):
        items.append(i * i)
    return handler({'x': 1})

if __name__ == '__main__':
    main()
`,
  },
  // v0.1.5: async bindings + R2 bucket parity (soft/ext/env reads, aliases,
  // plain vars, shadowing, norm, env docs, handler maps, super-init, options).
  r4_async_with: {
    "a.py": `import aiohttp

async def fetch(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()
`,
  },
  r4_async_for: {
    "a.py": `async def stream():
    pass

async def consume():
    async for item in stream():
        print(item)
`,
  },
  r2_soft_read: {
    "a.py": "config = {'api_key': 'x'}\nprint(config.get('missing_key', 'fallback'))\n",
  },
  // v0.1.6: match statements - captures, wildcards, guards, mapping/class/as
  // patterns, or-intersection, soft keywords (match/case as identifiers),
  // tuple subjects, and the dict-pattern crash regression.
  r4_match_seq_capture: {
    "a.py": `def handle(cmd):
    match cmd:
        case ['go', direction]:
            return direction
        case [x, y] if x > 0:
            return x + y
        case _:
            return None
`,
  },
  r4_match_mapping_rest: {
    "a.py": `def f(cmd):
    match cmd:
        case {'cmd': c, **rest}:
            return c, rest
        case {}:
            return None
`,
  },
  r4_match_class_kwd: {
    "a.py": `class Point:
    pass
Point = Point()
def f(p):
    match p:
        case Point(x=px, y=py):
            return px + py
        case Point(0, 0):
            return None
`,
  },
  r4_match_or_intersection: {
    "a.py": `def f(cmd):
    match cmd:
        case ("a", x) | ("b", x):
            return x
        case Point(y=py) | Point(z=py):
            return py
`,
  },
  r4_match_as_pattern: {
    "a.py": `def f(cmd):
    match cmd:
        case [first] as whole:
            return first, whole
`,
  },
  r4_match_value_pattern: {
    "a.py": `class Color:
    pass
Color = Color()
def f(c):
    match c:
        case Color.RED:
            return RED
        case _:
            return None
`,
  },
  r4_match_tuple_subject: {
    "a.py": `import urllib.parse
def f(meta):
    match urllib.parse.urlparse(meta).netloc.split("."), 1:
        case host, *_ if host[-2:] == ["dailymotion", "com"]:
            return host
        case _:
            return None
`,
  },
  r4_match_star_and_nested: {
    "a.py": `def f(t):
    match t:
        case [head, *mid, tail]:
            return head, mid, tail
        case (a, (b, c)):
            return a, b, c
`,
  },
  r4_match_soft_keywords: {
    "a.py": `import re
case = re.match(r"x", "x")
match = case
if match:
    print(match.group())
def case():
    return 1
`,
  },
  r2_ext_source: {
    "a.py": "import json\ncfg = json.load(open('x.json'))\nprint(cfg.get('anything'))\n",
  },
  r2_json_inline: {
    "a.py": "import json\ncfg = json.loads('{\"host\": \"x\", \"port\": 80}')\nprint(cfg.get('host'), cfg.get('port'))\n",
  },
  r2_dict_environ_copy: {
    "a.py": "import os\ncfg = dict(os.environ)\nprint(cfg.get('HOME'))\n",
  },
  r2_alias: {
    "a.py": "cfg = {'host': 'x'}\nsettings = cfg\nprint(settings.get('host'))\nprint(settings.get('nope'))\n",
  },
  r2_plain_var: {
    "a.py": "settings = {'host': 'x'}\noptions = fetch_thing()\nprint(options.get('anything'))\n",
  },
  r2_test_skip: {
    "tests/test_cfg.py": "import os\nk = os.getenv('NOPE')\nconfig = {'never_read': 1}\nprint(config.get('missing'))\n",
  },
  r2_norm: {
    "a.py": "config = {'max_retries': 3}\nprint(config.get('max-retries'))\n",
  },
  r2_env_example_doc: {
    ".env.example": "API_KEY=abc\n",
    "a.py": "import os\nk1 = os.getenv('API_KEY')\nk2 = os.getenv('SECRET')\n",
  },
  r2_handler_map: {
    "a.py": `def get_a():
    return 1

def set_a(v):
    pass

GETTERS = {'get_a': get_a, 'set_a': set_a}
`,
  },
  r2_shadowing: {
    "a.py": "groups = [{'x': 1}]\nout = [settings['x'] for settings in groups]\n",
  },
  r2_super_init: {
    "a.py": `class Base:
    def __init__(self, cfg):
        self.config = cfg

class Child(Base):
    def __init__(self):
        super().__init__({'alpha': 1})

    def show(self):
        print(self.config['alpha'])
`,
  },
  r2_options_api: {
    "a.py": "opts = {'timeout': 5}\nprint(opts.get_option('timeout'))\nopts.set_option('retries', 3)\nprint(opts.get_option('retries'))\n",
  },
  r2_pluginargument: {
    "a.py": `def pluginargument(name, **kw):
    return lambda f: f

@pluginargument('quality', default='best')
def main():
    pass

options = {'quality': 'best'}
print(options.get('quality'))
`,
  },
  r2_upper_case_config: {
    "a.py": "DEFAULT_SETTINGS = {'host': 'x'}\nprint(DEFAULT_SETTINGS.get('host'))\n",
  },
  // v0.1.5 R1: attribute calls on unresolvable receivers are never guessed
  // against module-level functions (unittest.main, obj.x); self./cls. calls
  // resolve against the enclosing class; fixture calls are closure calls.
  r1_obj_attr_skip: {
    "a.py": `class Handler:
    def __init__(self):
        pass

def handle(x):
    pass

h = Handler()
h.handle(bad=1)
`,
  },
  r1_unittest_main: {
    "a.py": `import unittest

def main(argv=None):
    pass

unittest.main(verbosity=2)
`,
  },
  r1_self_method: {
    "a.py": `class Worker:
    def run(self, x):
        pass

    def go(self):
        self.run(badkw=1)
`,
  },
  r1_fixture_closure: {
    "a.py": `import pytest

@pytest.fixture
def client():
    pass

client(badkw=1)
`,
  },
  r4_not_in: {
    "a.py": "items = [1, 2]\nout = [x for x in items if x not in (2,)]\nprint(out)\n",
  },
  // httpie field test (v0.1.7): receiver resolution for R2.
  // `lexer.options.get('precise')` is a pygments lexer option dict, not the
  // app config - skipped. `env.config.get(...)` roots at config-ish `env`, so
  // it IS a config read, but through an attribute chain: never-defined keys
  // there are warning-tier (user-set config contract), not errors.
  r2_httpie_chain_receivers: {
    "a.py": "DEFAULTS = {'theme': 'auto'}\n"
      + "def precise(lexer, precise_token, parent_token):\n"
      + "    if lexer.options.get('precise'):\n"
      + "        return precise_token\n"
      + "    return parent_token\n"
      + "def warn(env):\n"
      + "    if env.config.get('disable_update_warnings'):\n"
      + "        return None\n"
      + "def pick(env):\n"
      + "    return env.config.get('theme')\n",
  },
  // httpie field test (v0.1.7): bare self reads inside a config class count
  // as reads of that key - Config.default_options was flagged dead config
  // even though the property reads it. Reads of undefined keys through self
  // are warning-tier like chain receivers.
  r2_self_in_config_class: {
    "a.py": "class Config:\n"
      + "    DEFAULTS = {'default_options': []}\n"
      + "    @property\n"
      + "    def default_options(self):\n"
      + "        return self['default_options']\n"
      + "    def check(self):\n"
      + "        return self.get('default_options')\n"
      + "    def dev(self):\n"
      + "        return self.get('developer_mode')\n",
  },
  // httpie field test (v0.1.7): bare self in a NON-config class is not a
  // config receiver - the defined key stays dead (warning), no phantom error.
  r2_self_in_plain_class: {
    "a.py": "SETTINGS = {'a': 1}\n"
      + "class Bot:\n"
      + "    def f(self):\n"
      + "        return self['a']\n",
  },
  // httpie field test (v0.1.7): R3 noise skips - version tuples under a
  // named constant and slice bounds are not magic numbers.
  r3_version_tuple_and_slice: {
    "a.py": "MIN_SUPPORTED_PY_VERSION = (3, 7)\n"
      + "MAX_SUPPORTED_PY_VERSION = (3, 11)\n"
      + "s = 'abcd'\n"
      + "x = s[3:]\n"
      + "y = 0.4\n"
      + "if y > 0.4:\n"
      + "    z = 0.4\n",
  },
  // requests field test (v0.1.8): version tuples/lists in comparisons.
  // Three sites on purpose - without the skips this hits the repeat
  // threshold and flags, so parity exercises the rule for real.
  r3_version_compare: {
    "a.py": "major, minor, patch = map(int, ver.split('.'))\n"
      + "assert (3, 0, 2) <= (major, minor, patch) < (8, 0, 0)\n"
      + "if crypto_version_list < [1, 3, 4]:\n"
      + "    warn(crypto_version_list)\n"
      + "if (3, 7) in supported_pairs:\n"
      + "    ok()\n",
  },
  // requests field test (v0.1.8): subscript compares + HTTP status ranges
  // are structural; bare repeated literals still flag.
  r3_subscript_and_status: {
    "a.py": "_ver = sys.version_info\n"
      + "is_py3 = _ver[0] == 3\n"
      + "if not 400 <= r.status_code < 500:\n"
      + "    return r\n"
      + "elif 500 <= r.status_code < 600:\n"
      + "    raise HttpError()\n"
      + "assert sanity_check\n"
      + "if len(v) == 3:\n"
      + "    return v\n"
      + "if nullcount == 3:\n"
      + "    pad = _null * 3\n",
  },
  // pyjwt field test (v0.1.9): self.options built from a literal-returning
  // defaults method defines its keys (Assign, AnnAssign, alias, .get).
  r2_method_literal_defaults: {
    "a.py": "class PyJWS:\n"
      + "    @staticmethod\n"
      + "    def _get_default_options():\n"
      + "        return {'verify_signature': True, 'enforce_minimum_key_length': False}\n"
      + "\n"
      + "    def __init__(self):\n"
      + "        self.options = self._get_default_options()\n"
      + "\n"
      + "    def decode(self):\n"
      + "        merged = self.options\n"
      + "        if merged['verify_signature']:\n"
      + "            return self.options.get('enforce_minimum_key_length', False)\n"
      + "        return None\n",
  },
  r2_annassign_literal_defaults: {
    "a.py": "class C:\n"
      + "    def _get_default_options(self):\n"
      + "        'docstring'\n"
      + "        return {'require': [], 'strict_aud': False}\n"
      + "\n"
      + "    def __init__(self):\n"
      + "        self.options: dict = self._get_default_options()\n"
      + "\n"
      + "    def check(self):\n"
      + "        return self.options['require'], self.options.get('strict_aud', False)\n",
  },
  r2_attr_dict_literal: {
    "a.py": "class C:\n"
      + "    def __init__(self):\n"
      + "        self.options = {'api_key': 'x', 'timeout': 30}\n"
      + "\n"
      + "    def run(self):\n"
      + "        return self.options['api_key'], self.options.get('timeout')\n",
  },
  r2_plain_call_still_not_config: {
    "a.py": "def build():\n"
      + "    return {'id': 1}\n"
      + "\n"
      + "def run():\n"
      + "    options = build()\n"
      + "    return options['id']\n",
  },
  // pyjwt field test (v0.1.9): int literals report as ints in the message.
  r3_int_display: {
    "a.py": "def a(x):\n"
      + "    return (x + 7) // 8\n"
      + "\n"
      + "def b(x):\n"
      + "    return (x + 7) // 8\n"
      + "\n"
      + "def c(x):\n"
      + "    return (x + 7) // 8\n",
  },
  // pyjwt field test (v0.1.9): repetition in test files is vectors, not
  // unnamed constants - R3 skips them like R2 does.
  r3_skips_test_files: {
    "tests/test_x.py": "def t():\n    return (123, 123, 123)\n",
  },
  r3_click_named_values: {
    // click field test v0.1.10: values already named by the code - dict
    // values (key names them), signature defaults (param names them),
    // keyword args (keyword names them), shift counts (1 << 32 is the
    // named form of 2**32). Only the three positional foo(3) still flag.
    "a.py": "ANSIS = {'black': 30, 'green': 32, 'cyan': 36}\nw = 30\nx = 30\ny = 32\nz = 32\n",
    "b.py": "def bar(width: int = 30):\n    pass\n\ndef dl(col_max: int = 30):\n    pass\n\ndef pb(*, width: int = 36):\n    pass\n\nwarn('a', stacklevel=3)\nwarn('b', stacklevel=3)\nwarn('c', stacklevel=3)\nfoo(3)\nfoo(3)\nfoo(3)\n",
    "c.py": "a = 1 << 32\nb = 1 << 32\nc = 1 << 32\n",
  },
  // v0.1.11: non-assignment bindings (with/async-with/for/async-for/except)
  // of config-ISH names are plain locals, not config receivers. The config-y
  // constructor and config-ish iterable keep config-ness.
  r2_with_bound_configish: {
    "a.py": "import aiohttp\n\nasync def fetch():\n    async with aiohttp.ClientSession() as options:\n        timeout = options.get('timeout', 30)\n    return timeout\n\ndef load():\n    with open('cfg.json') as config:\n        v = config['retries']\n    return v\n",
  },
  r2_for_bound_configish: {
    "a.py": "def a():\n    for options in [{'a': 1}]:\n        v = options.get('timeout', 30)\n    return v\n\nasync def b():\n    async for config in items():\n        v = config['retries']\n    return v\n\nasync def items():\n    return []\n",
  },
  r2_except_bound_configish: {
    "a.py": "def c():\n    try:\n        x = 1 / 0\n    except ValueError as settings:\n        v = settings.get('code', 5)\n    return v\n",
  },
  r2_configy_binding_keeps: {
    // config-y constructor via with, and config-ish iterable via for: the
    // reads still register (hard read errors, soft read warns, dead key
    // warns) in both engines.
    "a.py": "class Config:\n    def get(self, k, default=None):\n        return default\n\nasync def e():\n    with Config() as config:\n        v = config.get('timeout', 30)\n        hard = config.get('api_key')\n    return v, hard\n\nasync def f():\n    async with make_options() as options:\n        v = options.get('retries', 3)\n    return v\n\nasync def make_options():\n    return Config()\n",
    "b.py": "cfg = {'timeout': 30}\n\ndef g():\n    for config in cfg:\n        v = config.get('retries', 3)\n        hard = config['api_key']\n    return v, hard\n",
  },
  r4_for_iter_loads: {
    // v0.1.11 parseFor fix: iterables of for/async-for are real nodes, so
    // loads inside them are visible (phantom_name fires on undefined
    // iterables in both engines).
    "a.py": "def plain():\n    for x in agen():\n        print(x)\n    return 1\n",
    "b.py": "async def afor():\n    async for y in bgen():\n        print(y)\n    return 1\n",
    "c.py": "def multi():\n    for z in one(), two():\n        print(z)\n    return 1\n",
  },
  // ---- v0.1.14: cross-file star-import resolution (Phase B, JS mirror) ----
  r4_star_sibling_resolves: {
    // sibling star import resolves -> clean
    "a.py": "def helper(x):\n    return x + 1\n",
    "b.py": "from a import *\nresult = helper(2)\n",
  },
  r4_star_typo_flagged: {
    // typo through star import -> flagged
    "a.py": "def helper(x):\n    return x + 1\n",
    "b.py": "from a import *\nresult = helpr(2)\n",
  },
  r4_star_all_honored: {
    // __all__ honored: name outside it -> flagged, name inside -> clean
    "a.py": "__all__ = ['helper']\ndef helper(x):\n    return x + 1\n\ndef internal(x):\n    return x * 2\n",
    "b.py": "from a import *\nr1 = helper(2)\nr2 = internal(3)\n",
  },
  r4_star_all_empty: {
    // __all__ = [] exports nothing -> clean file, every name flagged
    "a.py": "__all__ = []\ndef helper(x):\n    return x + 1\n",
    "b.py": "from a import *\nr = helper(2)\n",
  },
  r4_star_underscore_not_exported: {
    // underscore-prefixed names are not exported -> flagged
    "a.py": "_hidden = 1\ndef helper(x):\n    return x + _hidden\n",
    "b.py": "from a import *\nr = _hidden\n",
  },
  r4_star_external_skips: {
    // external (unresolvable) star import -> whole-file skip preserved
    "a.py": "from os import *\nr = definitely_not_defined_anywhere(1)\n",
  },
  r4_star_relative_package: {
    // relative star import inside a package -> clean
    "pkg/__init__.py": "",
    "pkg/a.py": "def helper(x):\n    return x + 1\n",
    "pkg/b.py": "from .a import *\nresult = helper(2)\n",
  },
  r4_star_transitive_chain: {
    // transitive chain (a imports b imports c) -> clean
    "a.py": "from b import *\n",
    "b.py": "from c import *\n",
    "c.py": "def deep(x):\n    return x * 10\n",
    "main.py": "from a import *\nr = deep(3)\n",
  },
  r4_star_mixed_external_skips: {
    // mixed resolvable + external -> whole-file skip (conservative)
    "a.py": "def helper(x):\n    return x + 1\n",
    "b.py": "from a import *\nfrom os import *\nr = helper(2)\n",
  },
  r4_star_cycle_skips: {
    // import cycle -> whole-file skip (memo guards re-entry)
    "a.py": "from b import *\nx = 1\n",
    "b.py": "from a import *\ny = 2\n",
    "main.py": "from a import *\nr = zzz(1)\n",
  },
  r4_star_plain_imports_reexported: {
    // plain `import x` names ARE re-exported (probe-verified) -> clean
    "a.py": "import os\nimport datetime\n",
    "b.py": "from a import *\nr = os.getcwd()\nd = datetime.date.today()\n",
  },
  r4_star_sibling_submodule_name: {
    // a relative from-import also exports the sibling submodule name
    "pkg/__init__.py": "",
    "pkg/helpers.py": "def h(x):\n    return x + 1\n",
    "pkg/m1.py": "from .helpers import *\n",
    "pkg/main.py": "from m1 import *\nr = helpers.h(2)\n",
  },
  r4_star_all_dynamic_skips: {
    // dynamic __all__ (computed) -> unresolvable -> whole-file skip
    "a.py": "names = ['helper']\n__all__ = names\ndef helper(x):\n    return x + 1\n",
    "b.py": "from a import *\nr = helper(2)\n",
  },

  // v0.1.15 — dateutil field test #8 regressions
  r3_mixed_int_float_display: {
    "a.py": "x = 7\ny = 7.0\nz = 7\n",
  },
  // chained tuple assignment: `a, b = c = expr` must bind `c` and keep the
  // RHS literals (JS parser used to drop the chain tail — phantom `weekdays`,
  // lost range(7)).
  r3_chained_tuple_assign: {
    "a.py": "def weekday(x):\n"
      + "    return x\n"
      + "MO, TU, WE, TH, FR, SA, SU = weekdays = tuple(weekday(x) for x in range(7))\n"
      + "def f():\n"
      + "    return TU + 7\n"
      + "def g():\n"
      + "    return SU + 7\n",
  },
  r1_windows_error_compat: {
    "a.py": "import os\n\ndef _probe():\n"
      + "    try:\n"
      + "        os.open('x', os.O_RDONLY)\n"
      + "    except WindowsError:\n"
      + "        return None\n",
  },
  // JS BUILTINS list was hand-typed and missing the OSError family and the
  // Warning classes — these must be known in BOTH engines (python side
  // derives from dir(builtins)).
  r1_warning_and_oserror_family: {
    "a.py": "import warnings\n\nwarnings.warn('x', DeprecationWarning)\n\n\ndef f():\n"
      + "    try:\n"
      + "        return 1\n"
      + "    except FileNotFoundError:\n"
      + "        return 2\n",
  },
  // int families key exactly: 2**53, 2**53+1, 2**53+2 are three singletons,
  // not one bucket (float() collapse) — no finding expected.
  r3_big_int_families: {
    "a.py": "def f():\n"
      + "    return 9007199254740992\n"
      + "def g():\n"
      + "    return 9007199254740993\n"
      + "def h():\n"
      + "    return 9007199254740994\n",
  },

  // ---- field test #9 (black) regression cases — all five were live bugs ----
  // raw string with an escaped quote: r"[\'\"]" must not close early
  // (the tail re-tokenized as code, dropping the statement binding)
  ft9_raw_escaped_quote: {
    "a.py": "import re\n"
      + "def f(expression, f_expressions):\n"
      + "    debug_expressions_contain_visible_quotes = any(\n"
      + "        re.search(r\"[\\'\\\"].*(?<![!:=])={1}(?!=)(?![^\\s:])\", expression)\n"
      + "        for expression in f_expressions\n"
      + "    )\n"
      + "    if not debug_expressions_contain_visible_quotes:\n"
      + "        return 1\n",
  },
  // rf-string prefix: rf"..." must tokenize as ONE string, not NAME(r)+fstring
  ft9_rf_string_prefix: {
    "a.py": "import re\n"
      + "def h(new_quote, s):\n"
      + "    unescaped_new_quote = re.compile(rf\"(([^\\\\]|^)(\\\\\\\\)*){new_quote}\")\n"
      + "    if unescaped_new_quote.search(s):\n"
      + "        return 1\n"
      + "    return 0\n",
  },
  // f-string int subscript: f"{x[3]}" — the index is a slice position, not magic
  ft9_fstring_int_subscript: {
    "a.py": "def a(x):\n"
      + "    return f\"one {x[3]}\"\n"
      + "def b(x):\n"
      + "    return f\"two {x[3]}\"\n"
      + "def c(x):\n"
      + "    return f\"three {x[3]}\"\n",
  },
  // f-string slice + dotted receiver: f"{self.name[3:]}" — slice colon is not
  // a format spec
  ft9_fstring_slice_colon: {
    "a.py": "class C:\n"
      + "    def pretty(self):\n"
      + "        return f\"Python {self.name[2]}.{self.name[3:]}\"\n",
  },
  // f-string format spec WITH colons: {target:%H:%M} — one spec, no dangling %H
  ft9_fstring_format_colons: {
    "a.py": "def show(target, state):\n"
      + "    print(f\"Algiers {target:%H:%M} {state}\")\n"
      + "    print(f\"until {target:%H:%M} ({state})\")\n"
      + "    print(f\"left {target:%H:%M} {state}\")\n",
  },
  // starred for-iterable: for x in (a, *b) — the star used to break the parse
  // AND cascade into the next def (params dropped -> phantom_name)
  ft9_starred_for_iterable: {
    "a.py": "def j(common_base):\n"
      + "    for directory in (common_base, *common_base.parents):\n"
      + "        if (directory / \".git\").exists():\n"
      + "            return directory\n"
      + "    return directory\n"
      + "def find_pyproject_toml(path_search_start: tuple[str, ...], stdin_filename: str | None = None) -> str | None:\n"
      + "    path_project_root, _ = find_project_root(path_search_start, stdin_filename)\n"
      + "    return path_project_root\n",
  },
  // starred list element: [a, *b] — assignment binding used to be dropped
  ft9_starred_list_element: {
    "a.py": "def i(comment, _COMMENT_PREFIX, _COMMENT_LIST_SEPARATOR):\n"
      + "    semantic_comment_blocks = [\n"
      + "        _COMMENT_PREFIX + comment.strip(),\n"
      + "        *[_COMMENT_PREFIX + comment.strip().split(_COMMENT_LIST_SEPARATOR)],\n"
      + "    ]\n"
      + "    return any(comment in semantic_comment_blocks for comment in [])\n",
  },
  // RuntimeError builtin: raise RuntimeError(...) is not a phantom name
  ft9_runtimeerror_builtin: {
    "a.py": "def k():\n"
      + "    raise RuntimeError(\"boom\")\n"
      + "def l():\n"
      + "    try:\n"
      + "        k()\n"
      + "    except RuntimeError:\n"
      + "        return 1\n",
  },
  // mode.py shape: Enum members + f-string subscript — the exact black mix
  // that exposed the cross-file count bug
  ft9_enum_member_and_fstring: {
    "a.py": "from enum import Enum\n"
      + "class Feature(Enum):\n"
      + "    F_STRINGS = 2\n"
      + "    NUMERIC_UNDERSCORES = 3\n"
      + "def g():\n"
      + "    return Feature.NUMERIC_UNDERSCORES\n",
    "b.py": "x = 3\ny = 3\nz = 3\n",
  },
  // v0.1.18 — Aether review of the v0.1.16 diff: the f-string idxRe had no
  // :step group, no minus, and matched only the first bracket of a chain
  // (seeds: f"{x[1:10:2]}", f"{name[-3:]}", f"{a[1][2]}", f"{row[::2]}").
  // Genuine 3s/10s at lines 2/4/6 flag; index digits must never contribute.
  ft10_fstring_step_slice: {
    "a.py": "def demo(x):\n"
      + "    if x == 3 or x == 10:\n"
      + "        pass\n"
      + "    if x == 3 or x == 10:\n"
      + "        pass\n"
      + "    if x == 3 or x == 10:\n"
      + "        pass\n"
      + "    return f\"{x[1:10:2]}\"\n",
  },
  ft10_fstring_negative_slice: {
    "a.py": "def demo(name, x):\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    return f\"{name[-3:]}\", f\"{x[-3]}\"\n",
  },
  ft10_fstring_chained_subscript: {
    "a.py": "def demo(a, x):\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    return f\"{a[1][3]}\"\n",
  },
  ft10_fstring_step_only: {
    "a.py": "def demo(row, x):\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    return f\"{row[::3]}\"\n",
  },
  // negative slice bounds, structural (non-f-string) — the same UnaryOp
  // leak ran in BOTH engines' R3 walkers; the shipped CLI was affected
  ft10_negative_slice_bounds: {
    "a.py": "def demo(name, x):\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    if x == 3:\n"
      + "        pass\n"
      + "    z = name[-3:]\n"
      + "    w = x[-3]\n"
      + "    return z, w\n",
  },
  // starred assignment targets: *rest = xs / *_, most = xs — the parser
  // used to throw at a statement-level `*`, skipping the line and losing
  // the binding (blib2to3/pgen2/parse.py on the black src tree; field
  // parity #10 exposed it right after the v0.1.18 release)
  ft10_starred_assignment_targets: {
    "a.py": "def f(alive):\n"
      + "    ilabel, *rest = alive\n"
      + "    *_, most = alive\n"
      + "    if not rest:\n"
      + "        return ilabel\n"
      + "    return most\n",
  },
  ft11_lambda_star_kwargs: {
    // CrossEdge FT10: lambda *a, **k: None — the vararg/kwarg annotation
    // eat was not lambda-gated, so the body colon got eaten as an
    // annotation and the statement failed to parse (2 test files skipped).
    "a.py": "import json\n"
      + "def f():\n"
      + "    bot.journal = lambda *a, **k: None\n"
      + "    bot.audit = lambda *a, **k: None\n"
      + "    bot.save_state = lambda: None\n"
      + "    bot.paper_sell = lambda *a, **k: None\n"
      + "    bot.paper_buy = lambda *a, **k: None\n"
      + "    return bot\n",
  },
  ft11_unicode_ident: {
    // CrossEdge FT10 / black src: Ø is a valid Python identifier (U+00D8).
    // The ASCII-only tokenizer failed on linegen.py's `parens=Ø` idiom and
    // the whole file was at risk of being skipped.
    "a.py": "def f(mode):\n"
      + "    Ø = set()\n"
      + "    if mode:\n"
      + "        Ø.add('x')\n"
      + "    return Ø\n",
  },
  ft11_set_starred_element: {
    // black linegen.py: {id(rhs.closing_bracket), *omit} — starred element
    // in a SET literal (list/tuple starred was v0.1.17; set was missed).
    "a.py": "def f(omit):\n"
      + "    rhs = object()\n"
      + "    return {id(rhs), *omit}\n",
  },
  ft11_fstring_kwarg_name: {
    // CrossEdge FT10: json.dumps(acc, indent=2) inside an f-string leaked
    // the kwarg NAME as a phantom (Name nodes were emitted for call
    // keyword names by the f-string scanner).
    "a.py": "import json\n"
      + "def f(acc):\n"
      + "    print(f\"{json.dumps(acc, indent=2)}\")\n"
      + "    print(f\"{json.dumps(acc, separators=(',', ':'))}\")\n",
  },
  ft11_fstring_strftime: {
    // CrossEdge FT10: strftime('%Y-%m-%d %H:%M:%S') inside an f-string —
    // the format-spec strip ate the string at its first colon and the
    // format codes %Y/%H leaked in as phantom names 'Y'/'H'.
    "a.py": "from datetime import datetime\n"
      + "def f():\n"
      + "    return f\"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"\n",
  },
  ft11_fstring_multiline_line: {
    // CrossEdge FT10: literals inside a multi-line f-string were reported
    // at the string's start line (0.2/1.5/2.5 came back as 1688 instead of
    // 1690/1691/1692); implicit-concat pieces also need their own line.
    // Each value repeats >= 3 times so the finding fires and the message's
    // line numbers are compared byte-for-byte.
    "a.py": "def f(settings):\n"
      + "    return (\n"
      + "        f\"thr{float(settings.get('a', 0.20)):.2f} \"\n"
      + "        f\"SL{float(settings.get('b', 1.5)):.1f}x \"\n"
      + "        f\"TP{float(settings.get('c', 2.5)):.1f}x\"\n"
      + "    )\n"
      + "def g(settings):\n"
      + "    return (\n"
      + "        f\"thr{float(settings.get('a', 0.20)):.2f} \"\n"
      + "        f\"SL{float(settings.get('b', 1.5)):.1f}x \"\n"
      + "        f\"TP{float(settings.get('c', 2.5)):.1f}x\"\n"
      + "    )\n"
      + "def h(settings):\n"
      + "    return (\n"
      + "        f\"thr{float(settings.get('a', 0.20)):.2f} \"\n"
      + "        f\"SL{float(settings.get('b', 1.5)):.1f}x \"\n"
      + "        f\"TP{float(settings.get('c', 2.5)):.1f}x\"\n"
      + "    )\n",
  },
  ft11_fstring_stringkey_slice: {
    // CrossEdge FT10: f"{', '.join(x['key'][:3])}" — a string-keyed
    // subscript chained to a slice broke the old index regex, leaking the
    // slice bound 3 into the magic tally.
    "a.py": "def f(x):\n"
      + "    return f\"{', '.join(x['key'][:3])}\"\n",
  },
  ft11_parse_failure_skips_file: {
    // CrossEdge FT10 database.py: cursor..execute — a real SyntaxError.
    // Python's ast skips the whole file; the JS engine used to scan the
    // recoverable lines and inflate families (100/100.0 +4). Both engines
    // now skip the file whole, with the same note.
    "a.py": "def ok():\n"
      + "    return 1\n"
      + "cursor..execute('x')\n",
  },
  ft11_float_repr_scientific: {
    // CrossEdge FT10: 1e-08 — JS printed 1e-8; Python's repr zero-pads
    // the exponent. Also covers the plain-vs-scientific threshold
    // (1e-4 <= |v| < 1e16 is plain decimal).
    "a.py": "def f():\n"
      + "    a = 1e-8\n"
      + "    b = 1e-8\n"
      + "    c = 1e-8\n"
      + "    return a + b + c\n",
  },
  ft12_fstring_unicode_name: {
    // Aether residual on v0.1.20: tokenize took Ø but the f-string
    // scanner's nameRe stayed ASCII-only, so f"{café}" lost the name
    // entirely (py saw it, JS didn't).
    "a.py": "café = 1\n"
      + "print(f\"{café}\")\n",
  },
  ft12_fstring_unicode_name_digit: {
    // ø2 is ONE identifier (ø is XID_Start, 2 is XID_Continue). An ASCII
    // numRe lookbehind let the 2 leak as a phantom magic constant.
    "a.py": "ø2 = 1\n"
      + "print(f\"{ø2}\")\n",
  },
  ft12_fstring_unicode_get: {
    // getRe with a Unicode receiver. café is NOT defined: py sees the
    // f-string FormattedValue call and flags phantom 'café'; an ASCII
    // getRe would emit nothing and stay silent.
    "a.py": "print(f\"{café.get('missing_key')}\")\n",
  },
  ft12_fstring_unicode_chain: {
    // chainRe with a Unicode base name. ticket is NOT defined: py sees
    // one receiver name; an ASCII chainRe would split it into two
    // phantoms ('ticket' + 'árboles') and break parity.
    "a.py": "print(f\"{ticket.árboles[3]}\")\n",
  },
  ft12_fstring_unicode_kwarg: {
    // kwarg names are not usages — the blanker must strip a Unicode
    // kwarg name; the 2 stays a real magic constant.
    "a.py": "def func(**kw):\n"
      + "    pass\n"
      + "print(f\"{func(árg=2)}\")\n",
  },
  // v0.1.22: attribute-style config reads (kanlaon_watch field case) —
  // the walk had no Attribute branch, so class-style config (Config(**cfg))
  // looked 100% dead to R2.
  r2_attr_read_class_config: {
    "a.py": "DEFAULT_CONFIG = {\n"
      + "    'alert_threshold': 3,\n"
      + "    'volcano': 'KANLAON',\n"
      + "}\n"
      + "class Config:\n"
      + "    def __init__(self, alert_threshold, volcano):\n"
      + "        self.alert_threshold = alert_threshold\n"
      + "        self.volcano = volcano\n"
      + "def load_config(here):\n"
      + "    cfg = dict(DEFAULT_CONFIG)\n"
      + "    return Config(**cfg)\n"
      + "config = load_config('.')\n"
      + "if config.alert_threshold > 1:\n"
      + "    print(config.volcano)\n",
  },
  r2_attr_read_non_config_receiver: {
    // An attr read on a receiver that is NOT config-ish must not mask a
    // genuinely dead key.
    "a.py": "DEFAULT_CONFIG = {'url': 'https://x'}\n"
      + "request = None\n"
      + "print(request.url)\n",
  },
  r2_attr_store_not_read: {
    // `config.timeout = 9` (Store ctx) must not register as a read:
    // a key that is only ever written is still dead config.
    "a.py": "class Config:\n"
      + "    def __init__(self, **kw):\n"
      + "        pass\n"
      + "DEFAULT_CONFIG = {'timeout': 5}\n"
      + "config = Config(**DEFAULT_CONFIG)\n"
      + "config.timeout = 9\n",
  },

  // v0.1.23: dynamic-keyed reads (isort FT11). A config dict whose keys
  // are reached through a VARIABLE subscript or .get(expr) has no provably
  // dead key; a genuinely dead key in a separate dict is still flagged.
  r2_dynamic_key_read_kills_dead_keys: {
    "a.py": "CONFIG_SECTIONS = {\n"
      + "    '.editorconfig': 'editor',\n"
      + "    '.isort.cfg': 'isort',\n"
      + "    'pyproject.toml': 'pyproject',\n"
      + "}\n"
      + "cfg = {'abandoned': 1}\n"
      + "def lookup(name):\n"
      + "    return CONFIG_SECTIONS.get(name, {})\n"
      + "def grab(name):\n"
      + "    return CONFIG_SECTIONS[name]\n",
  },
  r2_env_payload_dict_is_data: {
    // {**os.environ, ...} builds a child-process env payload: data, not
    // config. LANG must not be flagged dead; the target is demoted so
    // env.get(...) never registers as a config read either. A genuinely
    // dead key elsewhere still fires.
    "a.py": "import os\n"
      + "import subprocess\n"
      + "def run(cmd):\n"
      + "    env = {**os.environ, 'LANG': 'C.UTF-8'}\n"
      + "    return subprocess.check_output(cmd, env=env)\n"
      + "cfg = {'lonely': 1}\n",
  },
  r2_dynamic_attr_read_kills_class_defaults: {
    // self.defaults[var] on a config class: the dynamic read covers every
    // key defined in the class-level defaults literal.
    "a.py": "class Config:\n"
      + "    defaults = {'port': 8080, 'host': '127.0.0.1'}\n"
      + "    def get(self, key):\n"
      + "        return self.defaults[key]\n",
  },
  r1_annotated_variadic_params: {
    // isort FT11 parse bug: **kwargs: Any, (annotation + trailing comma)
    // crashed the JS parser, the cascade skipped the WHOLE file. The
    // phantom read at the bottom proves both engines scanned the file.
    "a.py": "from typing import Any\n"
      + "def handle(name: str, **config_overrides: Any,):\n"
      + "    return config_overrides.get(name)\n"
      + "def api(*, verbose: bool = False, **kwargs: Any,):\n"
      + "    return kwargs\n"
      + "def main(**kwargs: Any,):\n"
      + "    pass\n"
      + "handle('x')\n"
      + "missing_name\n",
  },

  r2_implicit_tuple_star_rhs: {
    // review F1: `args = pos, *rest` (tomli/_parser.py:117) — bare starred
    // implicit tuple on an assignment RHS crashed the JS parser and the
    // WHOLE file was skipped as clean. The dead key proves both engines
    // scanned the file (py: 1 finding; JS used to skip: 0).
    "a.py": "def f(pos, *rest):\n"
      + "    args = pos, *rest\n"
      + "    return args\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_plain_rhs: {
    // review F1: plain `x = 1, 2` was equally unparseable — the JS engine
    // parsed assignment RHS as a single expression and never consumed the
    // bare comma tail.
    "a.py": "def f(pos, *rest):\n"
      + "    plain = 1, 2\n"
      + "    return plain\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_trailing_comma: {
    // review F1: `x = 1,` is a one-element tuple at parse level.
    "a.py": "def f():\n"
      + "    one = 1,\n"
      + "    return one\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_star_led: {
    // review F1: star-led RHS list: `x = *a, b`
    "a.py": "def f(a, *b):\n"
      + "    x = *a, b\n"
      + "    return x\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_return_star: {
    // review F1: `return a, *b`
    "a.py": "def f(a, *b):\n"
      + "    return a, *b\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_yield_star: {
    // review F1: `yield a, *b`
    "a.py": "def f(a, *b):\n"
      + "    yield a, *b\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_chained: {
    // review F1: chained assignment RHS is a star-list too: `a = b = c, d`
    "a.py": "def f(c, d):\n"
      + "    a = b = c, d\n"
      + "    return a, b\n"
      + "config = {'never_used': 1}\n",
  },
  r2_implicit_tuple_for_star: {
    // review F1: for-iterable comma list with a starred element
    "a.py": "def f(a, *rest):\n"
      + "    for x in a, *rest:\n"
      + "        pass\n"
      + "    return x\n"
      + "config = {'never_used': 1}\n",
  },
  r2_setdefault_defines_key: {
    // FT12: setdefault(key, default) defines the key when missing — config
    // built by setdefault must not read as ghost keys.
    "a.py": "def f(settings):\n"
      + "    settings.setdefault('extension_configs', {})\n"
      + "    settings.setdefault('extensions', [])\n"
      + "    for ext in settings['extension_configs'].keys():\n"
      + "        if ext not in settings['extensions']:\n"
      + "            settings['extensions'].append(ext)\n"
      + "    return settings\n",
  },
  r2_optional_presence_demote: {
    // FT12: `if "KEY" in settings:` is a presence test — later bare reads of
    // the key demote to a warning; absence is handled, never a silent default.
    "a.py": "def migrate(settings):\n"
      + "    if 'PLUGIN_PATH' in settings:\n"
      + "        settings['PLUGIN_PATHS'] = settings['PLUGIN_PATH']\n"
      + "        del settings['PLUGIN_PATH']\n"
      + "    return settings\n"
      + "CONFIG = {'PLUGIN_PATHS': []}\n",
  },
  r2_optional_softget_demote: {
    // FT12: a .get(k, default) read makes k optional for the scope; a bare
    // subscript read of the same key emits one fallback warning, not an error.
    "a.py": "def f(settings):\n"
      + "    if settings.get('DEFAULT_DATE', None) and settings['DEFAULT_DATE'] != 'fs':\n"
      + "        return settings['DEFAULT_DATE']\n"
      + "    return None\n"
      + "CONFIG = {'SITEURL': ''}\n",
  },
  r2_get1arg_outofview_soft: {
    // FT12: 1-arg .get on an out-of-view receiver (param) is a fallback
    // warning — the key may be user-set.
    "a.py": "def f(settings):\n"
      + "    if settings.get('AUTORELOAD_IGNORE_CACHE'):\n"
      + "        pass\n"
      + "    return settings\n"
      + "CONFIG = {'SITEURL': ''}\n",
  },
  r2_get1arg_inview_error: {
    // FT12: 1-arg .get on a receiver with a FULLY KNOWN in-file key set is a
    // provable ghost — error stays.
    "a.py": "config = {'api_key': 'x'}\n"
      + "print(config.get('missing_key'))\n",
  },
  r2_callarg_consumption_kills_dead: {
    // FT12: a config dict handed to a call (here: render(**CONF)-style pass to
    // a template renderer) is consumed by the callee — not provably dead.
    "a.py": "def render(tmpl, vars):\n"
      + "    return tmpl % vars\n"
      + "CONF = {'pelican': 'pelican', 'basedir': '.', 'ssh_host': 'x'}\n"
      + "out = render('Makefile', CONF)\n"
      + "print(CONF['basedir'])\n"
      + "print(CONF['ssh_host'])\n",
  },
  ft12_fstring_get_quoted_str_default: {
    // FT12 residual (Aether, closed v0.1.25): a QUOTED-STRING default in
    // an f-string .get was invisible to the JS engine — the default group
    // excluded quotes, so the whole match failed and the soft read never
    // registered (py warned, JS silent). Numeric/name defaults were fine.
    "a.py": "cfg = {'A_KEY': 'x'}\n"
      + "print(f\"v={cfg.get('A_KEY', 'strdef')}\")\n"
      + "print(f\"w={cfg.get('MISSING', 'fallback')}\")\n"
      + "print(f\"n={cfg.get('A_KEY', 5)}\")\n"
      + "print(f\"d={cfg.get('A_KEY', DEFAULT_NAME)}\")\n",
  },
  r2_multiread_ghost_reports_first_line: {
    // FT12 F1: with several reads of one ghost key, both engines report the
    // SOURCE-FIRST read line (py used ast.walk breadth-first and reported a
    // depth-arbitrary one).
    "a.py": "def f(settings):\n"
      + "    settings['x'] = 1\n"
      + "    a = settings['ghost_key']\n"
      + "    b = settings['ghost_key']\n"
      + "    c = settings['ghost_key']\n"
      + "    return a, b, c\n"
      + "CONFIG = {'SITEURL': ''}\n",
  },
  ft13_singleton_tuple_target: {
    // FT13 (pre-commit v4.6.2): `x, = f()` — singleton tuple target. The JS
    // engine walked into `=` and skipped the whole file (19 files skipped in
    // the tree); Python's exprlist allows the trailing comma (ast: Tuple
    // with one element). The dead-key line proves a skip would drop findings.
    "a.py": "def f():\n"
      + "    return [1]\n"
      + "\n"
      + "x, = f()\n"
      + "config = {'unused_key': 1}\n",
  },
  ft13_singleton_for_target: {
    // FT13: `for k, in [('a',)]:` and `[x for k, in rows]` — same singleton
    // trailing comma on a for/comprehension target.
    "a.py": "for k, in [('a',)]:\n"
      + "    pass\n"
      + "v = [x for x, in [('b',)]]\n"
      + "config = {'unused_key': 1}\n",
  },
  ft13_subscript_trailing_comma: {
    // FT13: `d['a',]` / `tuple[\n    int,\n]` — trailing comma in a
    // subscript (pre-commit's multi-line annotations). Python keeps a
    // one-element Tuple; the JS slice parser threw at `]`.
    "a.py": "d = {'a': 1}\n"
      + "v = d['a',]\n"
      + "def g() -> tuple[\n"
      + "    int,\n"
      + "]:\n"
      + "    pass\n"
      + "config = {'unused_key': 1}\n",
  },
  ft13_trailing_dot_float: {
    // FT13: `2.` (and `2., 3.` in a tuple) — trailing-dot float literal.
    // The tokenizer split `2` and `.` and the attribute parse threw.
    "a.py": "v = 2.\n"
      + "w = (1., 2., b'x')\n"
      + "config = {'unused_key': 1}\n",
  },
  r2_schema_call_defines_key: {
    // v0.1.26: cfgv-family schema calls declare config keys — Required /
    // Optional ('key', ...) count as defined AND consumed (the schema is
    // the user-facing contract; pre-commit FT13: fail_fast read but never
    // "defined", plus files/exclude/default_install_hook_types). Neither
    // engine may emit a finding here.
    "a.py": "import cfgv\n"
      + "schema = cfgv.Map(\n"
      + "    'Config', None,\n"
      + "    cfgv.Optional('fail_fast', cfgv.check_bool, False),\n"
      + "    cfgv.RequiredRecurse('repos', cfgv.Array()),\n"
      + ")\n",
    "b.py": "def f(config):\n"
      + "    return config['fail_fast']\n",
  },
  r3_pow_exponent_excluded: {
    // v0.1.26: 2 ** 12 — the exponent is the unit, like a shift count
    // (pre-commit FT13: max(min(..., 2 ** 17), 2 ** 12) flagged 12 x2).
    "a.py": "a = 2 ** 12\nb = max(1, 2 ** 12)\nc = min(3, 2 ** 12)\nz = 0\n",
  },
  r3_string_repeat_width_excluded: {
    // v0.1.26: '=' * 79 — a presentation width; the string is the unit
    // (pre-commit FT13: try_repo.py banners x3).
    "a.py": "a = '=' * 79\nb = '-' * 79\nc = 79 * '~'\nz = 0\n",
  },
  r3_len_bound_compare_excluded: {
    // v0.1.26: len(x) > 3 — argument-count bounds are structural
    // (pre-commit FT13: hook_impl.py x2 + languages/r.py x1).
    "a.py": "def f(args, other):\n"
      + "    if len(args) > 3:\n"
      + "        return 1\n"
      + "    if len(args) == 3:\n"
      + "        return 2\n"
      + "    if 3 < len(other):\n"
      + "        return 4\n"
      + "    return 0\n",
  },
  r3_usub_named_const_excluded: {
    // v0.1.26: STD_ERROR_HANDLE = -12 — the sign wraps the literal, the
    // statement parent still names it (pre-commit FT13: USub hid the
    // UPPER_NAME assign skip).
    "a.py": "STD_ERROR_HANDLE = -12\nOTHER_HANDLE = -12\nTHIRD_HANDLE = -12\nz = 0\n",
  },
  r3_bare_repeat_still_counted: {
    // control: the v0.1.26 exclusions must not swallow plain repeats —
    // both engines still report this one.
    "a.py": "def f(x):\n"
      + "    a = x + 7\n"
      + "    b = x + 7\n"
      + "    return a + b + 7\n",
  },
  ft13_class_kwarg_bases: {
    // FT13 sweep: `class X(Base, total=False)` / `metaclass=M` — keyword
    // args in class bases (TypedDict!) skipped whole files in the JS
    // engine (pyjwt types.py, click types.py, black tests). Keywords are
    // not bases; the file must scan (dead key proves it).
    "a.py": "class SigOptions(TypedDict, total=False):\n"
      + "    verify_signature: bool\n"
      + "class Small(Other, metaclass=M):\n"
      + "    pass\n"
      + "config = {'unused_key': 1}\n",
  },
  fstring_dotted_receiver: {
    // v0.1.26: {ctx.params.get('k')} — the f-string scanner must keep the
    // full dotted receiver (Python sees an Attribute chain). Emitting just
    // the last segment made 'params'/'environ' phantoms on click's tests
    // (FT13 sweep).
    "a.py": "def f(ctx):\n"
      + "    return f\"a={ctx.params.get('my_arg')} b={ctx.params.get('o')!r}\"\n",
  },
  ft13_async_comprehension: {
    // FT13 sweep: `[i async for i in z]` — the async form of a
    // comprehension never entered the comprehension parser (it only
    // checked for `for`), so black's slices.py fixture skipped whole.
    "a.py": "async def f():\n"
      + "    slice[await x : [i async for i in arange(42)] : 42]\n"
      + "config = {'unused_key': 1}\n",
  },
  ft13_paren_with_items: {
    // FT13 sweep: parenthesized with-item lists — Python splits on commas
    // into separate items (`with (a, b):` is TWO items, not a tuple), and
    // `with (x) as f:` must still read as one grouped expression. The JS
    // parser treated the list as a tuple / threw on the `as`.
    "a.py": "with (\n"
      + "    open('x') as f,\n"
      + "    other(),\n"
      + "):\n"
      + "    pass\n"
      + "with (single) as s:\n"
      + "    pass\n"
      + "config = {'unused_key': 1}\n",
  },
};