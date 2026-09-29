#!/usr/bin/env python3
"""Tests for drift. Run: python3 test_drift.py"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drift  # noqa: E402


class DriftTest(unittest.TestCase):

    def scan(self, files, rules="R1,R2,R3,R4"):
        with tempfile.TemporaryDirectory() as td:
            for name, content in files.items():
                p = Path(td) / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            findings, _notes = drift.analyze([td], rules=rules)
            return findings

    def rules_seen(self, findings):
        return {f.rule for f in findings}

    # --- R1: unexpected_kwarg ---

    def test_r1_flags_unexpected_kwarg(self):
        findings = self.scan({
            "a.py": "class SignalHistory:\n    def __init__(self, window, total=None):\n        pass\n",
            "b.py": "from a import SignalHistory\nsh = SignalHistory(total_r=5)\n",
        })
        r1 = [f for f in findings if f.rule == "unexpected_kwarg"]
        self.assertEqual(len(r1), 1)
        self.assertEqual(r1[0].severity, "error")
        self.assertIn("total_r", r1[0].message)

    def test_r1_accepts_var_kwargs(self):
        findings = self.scan({
            "a.py": "class Config:\n    def __init__(self, **kwargs):\n        pass\n",
            "b.py": "c = Config(anything=1)\n",
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    def test_r1_accepts_declared_kwarg(self):
        findings = self.scan({
            "a.py": "class Config:\n    def __init__(self, a, b=2):\n        pass\n",
            "b.py": "c = Config(a=1, b=3)\n",
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    def test_r1_flags_positional_only(self):
        findings = self.scan({
            "a.py": "def f(a, /, b):\n    pass\n",
            "b.py": "f(a=1, b=2)\n",
        })
        r1 = [f for f in findings if f.rule == "unexpected_kwarg"]
        self.assertEqual(len(r1), 1)
        self.assertIn("'a'", r1[0].message)

    def test_r1_skips_ambiguous_names(self):
        findings = self.scan({
            "a.py": "class Same:\n    def __init__(self, x):\n        pass\n",
            "b.py": "class Same:\n    def __init__(self, y):\n        pass\n",
            "c.py": "s = Same(z=1)\n",
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    def test_r1_self_call_uses_class_method_not_module_func(self):
        # Regression (v0.1.3): a module-level exit_prices() without position_side
        # must not shadow a PaperBot.exit_prices() method that accepts it.
        findings = self.scan({
            "a.py": (
                "def exit_prices(entry, candles, settings):\n"
                "    return 1\n"
                "class PaperBot:\n"
                "    def exit_prices(self, entry, candles, settings, position_side='LONG'):\n"
                "        return 2\n"
                "    def run(self):\n"
                "        return self.exit_prices(1, [], {}, position_side='SHORT')\n"
            ),
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    def test_r1_self_call_unknown_attr_skipped(self):
        # self.<name> with no matching class method cannot be resolved (it may
        # be assigned in __init__, inherited from a base drift cannot see, or a
        # mixin) — never guess against a same-named module-level function.
        findings = self.scan({
            "a.py": (
                "def exit_prices(entry, candles, settings):\n"
                "    return 1\n"
                "class PaperBot:\n"
                "    def run(self):\n"
                "        return self.exit_prices(1, [], {}, position_side='SHORT')\n"
            ),
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    def test_r1_unknown_receiver_attr_call_skipped(self):
        # unittest.main(verbosity=2) must not be checked against a module-level
        # main() function — the receiver is a different module entirely.
        findings = self.scan({
            "a.py": (
                "def main(argv=None):\n"
                "    return 0\n"
                "import unittest\n"
                "unittest.main(verbosity=2)\n"
            ),
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    def test_r1_class_name_attr_call_checked(self):
        # PaperBot.exit_prices(...) resolves against the class's own method.
        findings = self.scan({
            "a.py": (
                "class PaperBot:\n"
                "    def exit_prices(self, entry, candles, settings, position_side='LONG'):\n"
                "        return 2\n"
                "PaperBot.exit_prices(None, 1, [], {}, position_side='SHORT')\n"
                "PaperBot.exit_prices(None, 1, [], {}, bogus_key=3)\n"
            ),
        })
        r1 = [f for f in findings if f.rule == "unexpected_kwarg"]
        self.assertEqual(len(r1), 1)
        self.assertIn("bogus_key", r1[0].message)

    def test_r1_module_func_same_name_still_checked(self):
        # A direct module-level call to the shadowing function is still flagged.
        findings = self.scan({
            "a.py": (
                "def exit_prices(entry, candles, settings):\n"
                "    return 1\n"
                "class PaperBot:\n"
                "    def exit_prices(self, entry, candles, settings, position_side='LONG'):\n"
                "        return 2\n"
                "exit_prices(1, [], {}, position_side='SHORT')\n"
            ),
        })
        r1 = [f for f in findings if f.rule == "unexpected_kwarg"]
        self.assertEqual(len(r1), 1)
        self.assertIn("position_side", r1[0].message)

    def test_r1_self_call_inherited_method(self):
        findings = self.scan({
            "a.py": (
                "class Base:\n"
                "    def exits(self, a, b):\n"
                "        return a\n"
                "class Child(Base):\n"
                "    def run(self):\n"
                "        return self.exits(a=1, b=2)\n"
            ),
        })
        self.assertNotIn("unexpected_kwarg", self.rules_seen(findings))

    # --- R2: config_drift ---

    def test_r2_flags_phantom_key(self):
        findings = self.scan({
            "a.py": "config = {'api_key': 'x'}\nprint(config.get('missing_key'))\nprint(config.get('api_key'))\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "error")
        self.assertIn("missing_key", r2[0].message)

    def test_r2_flags_dead_key(self):
        findings = self.scan({
            "a.py": "config = {'never_used': 1}\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("never_used", r2[0].message)

    def test_r2_ok_when_key_used(self):
        findings = self.scan({
            "a.py": "config = {'api_key': 'x'}\nprint(config.get('api_key'))\n",
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_env_file(self):
        findings = self.scan({
            ".env": "API_KEY=abc\n",
            "a.py": "import os\nk = os.getenv('API_KEY')\n",
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_skips_without_config_source(self):
        findings = self.scan({
            "a.py": "import os\nk = os.getenv('NOPE')\n",
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_external_json_load_not_flagged(self):
        # Regression: config loaded from an external file has keys drift
        # cannot see — flagging them was the #1 false-positive source on the
        # crossedge field test (93 of 215 findings).
        findings = self.scan({
            "a.py": "import json\ncfg = json.load(open('cfg.json'))\nprint(cfg.get('granularity'))\n",
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_external_aliased_config_not_flagged(self):
        findings = self.scan({
            "a.py": "import json\ncfg = json.load(open('cfg.json'))\nsettings = cfg\nprint(settings.get('candle_count'))\n",
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_external_read_does_not_mask_real_drift(self):
        findings = self.scan({
            "a.py": "import json\ncfg = json.load(open('cfg.json'))\nconfig = {'a': 1}\nprint(cfg.get('a'))\nprint(config.get('b'))\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "error")
        self.assertIn("b", r2[0].message)  # internal read, never defined

    def test_r2_inline_json_loads_defines_keys(self):
        findings = self.scan({
            "a.py": "import json\ncfg = json.loads('{\"granularity\": 60}')\nprint(cfg.get('granularity'))\nprint(cfg.get('nope'))\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "error")
        self.assertIn("nope", r2[0].message)

    def test_r2_env_typo_warns_when_env_documented(self):
        findings = self.scan({
            ".env": "API_KEY=abc\n",
            "a.py": "import os\nk = os.getenv('API_KEy')\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("API_KEy", r2[0].message)

    def test_r2_env_example_counts_as_documentation(self):
        findings = self.scan({
            ".env.example": "GRANULARITY=60\n",
            "a.py": "import os\nk = os.environ['GRANULARITY']\n",
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_default_get_is_soft_not_error(self):
        # .get(k, default) is an explicit fallback, not silent drift.
        findings = self.scan({
            "a.py": "config = {'a': 1}\nprint(config.get('b', 42))\nprint(config.get('a'))\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("fallback default", r2[0].message)
        self.assertIn("b", r2[0].message)

    def test_r2_uppercase_defaults_dict_defines_keys(self):
        # Regression: DEFAULT_SETTINGS-style constants define config keys.
        findings = self.scan({
            "a.py": "DEFAULT_SETTINGS = {'granularity': 3600, 'fee': 0.004}\ndef f(settings):\n    return settings.get('granularity')\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)  # 'fee' defined but never read
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("fee", r2[0].message)

    def test_r2_alias_receiver_counts_as_config(self):
        # s = self.state.settings — reads through the alias are config reads.
        # FT12: a 1-arg .get on an OUT-OF-VIEW receiver (alias of an external
        # settings object) falls back to None by design — the key may be
        # user-set, so the honest severity is a fallback warning, not a
        # 'never defined anywhere' error.
        findings = self.scan({
            "a.py": (
                "DEFAULT_SETTINGS = {'kraken_margin_test_max_quote': 10.0}\n"
                "s = self.state.settings\n"
                "cap = float(s.get('kraken_margin_test_max_quote', 10))\n"
                "print(s.get('missing_key'))\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("missing_key", r2[0].message)

    def test_r2_helper_list_read_kills_dead_config(self):
        # get_val(['a', 'b'], default) proves the keys are read; it must not
        # produce an error (source may be external) nor a dead-config warning.
        findings = self.scan({
            "a.py": (
                "DEFAULT_SETTINGS = {'telegram_bot_token': '', 'other': 1}\n"
                "def get_val(keys, default=None):\n    return default\n"
                "bot_token = get_val(['telegram_bot_token', 'TELEGRAM_BOT_TOKEN'], '')\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("other", r2[0].message)

    def test_r2_subscript_read_still_error(self):
        findings = self.scan({
            "a.py": "config = {'a': 1}\nprint(config['a'])\nprint(config['b'])\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "error")
        self.assertIn("b", r2[0].message)

    def test_r2_alias_does_not_leak_across_scopes(self):
        # Regression: `s = self.state.settings` in one method must not make
        # `s['type']` in another method's comprehension a config read.
        findings = self.scan({
            "a.py": (
                "DEFAULT_SETTINGS = {'max_symbols': 8}\n"
                "class Bot:\n"
                "    def owner_test(self):\n"
                "        s = self.state.settings\n"
                "        return s.get('max_symbols', 8)\n"
                "    def analyze(self, signals):\n"
                "        return [s['type'] for s in signals]\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(r2, [])

    # --- v0.1.22: attribute-style config reads (kanlaon_watch field case) ---

    def test_r2_attr_read_kills_dead_key(self):
        # Class-style config: keys defined in a defaults dict, consumed via
        # Config(**cfg), read attribute-style (config.alert_threshold).
        # Before v0.1.22 the walk had no Attribute branch, so every key
        # looked 100% dead to R2.
        findings = self.scan({
            "a.py": (
                "DEFAULT_CONFIG = {\n"
                "    'alert_threshold': 3,\n"
                "    'volcano': 'KANLAON',\n"
                "}\n"
                "class Config:\n"
                "    def __init__(self, alert_threshold, volcano):\n"
                "        self.alert_threshold = alert_threshold\n"
                "        self.volcano = volcano\n"
                "def load_config(here):\n"
                "    cfg = dict(DEFAULT_CONFIG)\n"
                "    return Config(**cfg)\n"
                "config = load_config('.')\n"
                "if config.alert_threshold > 1:\n"
                "    print(config.volcano)\n"
            ),
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_attr_read_on_non_config_receiver_does_not_mask_dead(self):
        # An attr read on a receiver that is NOT config-ish must not mask a
        # genuinely dead key.
        findings = self.scan({
            "a.py": (
                "DEFAULT_CONFIG = {'url': 'https://x'}\n"
                "request = None\n"
                "print(request.url)\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("url", r2[0].message)

    def test_r2_attr_read_never_errors_on_undefined_key(self):
        # Method/property access on a config receiver must not produce
        # read-but-never-defined errors: an unknown attribute raises
        # AttributeError (loud), not a silent default, and 'items' is a
        # method name, not a config key.
        findings = self.scan({
            "a.py": (
                "class Config:\n"
                "    def __init__(self, **kw):\n"
                "        pass\n"
                "DEFAULT_CONFIG = {'a': 1}\n"
                "config = Config(**DEFAULT_CONFIG)\n"
                "print(config.items())\n"
                "print(config.timeout)\n"
                "print(DEFAULT_CONFIG['a'])\n"
            ),
        })
        self.assertNotIn("config_drift", self.rules_seen(findings))

    def test_r2_attr_store_is_not_a_read(self):
        # `config.timeout = 9` (Store ctx) must not register as a read:
        # a key that is only ever written is still dead config.
        findings = self.scan({
            "a.py": (
                "class Config:\n"
                "    def __init__(self, **kw):\n"
                "        pass\n"
                "DEFAULT_CONFIG = {'timeout': 5}\n"
                "config = Config(**DEFAULT_CONFIG)\n"
                "config.timeout = 9\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("timeout", r2[0].message)

    # --- R3: magic_number ---

    def test_r2_schema_call_declares_key(self):
        # pre-commit FT13: cfgv-family schema calls declare config keys —
        # Required('key', ...) / Optional('key', ...) count as defined AND
        # consumed by the machinery, so a read of the key is not a ghost
        # and the schema key is never dead config.
        findings = self.scan({
            "a.py": (
                "import cfgv\n"
                "schema = cfgv.Map(\n"
                "    'Config', None,\n"
                "    cfgv.Optional('fail_fast', cfgv.check_bool, False),\n"
                "    cfgv.RequiredRecurse('repos', cfgv.Array()),\n"
                ")\n"
            ),
            "b.py": (
                "def f(config):\n"
                "    return config['fail_fast']\n"
            ),
        })
        self.assertEqual([f for f in findings if f.rule == "config_drift"], [])

    def test_r3_flags_repeated_literal(self):
        findings = self.scan({
            "a.py": "x = 1.0\nz = 2.0\nif x > 0.4:\n    y = 0.4\nif z >= 0.4:\n    w = 0.4\n",
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertEqual(r3[0].severity, "warning")
        self.assertIn("0.4", r3[0].message)

    def test_r2_foreign_options_dict_not_config(self):
        # httpie field-test FP: lexer.options.get('precise') is a pygments
        # lexer option dict, not the app config. Attribute-chain receivers
        # count only when their ROOT is config-ish or self/cls.
        findings = self.scan({
            "a.py": (
                "DEFAULTS = {'theme': 'auto'}\n"
                "def precise(lexer, precise_token, parent_token):\n"
                "    if lexer.options.get('precise'):\n"
                "        return precise_token\n"
                "    return parent_token\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)  # 'theme' dead, 'precise' never flagged
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("theme", r2[0].message)

    def test_r2_chain_read_is_warning_not_error(self):
        # httpie field-test FP: env.config.get('disable_update_warnings') is a
        # documented user-set key. Reads through attribute chains are warning-
        # tier (external key contract), never errors.
        findings = self.scan({
            "a.py": (
                "DEFAULTS = {'theme': 'auto'}\n"
                "def warn(env):\n"
                "    if env.config.get('disable_update_warnings'):\n"
                "        return None\n"
                "def pick(env):\n"
                "    return env.config.get('theme')\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("disable_update_warnings", r2[0].message)
        self.assertNotIn("theme", r2[0].message)

    def test_r2_self_in_config_class_reads_keys(self):
        # httpie field-test FP: Config.default_options is read through
        # self['default_options'] inside the class — not dead config. Reads of
        # undefined keys through self are warning-tier like chains.
        findings = self.scan({
            "a.py": (
                "class Config:\n"
                "    DEFAULTS = {'default_options': []}\n"
                "    @property\n"
                "    def default_options(self):\n"
                "        return self['default_options']\n"
                "    def dev(self):\n"
                "        return self.get('developer_mode')\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("developer_mode", r2[0].message)

    def test_r2_self_in_plain_class_not_config(self):
        # Bare self in a non-config class is not a config receiver.
        findings = self.scan({
            "a.py": (
                "SETTINGS = {'a': 1}\n"
                "class Bot:\n"
                "    def f(self):\n"
                "        return self['a']\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)  # 'a' stays dead
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("a", r2[0].message)

    def test_r3_skips_version_tuples_and_slices(self):
        # httpie field-test noise: (3, 7) version tuples and url[3:] slice
        # bounds are not magic numbers.
        findings = self.scan({
            "a.py": (
                "MIN_SUPPORTED_PY_VERSION = (3, 7)\n"
                "MAX_SUPPORTED_PY_VERSION = (3, 11)\n"
                "s = 'abcd'\n"
                "x = s[3:]\n"
                "y = 0.4\n"
                "if y > 0.4:\n"
                "    z = 0.4\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("0.4", r3[0].message)
        self.assertNotIn("3.0", r3[0].message)

    def test_r3_skips_version_compare_idioms(self):
        # requests field-test noise: (3, 0, 2) <= (major, minor, patch),
        # [1, 3, 4] < crypto_version_list and (3, 7) in supported are all
        # version checks, not magic numbers. Three sites on purpose: without
        # the skips this would hit the repeat threshold and flag.
        findings = self.scan({
            "a.py": (
                "major, minor, patch = map(int, ver.split('.'))\n"
                "assert (3, 0, 2) <= (major, minor, patch) < (8, 0, 0)\n"
                "if crypto_version_list < [1, 3, 4]:\n"
                "    warn(crypto_version_list)\n"
                "if (3, 7) in supported_pairs:\n"
                "    ok()\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(r3, [])

    def test_r3_skips_subscript_compare_and_status_ranges(self):
        # requests field-test noise: _ver[0] == 3 is a Python-major check,
        # 400 <= r.status_code < 500 an HTTP status range, and len(v) == 3 a
        # length bound (v0.1.26, pre-commit FT13: structural, like a slice
        # index). Bare comparisons of the same literal still flag.
        findings = self.scan({
            "a.py": (
                "_ver = sys.version_info\n"
                "is_py3 = _ver[0] == 3\n"
                "if not 400 <= r.status_code < 500:\n"
                "    return r\n"
                "elif 500 <= r.status_code < 600:\n"
                "    raise HttpError()\n"
                "if len(v) == 3:\n"
                "    return v\n"
                "if nullcount == 3:\n"
                "    pad = _null * 3\n"
                "if tally == 3:\n"
                "    bump()\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        # int literals report as ints (v0.1.9): `3`, not `3.0`
        self.assertIn("3 appears 3 times", r3[0].message)
        self.assertNotIn("3.0", r3[0].message)
        self.assertNotIn("500", r3[0].message)

    def test_r3_skips_v0126_structural_contexts(self):
        # pre-commit FT13: a sign-wrapped literal under a named constant
        # (STD_ERROR_HANDLE = -12), power exponents (2 ** 12), string-repeat
        # widths ('=' * 79) and len() comparison bounds (len(args) > 3) are
        # structural — same family as shift counts and slice indices.
        findings = self.scan({
            "a.py": (
                "STD_ERROR_HANDLE = -12\n"
                "SECOND_HANDLE = -12\n"
                "THIRD_HANDLE = -12\n"
                "def f(maximum, args):\n"
                "    bound = max(min(maximum, 2 ** 12), 2 ** 12)\n"
                "    bar = '=' * 79\n"
                "    baz = '-' * 79\n"
                "    if len(args) > 3 or len(args) == 3:\n"
                "        return bound\n"
                "    return bar + baz\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(r3, [])

    def test_r4_raise_and_assert_exprs_are_seen(self):
        # requests field-test gap: the JS engine used to drop the expression
        # in `raise X()` and `assert X` entirely, so phantoms there were
        # invisible. Names in both must be flagged like any other use.
        findings = self.scan({
            "a.py": (
                "def go(ok):\n"
                "    if not ok:\n"
                "        raise Boom()\n"
                "    assert sanity_check\n"
                "    return ok\n"
            ),
        })
        r4 = [f for f in findings if f.rule == "phantom_name"]
        names = [f.message.split("'")[1] for f in r4]
        self.assertIn("Boom", names)
        self.assertIn("sanity_check", names)

    def test_r3_skips_named_constants(self):
        findings = self.scan({
            "a.py": "x = 1.0\nz = 2.0\nMARGIN = 0.4\nif x > MARGIN:\n    y = MARGIN\nif z >= MARGIN:\n    w = MARGIN\n",
        })
        self.assertNotIn("magic_number", self.rules_seen(findings))

    def test_r3_skips_dict_values(self):
        # click field test: _ansi_colors = {"green": 32, ...} — the KEY
        # names the value; flagging the definition site is wrong. The dict
        # values below (30 x3, 32 x3) would both flag pre-fix.
        findings = self.scan({
            "a.py": (
                "ANSIS = {'black': 30, 'green': 32, 'cyan': 36}\n"
                "w = 30\nx = 30\ny = 32\nz = 32\n"
                "if q > 0.4:\n    r = 0.4\nif p >= 0.4:\n    s = 0.4\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("0.4 appears", r3[0].message)
        self.assertNotIn("30 appears", r3[0].message)
        self.assertNotIn("32 appears", r3[0].message)

    def test_r3_keyword_named_positional_still_flag(self):
        # click field test: stacklevel=3 x3 is named by the keyword; the
        # SAME value passed positionally (foo(3) x3) still flags. Pre-fix
        # this counted 6 threes; post-fix exactly the 3 positional ones.
        findings = self.scan({
            "a.py": (
                "warn('a', stacklevel=3)\n"
                "warn('b', stacklevel=3)\n"
                "warn('c', stacklevel=3)\n"
                "foo(3)\nfoo(3)\nfoo(3)\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("3 appears 3 times", r3[0].message)
        self.assertNotIn("6 times", r3[0].message)

    def test_r3_skips_signature_defaults(self):
        # click field test: width: int = 30, col_max: int = 30, width = 36
        # — the parameter name IS the constant's name.
        findings = self.scan({
            "a.py": (
                "def bar(width: int = 30):\n    pass\n"
                "def dl(col_max: int = 30):\n    pass\n"
                "def pb(width: int = 36):\n    pass\n"
                "if x > 0.4:\n    y = 0.4\nif p >= 0.4:\n    s = 0.4\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("0.4 appears", r3[0].message)
        self.assertNotIn("30 appears", r3[0].message)
        self.assertNotIn("36 appears", r3[0].message)

    def test_r3_skips_shift_magnitudes(self):
        # click field test: random.randrange(1 << 32) — the shift count is
        # the unit; 1 << 32 IS the named form of 2**32.
        findings = self.scan({
            "a.py": (
                "a = 1 << 32\nb = 1 << 32\nc = 1 << 32\n"
                "if x > 0.4:\n    y = 0.4\nif p >= 0.4:\n    s = 0.4\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("0.4 appears", r3[0].message)
        self.assertNotIn("32 appears", r3[0].message)

    def test_r3_skips_date_matrix_in_verification_script(self):
        # Sarah's verify_refactor.py field report (v0.1.13): Jan 21, Jun 21,
        # Dec 21 are three different dates sharing a digit, not one constant
        # copied three times. Literals nested in collection literals are
        # data named by the collection. Same shape as a date() call matrix.
        findings = self.scan({
            "verify_refactor.py": (
                "from datetime import date\n"
                "D = lambda m, d: date(2026, m, d)\n"
                "for dt in [D(1, 21), D(6, 21), D(12, 21)]:\n"
                "    check(dt)\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(r3, [])

    def test_r3_skips_tuple_matrix_rows(self):
        # Same report, row-tuple shape: (2026, 1, 21) x3 as a matrix under a
        # lowercase name. Pre-fix this flagged both "2026 appears 3 times"
        # and "21 appears 3 times".
        findings = self.scan({
            "verify_refactor.py": (
                "DATES = [\n"
                "    (2026, 1, 21),\n"
                "    (2026, 6, 21),\n"
                "    (2026, 12, 21),\n"
                "]\n"
                "for y, m, d in DATES:\n"
                "    check(y, m, d)\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(r3, [])

    def test_r3_data_collection_does_not_hide_real_magic(self):
        # The collection skip must not go too far: a literal repeated in
        # LOGIC positions still flags, even when one copy sits in a list
        # (list element is data; the two bare uses are logic).
        findings = self.scan({
            "a.py": (
                "y = 21\n"
                "if x > 21:\n    pass\n"
                "if p >= 21:\n    pass\n"
                "ports = [21]\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("21 appears 3 times", r3[0].message)

    # --- R4: phantom_name ---

    def test_r4_flags_typo(self):
        findings = self.scan({"a.py": "print(misspeled)\n"})
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertEqual(r4[0].severity, "error")
        self.assertIn("misspeled", r4[0].message)

    def test_r4_ok_when_defined(self):
        findings = self.scan({"a.py": "x = 1\nprint(x)\n"})
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_skips_import_star_files(self):
        findings = self.scan({"a.py": "from foo import *\nprint(whatever)\n"})
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_ok_with_imports_and_params(self):
        findings = self.scan({
            "a.py": "import os\n\ndef greet(name):\n    print('hi', name)\n\ngreet('rosie')\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_builtins_exceptions_not_typos(self):
        # Regression: v0.1's hand-typed builtins list missed FileNotFoundError,
        # FileExistsError, UserWarning, Warning — real exception handlers got
        # flagged as phantom names (found on the httpie field test).
        findings = self.scan({
            "a.py": (
                "try:\n"
                "    open('x')\n"
                "except FileNotFoundError:\n"
                "    pass\n"
                "except (FileExistsError, PermissionError):\n"
                "    pass\n"
                "warn = UserWarning('hi')\n"
            ),
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_real_typo_still_flagged(self):
        # The builtins fix must not hide genuine typos.
        findings = self.scan({"a.py": "print(FileNotFoundEr)\n"})
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertIn("FileNotFoundEr", r4[0].message)

    # --- v0.1.4: streamlink field-test regression tests ---

    def test_r4_async_with_binding(self):
        findings = self.scan({"a.py": """
