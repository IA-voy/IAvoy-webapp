"""Selecciona qué archivos (y qué partes) entran al contexto del modelo."""

from __future__ import annotations

import re
from pathlib import Path

from freshcode.core.repo_map import FileEntry
from freshcode.llm.fake import estimate_tokens

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "add", "make", "use", "should",
    "una", "uno", "los", "las", "del", "que", "con", "por", "para", "como", "agrega", "agregar",
    "crea", "crear", "hacer", "haz", "debe", "cuando", "sus", "una", "esta", "este",
}
WINDOW = 15  # líneas de contexto alrededor de cada coincidencia en archivos grandes


def keywords(text: str) -> set[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)  # camelCase -> camel Case
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", text.replace("_", " "))
    return {w.lower() for w in words if len(w) >= 3 and w.lower() not in _STOPWORDS}


def score_entry(entry: FileEntry, kws: set[str]) -> int:
    """Cada keyword de la tarea cuenta una sola vez por archivo: pesa más en la ruta que en símbolos."""
    in_path = keywords(entry.path) & kws
    in_symbols = set().union(*(keywords(s.name) for s in entry.symbols)) & kws - in_path
    return 3 * len(in_path) + 2 * len(in_symbols)


def rank_entries(entries: list[FileEntry], task: str) -> list[FileEntry]:
    kws = keywords(task)
    return sorted(entries, key=lambda e: (-score_entry(e, kws), e.path))


def _windowed(source: str, kws: set[str], max_tokens: int) -> str:
    """Deja solo las ventanas de líneas que mencionan keywords. El texto conservado es literal,
    así que los bloques SEARCH del modelo siguen coincidiendo con el archivo real."""
    lines = source.splitlines()
    hits = [i for i, line in enumerate(lines) if keywords(line) & kws]
    if not hits:
        hits = [0]
    keep: set[int] = set()
    for i in hits:
        keep.update(range(max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)))

    out, last = [], -1
    for i in sorted(keep):
        if i != last + 1:
            out.append(f"... (líneas {last + 2}-{i} omitidas) ...")
        out.append(lines[i])
        last = i
    if last < len(lines) - 1:
        out.append(f"... (líneas {last + 2}-{len(lines)} omitidas) ...")

    text = "\n".join(out)
    while estimate_tokens(text) > max_tokens and out:
        out = out[: len(out) * 3 // 4]
        text = "\n".join(out) + "\n... (recortado) ..."
    return text


def load_context(
    root: str | Path,
    paths: list[str],
    task: str,
    max_tokens: int = 6000,
    per_file_tokens: int = 2000,
) -> str:
    """Arma el bloque de contexto con el contenido de `paths`.

    Archivos chicos van completos; los grandes, por ventanas alrededor de las keywords de la tarea.
    """
    root = Path(root)
    kws = keywords(task)
    blocks, used = [], 0
    for rel in paths:
        path = root / rel
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        body = source if estimate_tokens(source) <= per_file_tokens else _windowed(source, kws, per_file_tokens)
        block = f"### {rel}\n```\n{body}\n```"
        cost = estimate_tokens(block)
        if used + cost > max_tokens:
            blocks.append(f"### {rel}\n(omitido por presupuesto de contexto)")
            continue
        blocks.append(block)
        used += cost
    return "\n\n".join(blocks)
