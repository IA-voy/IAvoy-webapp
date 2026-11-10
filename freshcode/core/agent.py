"""Orquestador: plan -> stale guard -> edición -> tests -> reintento.

Configs (para el benchmark de P4):
  naive  todos los archivos completos, reescritura de archivos enteros, log de tests sin recortar
  lean   repo map + planner + contexto selectivo + SEARCH/REPLACE + errores recortados
  full   lean + Stale Guard (hechos frescos verificados con Tavily)

Ojo: las ediciones se aplican sobre `repo_path`. El benchmark debe correr sobre una copia.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from freshcode import stale_guard
from freshcode.contracts import Config, LLMClient, Response, Role, RunResult
from freshcode.core import prompts
from freshcode.core.edits import EditFormatError, EditResult, apply_edits, parse_search_replace, parse_whole_files
from freshcode.core.repo_map import build_repo_map, render_repo_map
from freshcode.core.retrieval import load_context, rank_entries
from freshcode.core.verify import detect_test_command, run_tests, trim_output

EventHandler = Callable[[str, str], None]  # (tipo, mensaje)


@dataclass
class AgentOptions:
    config: Config = "full"
    test_cmd: str | None = None
    max_retries: int = 2
    map_tokens: int = 1200
    context_tokens: int = 6000
    error_tokens: int = 400
    test_timeout: int = 180


class MeteredLLM:
    """Envuelve al cliente y suma los tokens de cada llamada a la fase actual."""

    def __init__(self, inner: LLMClient):
        self.inner = inner
        self.phase = "setup"
        self.by_phase: dict[str, int] = {}

    def call(self, role: Role, messages: list[dict], **kw) -> Response:
        response = self.inner.call(role, messages, **kw)
        self.by_phase[self.phase] = self.by_phase.get(self.phase, 0) + response.usage.total
        return response

    @property
    def total(self) -> int:
        return sum(self.by_phase.values())


def _parse_plan(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _apply_reply(root: Path, text: str, naive: bool) -> EditResult:
    try:
        edits = parse_whole_files(text) if naive else parse_search_replace(text)
    except EditFormatError as e:
        result = EditResult()
        result.failed.append((_FormatProblem(str(e)), str(e)))
        return result
    if not edits:
        result = EditResult()
        problem = "no se encontraron bloques de edición en la respuesta"
        result.failed.append((_FormatProblem(problem), problem))
        return result
    return apply_edits(root, edits)


class _FormatProblem:
    """Marcador para errores de formato que no corresponden a un archivo concreto."""

    def __init__(self, message: str):
        self.path, self.search, self.replace = "(respuesta)", message, ""


def run_task(
    task: str,
    repo_path: str | Path,
    llm: LLMClient,
    options: AgentOptions | None = None,
    on_event: EventHandler | None = None,
) -> RunResult:
    opts = options or AgentOptions()
    root = Path(repo_path).resolve()
    naive = opts.config == "naive"
    meter = MeteredLLM(llm)
    log: list[str] = []

    def emit(kind: str, message: str) -> None:
        log.append(f"[{kind}] {message}")
        if on_event:
            on_event(kind, message)

    entries = build_repo_map(root)
    plan_text, facts = "", []

    if naive:
        files = [e.path for e in entries]
        context = load_context(root, files, task, max_tokens=10**9, per_file_tokens=10**9)
        system = prompts.NAIVE_SYSTEM
        emit("context", f"naive: {len(files)} archivos completos en contexto")
    else:
        ranked = rank_entries(entries, task)
        repo_map = render_repo_map(ranked, opts.map_tokens)
        emit("map", f"repo map: {len(entries)} archivos")

        meter.phase = "planner"
        reply = meter.call("planner", [
            {"role": "system", "content": prompts.PLANNER_SYSTEM},
            {"role": "user", "content": f"TASK:\n{task}\n\nREPO MAP:\n{repo_map}"},
        ])
        plan = _parse_plan(reply.text)
        known = {e.path for e in entries}
        files = [f for f in plan.get("files", []) if f in known][:6]
        if not files:
            files = [e.path for e in ranked[:3]]
            emit("plan", "el planner no devolvió archivos válidos; uso los 3 más relevantes")
        plan_text = str(plan.get("plan", ""))
        libraries = plan.get("libraries", [])
        if libraries:
            plan_text += "\nLibraries: " + json.dumps(libraries, ensure_ascii=False)
        emit("plan", f"archivos: {', '.join(files)}")

        if opts.config == "full":
            meter.phase = "stale_guard"
            facts = stale_guard.check_claims(plan_text, root, llm=meter)
            emit("stale_guard", f"{len(facts)} hechos verificados")

        context = load_context(root, files, task, opts.context_tokens)
        system = prompts.EDITOR_SYSTEM

    facts_text = "\n".join(f.as_prompt_line() for f in facts)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompts.editor_user_message(task, plan_text, context, facts_text)},
    ]

    test_cmd = opts.test_cmd or detect_test_command(root)
    changed: list[str] = []
    success, tests_ran, retries = False, False, 0

    for attempt in range(opts.max_retries + 1):
        meter.phase = "editor" if attempt == 0 else "retry"
        reply = meter.call("editor", messages)
        result = _apply_reply(root, reply.text, naive)
        changed.extend(p for p in result.applied if p not in changed)
        emit("edit", f"intento {attempt + 1}: {len(result.applied)} archivos editados, {len(result.failed)} bloques fallidos")

        if test_cmd:
            run = run_tests(root, test_cmd, opts.test_timeout)
            tests_ran = True
            emit("test", "pasan" if run.passed else f"fallan (exit {run.exit_code})")
            if run.passed and not result.failed:
                success = True
                break
            error = run.output if naive else ("" if run.passed else trim_output(run.output, opts.error_tokens))
        else:
            if not result.failed:
                success = True
                emit("test", "sin comando de tests: se da por resuelta al aplicar las ediciones")
                break
            error = ""

        if attempt == opts.max_retries:
            break
        retries += 1

        if naive:
            # El baseline arrastra toda la conversación, como haría un agente ingenuo.
            messages += [
                {"role": "assistant", "content": reply.text},
                {"role": "user", "content": f"Tests failed:\n{error}\n{result.feedback()}\nFix it."},
            ]
        else:
            # Lean/full: conversación nueva con solo lo necesario, sin arrastrar el historial.
            files_now = files + [p for p in changed if p not in files]
            context = load_context(root, files_now, task, opts.context_tokens)
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompts.retry_user_message(task, context, error, result.feedback())},
            ]

    return RunResult(
        success=success,
        total_tokens=meter.total,
        tokens_by_phase=dict(meter.by_phase),
        retries=retries,
        facts=facts,
        changed_files=changed,
        tests_ran=tests_ran,
        log=log,
    )
