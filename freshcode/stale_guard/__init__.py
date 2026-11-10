"""Stale Guard: detecta afirmaciones que pueden estar desactualizadas y las verifica con Tavily.

Dueño: P3. Por ahora es un stub que no verifica nada, para que el agente funcione de punta a punta.
"""

from __future__ import annotations

from pathlib import Path

from freshcode.contracts import FreshFact, LLMClient


def check_claims(plan: str, repo_path: str | Path, llm: LLMClient | None = None) -> list[FreshFact]:
    """Recibe el plan del agente y devuelve hechos frescos para inyectar al editor.

    TODO(P3): extraer afirmaciones, cruzar versiones del repo, verificar con Tavily,
    calcular freshness score y cachear.
    """
    return []


def check_text(text: str, llm: LLMClient | None = None) -> list[FreshFact]:
    """Modo standalone (`freshcode check respuesta.md`): verifica cualquier respuesta de un LLM.

    TODO(P3)
    """
    raise NotImplementedError("Stale Guard standalone todavía no implementado (P3)")