session = object()
url = "x"
async def f():
    async with session.navigate(url) as frame_id:
        await session.loaded(frame_id)
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    def test_r4_async_with_tuple_unpack(self):
        findings = self.scan({"a.py": """
launch = object()
async def f():
    async with launch() as (_nursery, process):
        assert process.poll() is None
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    def test_r4_async_for_binding(self):
        findings = self.scan({"a.py": """
session = object()
async def f():
    async for frame_stopped_loading in session.listen():
        if frame_stopped_loading.frame_id == 1:
            return
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    def test_r4_match_pattern_binding(self):
        findings = self.scan({"a.py": """
import urllib.parse
def f(meta):
    match urllib.parse.urlparse(meta).netloc.split("."), 1:
        case host, *_ if host[-2:] == ["dailymotion", "com"]:
            return host
        case _:
            return None
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    # --- v0.1.6: match-statement fixes (dict pattern crash, `as` inner capture) ---

    def test_r4_match_dict_pattern_binds_and_does_not_crash(self):
        # MatchMapping AST (keys + flat patterns) used to crash _add_match_names.
        findings = self.scan({"a.py": """
def f(cmd):
    match cmd:
        case {"cmd": c, **rest}:
            print(c, rest)
        case _:
            return None
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    def test_r4_match_as_pattern_binds_inner_capture(self):
        # `case [first] as whole:` — `first` used to be flagged phantom because
        # MatchAs recursion read the wrong attribute.
        findings = self.scan({"a.py": """
def f(cmd):
    match cmd:
        case [first] as whole:
            return first, whole
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    def test_r4_match_or_intersection_semantics(self):
        # Only names bound by EVERY alternative are usable; drift keeps the
        # intersection, so a name used in the body but bound in one branch
        # stays flagged (CPython raises on it at runtime too).
        findings = self.scan({"a.py": """
def f(cmd):
    match cmd:
        case ("a", x) | ("b", x):
            return x
        case Point(y=py) | Point(z=py):
            return py
"""})
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)  # Point itself is an undefined load
        self.assertNotIn("x", r4[0].message)

    def test_r4_match_class_kwd_patterns_bind_values_only(self):
        # kwd_attrs (x, y) are attribute names, not bindings; kwd_patterns
        # (px, py) bind.
        findings = self.scan({"a.py": """
class Point:
    pass
Point = Point()
def f(p):
    match p:
        case Point(x=px, y=py):
            return px + py
"""})
        self.assertFalse(any(f.rule == "phantom_name" for f in findings))

    def test_r4_match_value_pattern_does_not_bind(self):
        # Dotted `Color.RED` is a value pattern (a load, not a capture); the
        # bare name RED used in the body stays a phantom.
        findings = self.scan({"a.py": """
class Color:
    pass
Color = Color()
def f(c):
    match c:
        case Color.RED:
            return RED
        case _:
            return None
"""})
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertIn("RED", r4[0].message)

    def test_r4_sphinx_conf_tags(self):
        findings = self.scan({"docs/conf.py": """
tags.add("html")
print(html_theme)
"""})
        r4 = [f for f in findings if f.rule == "phantom_name"]
        # `tags` is Sphinx-injected; html_theme is genuinely undefined and stays flagged
        self.assertEqual(len(r4), 1)
        self.assertIn("html_theme", r4[0].message)

    # --- R4 cross-file star-import resolution (v0.1.14, Phase A) ---

    def test_r4_star_import_resolves_sibling_exports(self):
        findings = self.scan({
            "config.py": "THRESHOLD = 10\n\ndef helper():\n    return 1\n",
            "main.py": "from config import *\nprint(THRESHOLD, helper())\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_star_import_still_flags_typo(self):
        findings = self.scan({
            "config.py": "THRESHOLD = 10\n",
            "main.py": "from config import *\nprint(THRESHOLd)\n",
        })
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertIn("THRESHOLd", r4[0].message)

    def test_r4_star_import_honors_all(self):
        # __all__ wins exactly: SECRET is defined but not in __all__,
        # so `from cfg import *` cannot bind it -> real phantom.
        findings = self.scan({
            "cfg.py": "VALUE = 1\nSECRET = 2\n__all__ = ['VALUE']\n",
            "use.py": "from cfg import *\nprint(VALUE)\nprint(SECRET)\n",
        })
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertIn("SECRET", r4[0].message)

    def test_r4_star_import_underscore_names_not_exported(self):
        findings = self.scan({
            "cfg.py": "_PRIVATE = 1\n",
            "use.py": "from cfg import *\nprint(_PRIVATE)\n",
        })
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertIn("_PRIVATE", r4[0].message)

    def test_r4_external_star_import_still_skips_file(self):
        # Unresolvable star import (stdlib): legacy whole-file skip stays.
        findings = self.scan({"a.py": "from datetime import *\nprint(totally_made_up)\n"})
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_relative_star_import_resolves_package_sibling(self):
        findings = self.scan({
            "pkg/__init__.py": "",
            "pkg/helpers.py": "H = 7\n",
            "pkg/main.py": "from .helpers import *\nprint(H)\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_star_import_chain_resolves_transitively(self):
        findings = self.scan({
            "base.py": "BASE = 1\n",
            "mid.py": "from base import *\nOWN = 2\n",
            "top.py": "from mid import *\nprint(BASE, OWN)\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_mixed_resolvable_and_external_star_skips_file(self):
        findings = self.scan({
            "config.py": "THRESHOLD = 10\n",
            "main.py": "from config import *\nfrom datetime import *\nprint(THRESHOLD, made_up)\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_star_import_cycle_skips_file(self):
        findings = self.scan({
            "a.py": "from b import *\nA = 1\n",
            "b.py": "from a import *\nB = 2\n",
            "use.py": "from a import *\nprint(A, made_up)\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_plain_import_names_are_exported(self):
        # CPython 3.11 probe: `from m import *` DOES bind plain-import names.
        findings = self.scan({
            "m.py": "import os\n",
            "use.py": "from m import *\nprint(os)\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_star_import_exports_sibling_submodule_name(self):
        # Probe-verified: `from .helpers import *` in a package also binds
        # the sibling submodule name on the package.
        findings = self.scan({
            "pkg/__init__.py": "from .helpers import *\n",
            "pkg/helpers.py": "H = 7\n",
            "main.py": "from pkg import *\nprint(helpers.H)\n",
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r1_ignores_external_import_collision(self):
        # get_version is imported from an external lib; the same-named
        # function in browser.py must NOT be used as the callee (v0.1.3
        # resolved it wrong — the _version.py streamlink FP).
        findings = self.scan({
            "lib.py": "def get_version():\n    pass\n",
            "a.py": """
from versioningit import get_version
__version__ = get_version(project_dir=".")
""",
        })
        self.assertFalse(any(f.rule == "unexpected_kwarg" for f in findings))

    def test_r1_skips_pytest_fixture_callee(self):
        findings = self.scan({
            "conftest.py": """
import pytest
@pytest.fixture()
def webbrowser_launch(monkeypatch, caplog):
    return lambda **kw: kw
""",
            "test_a.py": """
import pytest
async def test_x(webbrowser_launch):
    async with webbrowser_launch(webbrowser=1, headless=True):
        pass
""",
        })
        self.assertFalse(any(f.rule == "unexpected_kwarg" for f in findings))

    def test_r1_resolves_same_project_import(self):
        findings = self.scan({
            "pkg/__init__.py": "",
            "pkg/order_execution.py": "def place(order, venue=None):\n    pass\n",
            "pkg/bot.py": "from pkg.order_execution import place\nplace(side=1)\n",
        })
        r1 = [f for f in findings if f.rule == "unexpected_kwarg"]
        self.assertEqual(len(r1), 1)
        self.assertIn("side", r1[0].message)

    def test_r2_inline_constructor_dict_defines_keys(self):
        findings = self.scan({
            "opts.py": """
class Options:
    def __init__(self, d):
        self.d = d
    def get(self, k):
        return self.d.get(k)
""",
            "stream.py": """
class StreamOptions(Options):
    def __init__(self, session):
        super().__init__({"hls-live-edge": 3, "stream-timeout": 60.0})
""",
            "use.py": """
from stream import StreamOptions
options = StreamOptions(None)
x = options.get("hls-live-edge")
y = options.get("stream-timeout")
""",
        })
        self.assertFalse(any(f.rule == "config_drift" and f.severity == "error" for f in findings))

    def test_r2_get_option_and_set_option_tracked(self):
        findings = self.scan({"a.py": """
class Plugin:
    def get_option(self, k):
        return self.options.get(k)
    def set_option(self, k, v):
        self.options.set(k, v)

def run(p):
    p.set_option("stream-timeout", 60)
    return p.get_option("stream-timeout")
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_dash_underscore_keys_equivalent(self):
        findings = self.scan({"a.py": """
config = {"purge-credentials": False}
x = config.get("purge_credentials")
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_dict_copy_is_still_config(self):
        findings = self.scan({"a.py": """
settings = {"telegram_alert_on_buy": True}

def tick():
    settings = dict(settings)
    if settings.get("telegram_alert_on_buy", True):
        send()
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_dynamic_key_read_kills_dead_keys(self):
        # isort FT11: CONFIG_SECTIONS looked 100% dead because every read
        # (settings.py:317 .get(expr), 756/796 subscript[var]) used a
        # variable key. A dynamic-keyed read can hit ANY key of that dict,
        # so none is provably dead — but a genuinely dead key in a separate
        # dict must still fire.
        findings = self.scan({"settings.py": """
CONFIG_SECTIONS = {
    ".editorconfig": "editor",
    ".isort.cfg": "isort",
    "pyproject.toml": "pyproject",
}
cfg = {"abandoned": 1}

def lookup(name):
    return CONFIG_SECTIONS.get(name, {})

def grab(name):
    return CONFIG_SECTIONS[name]
"""})
        dead = [f for f in findings if f.rule == "config_drift" and f.severity == "warning"]
        self.assertEqual([f.message.split("'")[1] for f in dead], ["abandoned"])

    def test_r2_dynamic_attr_read_kills_class_defaults(self):
        # self.defaults[var] inside a config class covers every key defined
        # in the class-level defaults literal (attr receivers register under
        # the attribute name, mirroring v0.1.22's attr bucket).
        findings = self.scan({"a.py": """
class Config:
    defaults = {"port": 8080, "host": "127.0.0.1"}
    def get(self, key):
        return self.defaults[key]
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_env_payload_dict_is_data_not_config(self):
        # isort FT11: `env = {**os.environ, "LANG": "C.UTF-8"}` was flagged
        # as dead config key LANG. An env-merge literal is a child-process
        # env payload — data, not config (Sarah's data rule). The target is
        # demoted too, so a later env.get(...) never reads as config.
        findings = self.scan({"a.py": """
import os
import subprocess

def run(cmd):
    env = {**os.environ, "LANG": "C.UTF-8"}
    return subprocess.check_output(cmd, env=env)

cfg = {"lonely": 1}
"""})
        dead = [f for f in findings if f.rule == "config_drift" and f.severity == "warning"]
        self.assertEqual([f.message.split("'")[1] for f in dead], ["lonely"])

    def test_r2_env_payload_target_demoted(self):
        # env.get(...) on a demoted payload target must not become a
        # read-but-never-defined config error.
        findings = self.scan({"a.py": """
import os

def run():
    env = {**os.environ, "LANG": "C.UTF-8"}
    return env.get("LANG", "en")
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_pluginargument_defines_keys(self):
        findings = self.scan({
            "plugin.py": """
class Plugin:
    def get_option(self, k):
        return None
""",
            "twitch.py": """
from plugin import pluginargument, Plugin
@pluginargument("force-client-integrity", action="store_true")
class Twitch(Plugin):
    def run(self):
        return self.get_option("force-client-integrity")
""",
        })
        self.assertFalse(any(f.rule == "config_drift" and f.severity == "error" for f in findings))

    def test_r2_local_dict_not_config(self):
        findings = self.scan({"a.py": """
def fetch():
    return {"id": 1, "title": "x"}

def run():
    options = fetch()
    self_id = options["id"]
    self_title = options["title"]
    return self_id, self_title
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_real_undefined_read_still_flagged(self):
        findings = self.scan({
            "opts.py": "class Options:\n    def get(self, k):\n        return None\n",
            "a.py": """
from opts import Options
options = Options()
x = options.get("typo-key")
""",
        })
        # FT12: options is an Options() instance — out-of-view receiver, so a
        # 1-arg .get is a fallback warning, not a provable-ghost error. (An
        # in-view dict or literal-returner-backed receiver still errors.)
        r2 = [f for f in findings if f.rule == "config_drift" and f.severity == "warning"]
        self.assertEqual(len(r2), 1)
        self.assertIn("typo-key", r2[0].message)

    # --- FT12 (pelican 4.12.0) regression family ---

    def test_r2_setdefault_defines_key(self):
        # setdefault(key, default) DEFINES the key when missing: config built
        # by setdefault must not read as ghost keys (pelican MarkdownReader).
        findings = self.scan({
            "a.py": (
                "def f(settings):\n"
                "    settings.setdefault('extension_configs', {})\n"
                "    settings.setdefault('extensions', [])\n"
                "    for ext in settings['extension_configs'].keys():\n"
                "        if ext not in settings['extensions']:\n"
                "            settings['extensions'].append(ext)\n"
                "    return settings\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(r2, [])

    def test_r2_presence_tested_key_demotes_to_warning(self):
        # `if "KEY" in settings:` marks the key optional for the scope — a
        # later bare read warns, never claims a silent default (pelican
        # deprecated-setting migrations).
        findings = self.scan({
            "a.py": (
                "def migrate(settings):\n"
                "    if 'PLUGIN_PATH' in settings:\n"
                "        settings['PLUGIN_PATHS'] = settings['PLUGIN_PATH']\n"
                "        del settings['PLUGIN_PATH']\n"
                "    return settings\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("PLUGIN_PATH", r2[0].message)
        self.assertIn("optional", r2[0].message)

    def test_r2_fallback_guarded_subscript_demotes(self):
        # a bare subscript guarded by a .get(k, default) on the same line is
        # optional, not a provable ghost; exactly one fallback warning fires
        # (pelican readers.py default_metadata DEFAULT_DATE).
        findings = self.scan({
            "a.py": (
                "def f(settings):\n"
                "    if settings.get('DEFAULT_DATE', None) and settings['DEFAULT_DATE'] != 'fs':\n"
                "        return settings['DEFAULT_DATE']\n"
                "    return None\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("DEFAULT_DATE", r2[0].message)

    def test_r2_get1arg_outofview_is_fallback_warning(self):
        # 1-arg .get on an OUT-OF-VIEW receiver (param) falls back to None:
        # warning, not a 'never defined anywhere' error (pelican
        # AUTORELOAD_IGNORE_CACHE migration).
        findings = self.scan({
            "a.py": (
                "def f(settings):\n"
                "    if settings.get('AUTORELOAD_IGNORE_CACHE'):\n"
                "        pass\n"
                "    return settings\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("AUTORELOAD_IGNORE_CACHE", r2[0].message)

    def test_r2_get1arg_inview_keeps_error(self):
        # 1-arg .get on a receiver whose full key set is known in-file is a
        # PROVABLE ghost — the error stays.
        findings = self.scan({
            "a.py": "config = {'api_key': 'x'}\nprint(config.get('missing_key'))\n",
        })
        r2 = [f for f in findings if f.rule == "config_drift" and f.severity == "error"]
        self.assertEqual(len(r2), 1)
        self.assertIn("missing_key", r2[0].message)

    def test_r2_callarg_consumption_kills_dead_keys(self):
        # a config dict handed to a call is consumed by the callee (template
        # renderers, builders) — no key of it is provably dead
        # (pelican_quickstart CONF -> Jinja templates).
        findings = self.scan({
            "a.py": (
                "def render(tmpl, vars):\n"
                "    return tmpl % vars\n"
                "CONF = {'pelican': 'pelican', 'basedir': '.', 'ssh_host': 'x'}\n"
                "out = render('Makefile', CONF)\n"
                "print(CONF['basedir'])\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(r2, [])

    def test_r2_multiread_ghost_reports_source_first_line(self):
        # F1: several reads of one ghost key — the finding carries the
        # SOURCE-FIRST read's line in BOTH engines (py used ast.walk
        # breadth-first and picked a depth-arbitrary line).
        findings = self.scan({
            "a.py": (
                "def f(settings):\n"
                "    settings['x'] = 1\n"
                "    a = settings['ghost_key']\n"
                "    b = settings['ghost_key']\n"
                "    return a, b\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift" and f.severity == "error"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].line, 3)
        self.assertIn("ghost_key", r2[0].message)

    def test_r2_method_returned_literal_defines_keys(self):
        # pyjwt field-test pattern: self.options is built from a method that
        # returns a plain dict literal. Its keys are definitions, so reads
        # through self.options (direct, .get, and via an alias) are not drift.
        findings = self.scan({"a.py": """
class PyJWS:
    @staticmethod
    def _get_default_options():
        return {"verify_signature": True, "enforce_minimum_key_length": False}

    def __init__(self):
        self.options = self._get_default_options()

    def decode(self):
        merged = self.options
        if merged["verify_signature"]:
            return self.options.get("enforce_minimum_key_length", False)
        return None
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_annassign_method_returned_literal_defines_keys(self):
        # AnnAssign variant: self.options: dict = self._get_default_options()
        findings = self.scan({"a.py": """
class C:
    def _get_default_options(self):
        'docstring'
        return {"require": [], "strict_aud": False}

    def __init__(self):
        self.options: dict = self._get_default_options()

    def check(self):
        return self.options["require"], self.options.get("strict_aud", False)
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_attr_target_dict_literal_defines_keys(self):
        # Direct literal assigned to a config-named attribute also defines.
        findings = self.scan({"a.py": """
class C:
    def __init__(self):
        self.options = {"api_key": "x", "timeout": 30}

    def run(self):
        return self.options["api_key"], self.options.get("timeout")
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    # --- v0.1.11: non-assignment bindings (with/for/except) are plain locals ---

    def test_r2_with_bound_configish_name_not_config(self):
        # `with open(...) as config:` / `async with ... as options:` bind a
        # plain local, not a config receiver (aiohttp session FP class).
        findings = self.scan({"a.py": """
import aiohttp

async def fetch():
    async with aiohttp.ClientSession() as options:
        timeout = options.get("timeout", 30)
    return timeout

def load():
    with open("cfg.json") as config:
        v = config["retries"]
    return v
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_for_bound_configish_name_not_config(self):
        # Loop targets are elements of the iterable, not the config object.
        findings = self.scan({"a.py": """
def a():
    for options in [{"a": 1}]:
        v = options.get("timeout", 30)
    return v

async def b():
    async for config in items():
        v = config["retries"]
    return v

async def items():
    return []
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_except_bound_configish_name_not_config(self):
        # The except-as name is an exception object, never config.
        findings = self.scan({"a.py": """
def c():
    try:
        x = 1 / 0
    except ValueError as settings:
        v = settings.get("code", 5)
    return v
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r2_configy_constructor_with_keeps_config_ness(self):
        # `with Config() as config:` — the context expr is a config-y
        # constructor, so reads through the bound name still register.
        # FT12: 1-arg .get on an out-of-view instance (Config()) is a
        # fallback read — warning, not error; only in-view receivers whose
        # defs are known keep the provable-ghost error.
        findings = self.scan({"a.py": """
class Config:
    def get(self, k, default=None):
        return default

async def e():
    with Config() as config:
        v = config.get("timeout", 30)
        hard = config.get("api_key")
    return v, hard

async def f():
    async with make_options() as options:
        v = options.get("retries", 3)
    return v

async def make_options():
    return Config()
"""})
        r2 = [f for f in findings if f.rule == "config_drift"]
        sev = sorted(f.severity for f in r2)
        self.assertEqual(sev, ["warning", "warning", "warning"])
        msgs = " ".join(f.message for f in r2)
        self.assertIn("api_key", msgs)
        self.assertIn("timeout", msgs)
        self.assertIn("retries", msgs)

    def test_r2_for_configish_iterable_keeps_config_ness(self):
        # `for config in cfg:` — a config-ish iterable keeps the bound name
        # config-ish (its elements are config objects).
        findings = self.scan({"a.py": """
cfg = {"timeout": 30}

def g():
    for config in cfg:
        v = config.get("retries", 3)
        hard = config["api_key"]
    return v, hard
"""})
        r2 = [f for f in findings if f.rule == "config_drift"]
        sev = sorted(f.severity for f in r2)
        self.assertEqual(sev, ["error", "warning", "warning"])
        msgs = " ".join(f.message for f in r2)
        self.assertIn("api_key", msgs)
        self.assertIn("retries", msgs)
        self.assertIn("timeout", msgs)  # defined but never read: dead config

    def test_r2_non_literal_call_still_not_config(self):
        # A call that is NOT a literal-returning defaults method still marks
        # the config-named target as a plain local dict (no findings at all).
        findings = self.scan({"a.py": """
def build():
    return {"id": 1}

def run():
    options = build()
    return options["id"]
"""})
        self.assertFalse(any(f.rule == "config_drift" for f in findings))

    def test_r3_int_display_not_float(self):
        # (bit_length + 7) // 8 three times: the message says `7`, `8`,
        # not `7.0` / `8.0` (pyjwt field test).
        findings = self.scan({"a.py": """
def a(x):
    return (x + 7) // 8

def b(x):
    return (x + 7) // 8

def c(x):
    return (x + 7) // 8
"""})
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 2)
        self.assertIn("7 appears 3 times", r3[0].message)
        self.assertIn("8 appears 3 times", r3[1].message)
        self.assertTrue(all(".0" not in f.message for f in r3))

    def test_r3_skips_test_files(self):
        # Repetition in test files is test data, not unnamed constants
        # (pyjwt field test: 65537 x6, 1024 x5).
        findings = self.scan({
            "tests/test_x.py": "def t():\n    return (123, 123, 123)\n",
            "a.py": "def a(x):\n    return (x + 7) // 8\n\ndef b(x):\n    return (x + 7) // 8\n\ndef c(x):\n    return (x + 7) // 8\n",
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 2)
        self.assertTrue(all("test_x" not in f.file for f in r3))

    # --- clean project ---

    def test_clean_project_has_no_findings(self):
        findings = self.scan({
            "a.py": "import os\n\nCONFIG = {'PORT': 8080}\n\ndef start(port):\n    return os.getenv('PORT', port)\n\nstart(CONFIG['PORT'])\n",
        })
        self.assertEqual(findings, [])

    # --- CLI ---

    def test_cli_json_and_exit_code(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.py").write_text(
                "class Foo:\n    def __init__(self, a):\n        pass\nf = Foo(b=1)\n",
                encoding="utf-8",
            )
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "drift.py"), "--json", td],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(r.returncode, 1)
            data = json.loads(r.stdout)
            self.assertTrue(any(d["rule"] == "unexpected_kwarg" for d in data))

    def test_cli_clean_exit_zero(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.py").write_text("x = 1\nprint(x)\n", encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "drift.py"), td],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(r.returncode, 0)

    def test_cli_rules_accepts_descriptive_name(self):
        # --rules magic_number must mean R3, not silently scan nothing
        # (found live on Sarah's algiers_sun.py field test).
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.py").write_text(
                "def f(x):\n    return (x + 7) // 8\n\ndef g(x):\n    return (x + 7) // 8\n\ndef h(x):\n    return (x + 7) // 8\n",
                encoding="utf-8",
            )
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "drift.py"),
                 "--rules", "magic_number", td],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(r.returncode, 0)  # warning, not error
            self.assertIn("7 appears 3 times", r.stdout)
            self.assertIn("8 appears 3 times", r.stdout)

    def test_cli_rules_unknown_name_fails_loudly(self):
        # The footgun this guards: --rules bogus used to scan nothing and
        # report a clean bill of health.
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.py").write_text(
                "class Foo:\n    def __init__(self, a):\n        pass\nf = Foo(b=1)\n",
                encoding="utf-8",
            )
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "drift.py"),
                 "--rules", "bogus", td],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(r.returncode, 2)
            self.assertIn("unknown rule", r.stderr)
            self.assertNotIn("unexpected_kwarg", r.stdout)

    def test_analyze_rejects_unknown_rule(self):
        with self.assertRaises(ValueError):
            drift.analyze(["."], rules="R1,banana")

    # --- v0.1.15: dateutil field test #8 regressions ---

    def test_r4_windows_error_is_compat_name(self):
        # dateutil field test: `except WindowsError:` in tz/win.py and
        # tz/tz.py is a py2 builtin that py3 keeps as an OSError alias on
        # Windows — deliberate compat code, not a typo.
        findings = self.scan({
            "a.py": (
                "import os\n"
                "def _settzkeyname():\n"
                "    try:\n"
                "        os.open('x', os.O_RDONLY)\n"
                "    except WindowsError:\n"
                "        return None\n"
            ),
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))

    def test_r4_windows_error_typo_still_flagged(self):
        findings = self.scan({"a.py": "try:\n    pass\nexcept WindowsErrror:\n    pass\n"})
        r4 = [f for f in findings if f.rule == "phantom_name"]
        self.assertEqual(len(r4), 1)
        self.assertIn("WindowsErrror", r4[0].message)

    def test_r3_mixed_int_float_reports_both_forms(self):
        # dateutil field test: 44 int 7s + relativedelta's `days / 7.0` used
        # to print "7.0 appears 45 times" at an int anchor. A mixed bucket
        # must name both forms.
        findings = self.scan({"a.py": "x = 7\ny = 7.0\nz = 7\n"})
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("7 / 7.0 appears 3 times", r3[0].message)

    def test_r3_uniform_buckets_keep_own_forms(self):
        findings = self.scan({"a.py": "x = 7\ny = 7\nz = 7\n"})
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("7 appears 3 times", r3[0].message)
        self.assertNotIn("7.0", r3[0].message)
        findings = self.scan({"a.py": "x = 7.0\ny = 7.0\nz = 7.0\n"})
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("7.0 appears 3 times", r3[0].message)

    def test_r3_big_int_families_not_merged(self):
        # float() bucketing collapsed 2**53 and 2**53+1 into one family.
        # Exact int keys keep them apart: three singletons, zero findings.
        findings = self.scan({
            "a.py": (
                "def f():\n"
                "    return 9007199254740992\n"
                "def g():\n"
                "    return 9007199254740993\n"
                "def h():\n"
                "    return 9007199254740994\n"
            ),
        })
        self.assertNotIn("magic_number", self.rules_seen(findings))

    def test_r3_chained_tuple_assign_binds_and_counts(self):
        # dateutil field test: `MO, TU, ... SU = weekdays = tuple(...)` —
        # the JS parser dropped the chain tail (phantom `weekdays`, lost
        # range(7)). The chain must bind every target and keep every RHS
        # literal.
        findings = self.scan({
            "a.py": (
                "def weekday(x):\n"
                "    return x\n"
                "MO, TU, WE, TH, FR, SA, SU = weekdays = tuple(weekday(x) for x in range(7))\n"
                "def f():\n"
                "    return TU + 7\n"
                "def g():\n"
                "    return SU + 7\n"
            ),
        })
        self.assertNotIn("phantom_name", self.rules_seen(findings))
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("7 appears 3 times", r3[0].message)

    # --- v0.1.18: negative slice/index bounds (Aether review 08-25) ---

    def test_r3_negative_slice_bounds_not_magic(self):
        # name[-3:] / x[-3] — the sign is part of the index. CPython keeps
        # UnaryOp(USub) inside subscripts/slices (a bare -3 folds to
        # Constant(-3)), so the digit leaked into the magic tally — in the
        # shipped CLI, not just the browser engine.
        findings = self.scan({
            "a.py": (
                "def demo(name, x):\n"
                "    if x == 3 or x == 3:\n"
                "        pass\n"
                "    z = name[-3:]\n"
                "    w = x[-3]\n"
                "    return z, w\n"
            ),
        })
        self.assertEqual([f for f in findings if f.rule == "magic_number"], [])

    def test_r3_negative_comparison_still_counts(self):
        # -3 in a comparison is a genuine magic constant — the skip must
        # only apply to subscript/slice positions, never to expressions.
        findings = self.scan({
            "a.py": (
                "def demo(x):\n"
                "    if x == -3:\n"
                "        pass\n"
                "    if x == -3:\n"
                "        pass\n"
                "    if x == -3:\n"
                "        pass\n"
                "    return x\n"
            ),
        })
        r3 = [f for f in findings if f.rule == "magic_number"]
        self.assertEqual(len(r3), 1)
        self.assertIn("3 appears 3 times", r3[0].message)

    def test_r3_fstring_negative_step_chained_indices_not_magic(self):
        # f-string path: x[1:10:2] / name[-3:] / a[1][3] / row[::3] — step
        # groups, negatives and chained brackets. Python parses real ast
        # (only the UnaryOp skip was needed); the JS idxRe regex needed all
        # three (Aether's corpus seeds).
        findings = self.scan({
            "a.py": (
                "def demo(x, name, row, a):\n"
                "    if x == 3 or x == 3:\n"
                "        pass\n"
                "    return (f\"{x[1:10:2]}\", f\"{name[-3:]}\",\n"
                "            f\"{a[1][3]}\", f\"{row[::3]}\")\n"
            ),
        })
        self.assertEqual([f for f in findings if f.rule == "magic_number"], [])

    def test_r1_starred_assignment_targets_bind(self):
        # *rest = xs / *_, most = xs — the JS parser used to throw at a
        # statement-level `*`, skipping the line and losing the binding
        # (blib2to3/pgen2/parse.py, black src tree, field parity #10).
        findings = self.scan({
            "a.py": (
                "def f(alive):\n"
                "    ilabel, *rest = alive\n"
                "    *_, most = alive\n"
                "    if not rest:\n"
                "        return ilabel\n"
                "    return most\n"
            ),
        })
        self.assertEqual([f for f in findings if f.rule == "phantom_name"], [])

    # --- review F1 (Aether, v0.1.23): implicit-tuple RHS parser gap ---
    # The JS engine parsed assignment/return/yield RHS as a single
    # expression, so any bare comma list after `=` threw and the WHOLE file
    # was skipped as clean (`args = pos, *rest`, tomli/_parser.py:117 — and
    # even plain `x = 1, 2`). Corpus r2_implicit_tuple_* pins parity; these
    # pin the Python-side contract: a dead key in the same file must fire.

    def test_implicit_tuple_forms_still_scan(self):
        forms = [
            "args = pos, *rest\n",
            "plain = 1, 2\n",
            "one = 1,\n",
            "x = *a, b\n",
            "a = b = c, d\n",
            "x: int = 1, 2\n",
            "return a, *b\n",
            "yield a, *b\n",
            "for x in a, *b:\n        pass\n",
        ]
        for form in forms:
            if form.startswith("return"):
                src = "def f(a, *b):\n    " + form
            elif form.startswith("yield"):
                src = "def f(a, *b):\n    " + form
            elif form.startswith("for "):
                src = "def f(a, *b):\n    " + form + "\n    return x\n"
            elif form.startswith("x: "):
                src = "def f(a, b):\n    " + form + "\n    return x\n"
            elif form.startswith("a = b"):
                src = "def f(c, d):\n    " + form + "\n    return a, b\n"
            elif form.startswith("x = "):
                src = "def f(a, *b):\n    " + form + "\n    return x\n"
            elif form.startswith("args"):
                src = "def f(pos, *rest):\n    " + form + "\n    return args\n"
            else:
                src = "def f(pos, *rest):\n    " + form + "\n    return one\n"
            findings = self.scan({
                "a.py": src + "config = {'never_used': 1}\n",
            })
            r2 = [f for f in findings if f.rule == "config_drift"]
            self.assertEqual(len(r2), 1, f"form {form!r} must keep the file scannable")

    # --- review F2 (Aether, v0.1.23): walker skip-dir path matching ---

    def test_scan_root_inside_site_packages_scans(self):
        # SKIP_DIRS used to match ANY absolute path part, so scanning a tree
        # rooted under a dir named site-packages silently zero-scanned.
        with tempfile.TemporaryDirectory() as td:
            sp = Path(td) / "site-packages"
            p = sp / "mod.py"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("config = {'never_used': 1}\n", encoding="utf-8")
            findings, _notes = drift.analyze([str(sp)], rules="R2")
            r2 = [f for f in findings if f.rule == "config_drift"]
            self.assertEqual(len(r2), 1)

    def test_subdir_site_packages_still_skipped(self):
        # ...but a site-packages SUBDIR inside a normal root stays skipped
        # (vendored trees are not scan scope).
        findings = self.scan({
            "pkg/site-packages/mod.py": "config = {'never_used': 1}\n",
        }, rules="R2")
        self.assertEqual([f for f in findings if f.rule == "config_drift"], [])

    def test_all_skipped_dir_is_loud_not_clean(self):
        # a directory whose .py files are ALL consumed by skip dirs must
        # never report a clean bill: analyze() notes it, main() exits 2.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "__pycache__" / "mod.py"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("config = {'never_used': 1}\n", encoding="utf-8")
            findings, notes = drift.analyze([td], rules="R2")
            self.assertEqual(findings, [])
            self.assertTrue(any(n.startswith("drift: nothing scanned") for n in notes))
            self.assertEqual(drift.main([td, "--rules", "R2"]), 2)

    def test_r2_fstring_get_quoted_str_default_registers_soft_read(self):
        # FT12 residual (Aether, closed v0.1.25): an f-string .get with a
        # QUOTED-STRING default was invisible to the JS engine's f-string
        # scanner (its default group excluded quotes, so the whole match
        # failed and the soft read never registered). py always saw the
        # real AST; this pins the py side of the contract the JS fix now
        # matches: a 2-arg .get inside an f-string registers a soft read
        # — an existing key stays quiet, a never-defined key demotes to
        # the fallback warning (not an error). Numeric and name defaults
        # keep their old behavior.
        findings = self.scan({
            "a.py": (
                "cfg = {'A_KEY': 'x'}\n"
                "print(f\"v={cfg.get('A_KEY', 'strdef')}\")\n"
                "print(f\"w={cfg.get('MISSING', 'fallback')}\")\n"
                "print(f\"n={cfg.get('A_KEY', 5)}\")\n"
                "print(f\"d={cfg.get('A_KEY', DEFAULT_NAME)}\")\n"
            ),
        })
        r2 = [f for f in findings if f.rule == "config_drift"]
        self.assertEqual(len(r2), 1)
        self.assertEqual(r2[0].severity, "warning")
        self.assertIn("fallback default", r2[0].message)
        self.assertIn("MISSING", r2[0].message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
