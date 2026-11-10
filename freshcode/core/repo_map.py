"""Mapa compacto del repo: rutas y firmas de símbolos, sin el cuerpo del código.

Python se analiza con `ast`; JS/TS con expresiones regulares por línea. Es menos preciso
que tree-sitter, pero no tiene dependencias y alcanza para que el planner ubique archivos.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from freshcode.llm.fake import estimate_tokens

IGNORED_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".turbo", ".freshcode",
}
IGNORED_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock"}
PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
TEXT_EXT = PY_EXT | JS_EXT | {
    ".json", ".toml", ".md", ".css", ".html", ".yml", ".yaml", ".txt", ".cfg", ".ini", ".sql", ".sh",
}
MAX_FILE_BYTES = 200_000

_JS_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(?P<name>\w+)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(?P<name>\w+)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"),
    re.compile(r"^\s*(?:export\s+)?(?:interface|type|enum)\s+(?P<name>\w+)"),
    re.compile(r"^\s*export\s+(?:const|let|var)\s+(?P<name>\w+)"),
]


@dataclass
class Symbol:
    name: str
    signature: str
    line: int
    depth: int = 0


@dataclass
class FileEntry:
    path: str  # relativa al root, con "/"
    size: int
    symbols: list[Symbol] = field(default_factory=list)


def list_files(root: Path) -> list[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in IGNORED_DIRS and not d.startswith(".") and not d.endswith(".egg-info")
        )
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if name in IGNORED_FILES or path.suffix not in TEXT_EXT:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            files.append(path)
    return files


def python_symbols(source: str) -> list[Symbol]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    symbols: list[Symbol] = []

    def visit(nodes, depth: int) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                sig = f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"
                symbols.append(Symbol(node.name, sig, node.lineno, depth))
            elif isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                sig = f"class {node.name}({bases})" if bases else f"class {node.name}"
                symbols.append(Symbol(node.name, sig, node.lineno, depth))
                visit(node.body, depth + 1)

    visit(tree.body, 0)
    return symbols


def js_symbols(source: str) -> list[Symbol]:
    symbols = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for pattern in _JS_PATTERNS:
            match = pattern.match(line)
            if match:
                sig = line.strip().rstrip("{").strip()
                depth = 1 if line[:1] in (" ", "\t") else 0
                symbols.append(Symbol(match.group("name"), sig[:120], lineno, depth))
                break
    return symbols


def build_repo_map(root: str | Path) -> list[FileEntry]:
    root = Path(root)
    entries = []
    for path in list_files(root):
        rel = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix in PY_EXT:
            symbols = python_symbols(source)
        elif path.suffix in JS_EXT:
            symbols = js_symbols(source)
        else:
            symbols = []
        entries.append(FileEntry(rel, len(source), symbols))
    return entries


def render_repo_map(entries: list[FileEntry], max_tokens: int = 1200) -> str:
    """Rinde las entradas en orden. Primero se reserva espacio para listar todas las rutas;
    lo que sobra se gasta en firmas, empezando por las entradas más relevantes."""
    path_costs = [estimate_tokens(e.path) for e in entries]
    spare = max_tokens - sum(path_costs)
    lines: list[str] = []
    used = 0
    for entry, path_cost in zip(entries, path_costs):
        signatures = ["  " * (s.depth + 1) + s.signature for s in entry.symbols]
        extra = estimate_tokens("\n".join(signatures)) if signatures else 0
        if spare < 0 and used + path_cost > max_tokens:
            break
        lines.append(entry.path)
        used += path_cost
        if signatures and extra <= spare:
            lines.extend(signatures)
            spare -= extra
            used += extra
    return "\n".join(lines)
