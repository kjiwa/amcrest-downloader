"""Repo-level invariants: no machine-local path is tracked, shell scripts are valid,
and console scripts resolve.
"""

import importlib
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
LEAK_RE = re.compile(r"/(?:Users|home)/([A-Za-z0-9_.-]+)")
ALLOWED_USER = "user"


def _tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return [ROOT / line for line in output.splitlines() if line]


def _in_work_tree() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True, check=False
    )
    return result.returncode == 0


def _shell_scripts() -> list[str]:
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "scripts").glob("*.sh"))


def _console_scripts() -> dict[str, str]:
    text = (ROOT / "pyproject.toml").read_text()
    match = re.search(r"^\[project\.scripts\]\n((?:.+\n?)*)", text, re.MULTILINE)
    if not match:
        return {}
    return dict(re.findall(r'^(\S+) = "([^"]+)"', match.group(1), re.MULTILINE))


class NoLocalPathLeaksTests(unittest.TestCase):
    @unittest.skipUnless(_in_work_tree(), "not inside a git work tree")
    def test_no_tracked_text_file_names_a_real_home_directory(self):
        offenders = []
        for path in _tracked_files():
            if not path.is_file():
                continue
            data = path.read_bytes()
            if b"\x00" in data[:8000]:
                continue
            for match in LEAK_RE.finditer(data.decode(errors="ignore")):
                if match.group(1) != ALLOWED_USER:
                    offenders.append(f"{path.relative_to(ROOT)}: {match.group(0)}")
        self.assertEqual(offenders, [])


class ShellScriptTests(unittest.TestCase):
    def test_scripts_parse(self):
        scripts = _shell_scripts()
        self.assertTrue(scripts)
        for script in scripts:
            result = subprocess.run(
                ["sh", "-n", script], cwd=ROOT, capture_output=True, text=True, check=False
            )
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck is not installed")
    def test_scripts_pass_shellcheck(self):
        scripts = _shell_scripts()
        self.assertTrue(scripts)
        result = subprocess.run(
            ["shellcheck", *scripts], cwd=ROOT, capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ConsoleScriptTests(unittest.TestCase):
    def test_targets_resolve_to_callables(self):
        scripts = _console_scripts()
        self.assertTrue(scripts)
        for name, target in scripts.items():
            module, _, attr = target.partition(":")
            self.assertTrue(callable(getattr(importlib.import_module(module), attr)), name)


if __name__ == "__main__":
    unittest.main()
