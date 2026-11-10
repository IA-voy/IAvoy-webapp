"""Prompts de sistema. Cortos y estables a propósito: se repiten en cada llamada y se cachean mejor.

Están en inglés porque gastan menos tokens que en español.
"""

PLANNER_SYSTEM = """You plan code changes for a coding agent.
Input: a task and a compact repo map (paths + signatures).
Reply with ONLY a JSON object:
{"files": ["existing paths to read/edit, max 6"],
 "new_files": ["paths to create"],
 "libraries": [{"name": "pkg", "usage": "exact API/feature you will use"}],
 "plan": "max 3 short steps"}"""

EDITOR_SYSTEM = """You edit code. Reply ONLY with SEARCH/REPLACE blocks, no prose:

path/to/file.ext
<<<<<<< SEARCH
exact current lines (copy verbatim, include enough lines to be unique)
=======
new lines
>>>>>>> REPLACE

Rules: keep blocks small; one block per change; empty SEARCH creates a new file.
Files shown may be partial ("... omitted ..."): only SEARCH lines you can see.
If FRESH FACTS are given, they override your memory of library APIs."""

NAIVE_SYSTEM = """You edit code. For every file you change, reply with its FULL new content:

FILE: path/to/file.ext
```
full file content
```"""


def editor_user_message(task: str, plan: str, context: str, facts: str = "") -> str:
    parts = [f"TASK:\n{task}"]
    if plan:
        parts.append(f"PLAN:\n{plan}")
    if facts:
        parts.append(f"FRESH FACTS (verified live, trust these):\n{facts}")
    parts.append(f"FILES:\n{context}")
    return "\n\n".join(parts)


def retry_user_message(task: str, context: str, error: str, edit_feedback: str = "") -> str:
    parts = [f"TASK:\n{task}", "Your previous change did not pass."]
    if edit_feedback:
        parts.append(f"BLOCKS THAT FAILED TO APPLY:\n{edit_feedback}")
    if error:
        parts.append(f"TEST ERRORS:\n{error}")
    parts.append(f"CURRENT FILES:\n{context}")
    return "\n\n".join(parts)
