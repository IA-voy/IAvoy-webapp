"""Corre los tests del repo y recorta la salida a lo que el modelo necesita para corregir."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_NOISE = re.compile(
    r"site-packages|node_modules|<frozen |^\s*$|^platform |^rootdir|^plugins:|^cachedir|^collect"
    r"|^=+ (test session starts|warnings summary)|DeprecationWarning|^\s*-- Docs:"
)
_SIGNAL = re.compile(
    r"Error|Exception|assert|FAILED|FAIL\b|failed|Expected|Received|expected|received|"
    r"Traceback|^E\s|^>\s|●|✕|✗|\bat\s.+:\d+"
)


@dataclass
class TestRun:
    passed: bool
    exit_code: int
    output: str
    timed_out: bool = False


def detect_test_command(root: str | Path) -> str | None:
    root = Path(root)
    package = root / "package.json"
    if package.is_file():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
        except json.JSONDecodeError:
            scripts = {}
        if "test" in scripts:
            return "npm test --silent"
    if (root / "pytest.ini").exists() or (root / "tests").is_dir() or any(root.glob("test_*.py")):
        return "python -m pytest -q"
    if (root / "pyproject.toml").exists():
        return "python -m pytest -q"
    return None


def _text(data: str | bytes | None) -> str:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def run_tests(root: str | Path, command: str, timeout: int = 180) -> TestRun:
    # Sin esto, en Windows los subprocesos de Python escriben en cp1252 y los acentos llegan rotos.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "FORCE_COLOR": "0", "NO_COLOR": "1"}
    try:
        proc = subprocess.run(
            command, shell=True, cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired as e:
        out = _text(e.stdout) + _text(e.stderr)
        return TestRun(False, -1, out + f"\n[timeout tras {timeout}s]", timed_out=True)
    return TestRun(proc.returncode == 0, proc.returncode, proc.stdout + proc.stderr)


def trim_output(output: str, max_tokens: int = 400) -> str:
    """Conserva las líneas con señal (errores, asserts, frames propios) y descarta el ruido."""
    lines = output.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _SIGNAL.search(line) and not _NOISE.search(line):
            keep.update(range(max(0, i - 1), min(len(lines), i + 3)))
    keep = {i for i in keep if not _NOISE.search(lines[i])}

    if keep:
        out, last = [], -2
        for i in sorted(keep):
            if i != last + 1:
                out.append("...")
            out.append(lines[i])
            last = i
    else:
        out = [line for line in lines if not _NOISE.search(line)][-30:]

    # El resumen final (p. ej. "1 failed, 2 passed") casi siempre es útil.
    tail = next((line for line in reversed(lines) if line.strip()), "")
    if tail and tail not in out:
        out.append(tail)

    text = "\n".join(out)
    max_chars = max_tokens * 4
    if len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + "\n... (recortado) ...\n" + text[-half:]
    return text
