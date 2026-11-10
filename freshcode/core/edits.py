"""Parseo y aplicación de ediciones.

Formato principal (configs lean/full), bloques SEARCH/REPLACE:

    ruta/al/archivo.py
    <<<<<<< SEARCH
    líneas exactas actuales
    =======
    líneas nuevas
    >>>>>>> REPLACE

SEARCH vacío crea el archivo (o agrega al final si ya existe).

Formato naive (baseline), archivo completo:

    FILE: ruta/al/archivo.py
    ```
    contenido completo
    ```
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SEARCH = re.compile(r"^<{5,9} ?SEARCH\s*$")
_DIVIDER = re.compile(r"^={5,9}\s*$")
_REPLACE = re.compile(r"^>{5,9} ?REPLACE\s*$")
_WHOLE_FILE = re.compile(r"^FILE:\s*(?P<path>\S+)\s*\n```[^\n]*\n(?P<body>.*?)^```\s*$", re.M | re.S)


class EditFormatError(ValueError):
    pass


@dataclass
class Edit:
    path: str
    search: str
    replace: str


@dataclass
class EditResult:
    applied: list[str] = field(default_factory=list)
    failed: list[tuple[Edit, str]] = field(default_factory=list)

    def feedback(self) -> str:
        """Mensaje corto para el modelo explicando qué bloques no se aplicaron."""
        parts = []
        for edit, reason in self.failed:
            snippet = edit.search if len(edit.search) < 400 else edit.search[:400] + "..."
            parts.append(f"{edit.path}: {reason}\nSEARCH era:\n{snippet}")
        return "\n\n".join(parts)


def _clean_path(line: str) -> str:
    path = line.strip().strip("`*#:").strip()
    for prefix in ("File:", "FILE:", "file:", "Path:", "path:"):
        if path.startswith(prefix):
            path = path[len(prefix):].strip()
    return path.strip("`").strip()


def parse_search_replace(text: str) -> list[Edit]:
    lines = text.splitlines(keepends=True)
    edits: list[Edit] = []
    i = 0
    while i < len(lines):
        if not _SEARCH.match(lines[i].rstrip("\n")):
            i += 1
            continue

        # La ruta es la línea no vacía anterior que no sea una cerca de código.
        path, j = "", i - 1
        while j >= 0:
            candidate = lines[j].strip()
            if candidate and not candidate.startswith("```"):
                path = _clean_path(candidate)
                break
            j -= 1
        if not path:
            raise EditFormatError(f"Bloque SEARCH sin ruta de archivo (línea {i + 1})")

        search, replace, k = [], [], i + 1
        while k < len(lines) and not _DIVIDER.match(lines[k].rstrip("\n")):
            search.append(lines[k])
            k += 1
        if k >= len(lines):
            raise EditFormatError(f"Falta '=======' en el bloque de {path}")
        k += 1
        while k < len(lines) and not _REPLACE.match(lines[k].rstrip("\n")):
            replace.append(lines[k])
            k += 1
        if k >= len(lines):
            raise EditFormatError(f"Falta '>>>>>>> REPLACE' en el bloque de {path}")

        edits.append(Edit(path, "".join(search), "".join(replace)))
        i = k + 1
    return edits


def parse_whole_files(text: str) -> list[Edit]:
    """Formato naive: cada archivo se reemplaza entero (search=None se modela como reescritura)."""
    return [Edit(m["path"], "\0WHOLE\0", m["body"]) for m in _WHOLE_FILE.finditer(text)]


def _resolve(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if root != path and root not in path.parents:
        raise EditFormatError(f"Ruta fuera del repo: {rel}")
    return path


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _fuzzy_replace(content: str, search: str, replace: str) -> str | None:
    """Coincidencia por líneas ignorando espacios al inicio y al final.

    Si hay exactamente una coincidencia, reemplaza re-indentando REPLACE según la indentación real.
    """
    c_lines = content.splitlines(keepends=True)
    s_lines = search.splitlines()
    while s_lines and not s_lines[0].strip():
        s_lines.pop(0)
    while s_lines and not s_lines[-1].strip():
        s_lines.pop()
    if not s_lines:
        return None

    target = [line.strip() for line in s_lines]
    n = len(target)
    matches = [
        i for i in range(len(c_lines) - n + 1)
        if all(c_lines[i + j].strip() == target[j] for j in range(n))
    ]
    if len(matches) != 1:
        return None

    start = matches[0]
    k = next(j for j, line in enumerate(s_lines) if line.strip())
    real_indent, model_indent = _indent(c_lines[start + k]), _indent(s_lines[k])

    new_lines = []
    for line in replace.splitlines():
        if line.strip() and line.startswith(model_indent):
            line = real_indent + line[len(model_indent):]
        new_lines.append(line + "\n")
    if new_lines and not c_lines[start + n - 1].endswith("\n"):
        new_lines[-1] = new_lines[-1].rstrip("\n")

    return "".join(c_lines[:start] + new_lines + c_lines[start + n:])


def apply_edit(root: Path, edit: Edit) -> None:
    path = _resolve(root, edit.path)

    if edit.search == "\0WHOLE\0":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(edit.replace, encoding="utf-8", newline="")
        return

    if not edit.search.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + edit.replace, encoding="utf-8", newline="")
        return

    if not path.is_file():
        raise EditFormatError("el archivo no existe (usa SEARCH vacío para crearlo)")

    content = path.read_text(encoding="utf-8")
    count = content.count(edit.search)
    if count == 1:
        new = content.replace(edit.search, edit.replace, 1)
    elif count > 1:
        raise EditFormatError(f"SEARCH aparece {count} veces; agrega líneas de contexto para que sea único")
    else:
        new = _fuzzy_replace(content, edit.search, edit.replace)
        if new is None:
            raise EditFormatError("SEARCH no coincide con el archivo; copia las líneas exactas")
    path.write_text(new, encoding="utf-8", newline="")


def apply_edits(root: str | Path, edits: list[Edit]) -> EditResult:
    root = Path(root).resolve()
    result = EditResult()
    for edit in edits:
        try:
            apply_edit(root, edit)
        except (EditFormatError, OSError) as e:
            result.failed.append((edit, str(e)))
        else:
            if edit.path not in result.applied:
                result.applied.append(edit.path)
    return result
