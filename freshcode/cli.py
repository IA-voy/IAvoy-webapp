"""CLI de FreshCode.

    freshcode run "tarea" --repo ruta [--config full|lean|naive] [--test-cmd "..."]
    freshcode map --repo ruta [--task "..."]
    freshcode check respuesta.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from freshcode import stale_guard
from freshcode.core.agent import AgentOptions, run_task
from freshcode.core.repo_map import build_repo_map, render_repo_map
from freshcode.core.retrieval import rank_entries
from freshcode.llm import get_client
from freshcode.llm.fake import estimate_tokens

_ICONS = {"map": "📂", "context": "📂", "plan": "🧠", "stale_guard": "🔍", "edit": "✏️ ", "test": "✅"}


def _print_event(kind: str, message: str) -> None:
    print(f"{_ICONS.get(kind, '•')} {message}")


def cmd_run(args: argparse.Namespace) -> int:
    options = AgentOptions(config=args.config, test_cmd=args.test_cmd, max_retries=args.max_retries)
    result = run_task(args.task, args.repo, get_client(), options, on_event=None if args.json else _print_event)
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        phases = ", ".join(f"{k} {v:,}" for k, v in result.tokens_by_phase.items())
        status = "resuelta" if result.success else "NO resuelta"
        print(f"\n{'🎉' if result.success else '❌'} Tarea {status} | reintentos: {result.retries}")
        print(f"💰 Total: {result.total_tokens:,} tokens ({phases})")
    return 0 if result.success else 1


def cmd_map(args: argparse.Namespace) -> int:
    entries = build_repo_map(args.repo)
    if args.task:
        entries = rank_entries(entries, args.task)
    text = render_repo_map(entries, args.max_tokens)
    print(text)
    print(f"\n~{estimate_tokens(text):,} tokens, {len(entries)} archivos", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    try:
        facts = stale_guard.check_text(text, llm=get_client())
    except NotImplementedError as e:
        print(e, file=sys.stderr)
        return 2
    for fact in facts:
        print(fact.as_prompt_line())
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="freshcode")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="resolver una tarea de código")
    run.add_argument("task")
    run.add_argument("--repo", default=".")
    run.add_argument("--config", choices=["naive", "lean", "full"], default="full")
    run.add_argument("--test-cmd")
    run.add_argument("--max-retries", type=int, default=2)
    run.add_argument("--json", action="store_true", help="imprime el RunResult en JSON")
    run.set_defaults(func=cmd_run)

    repo_map = sub.add_parser("map", help="ver el repo map que recibe el planner")
    repo_map.add_argument("--repo", default=".")
    repo_map.add_argument("--task")
    repo_map.add_argument("--max-tokens", type=int, default=1200)
    repo_map.set_defaults(func=cmd_map)

    check = sub.add_parser("check", help="verificar afirmaciones obsoletas en una respuesta de LLM")
    check.add_argument("file")
    check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
