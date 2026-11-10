"""Acceso a LLMs. Todas las llamadas pasan por Bifrost (dueño: P2)."""

from freshcode.llm.client import BifrostClient, get_client
from freshcode.llm.fake import ScriptedLLM

__all__ = ["BifrostClient", "ScriptedLLM", "get_client"]
