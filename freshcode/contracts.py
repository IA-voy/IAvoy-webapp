"""Contratos compartidos entre módulos.

Cambiar algo aquí afecta a todo el equipo: avisar antes de modificarlo.
  - P2 implementa LLMClient            (freshcode/llm)
  - P3 implementa check_claims          (freshcode/stale_guard) -> list[FreshFact]
  - P1 implementa run_task              (freshcode/core/agent.py) -> RunResult
  - P4 consume RunResult en el benchmark
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Role = Literal["planner", "editor", "judge"]
Config = Literal["naive", "lean", "full"]
Verdict = Literal["fresh", "stale", "uncertain"]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class Response:
    text: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    cached: bool = False


class LLMClient(Protocol):
    def call(self, role: Role, messages: list[dict], **kw) -> Response: ...


@dataclass
class FreshFact:
    claim: str
    verdict: Verdict
    score: float  # 0 = seguro que cambió, 1 = seguro que sigue vigente
    correction: str = ""
    source_url: str = ""

    def as_prompt_line(self) -> str:
        text = self.correction or self.claim
        source = f" [{self.source_url}]" if self.source_url else ""
        return f"- ({self.verdict}, {self.score:.2f}) {text}{source}"


@dataclass
class RunResult:
    success: bool
    total_tokens: int
    tokens_by_phase: dict[str, int]
    retries: int
    facts: list[FreshFact] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    tests_ran: bool = False
    log: list[str] = field(default_factory=list)
