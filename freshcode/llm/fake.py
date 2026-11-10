"""LLM de mentira con respuestas guionadas, para tests y para desarrollar sin gastar tokens."""

from __future__ import annotations

from freshcode.contracts import Response, Role, Usage


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


class ScriptedLLM:
    def __init__(self, responses: dict[Role, list[str]]):
        self.responses = {role: list(texts) for role, texts in responses.items()}
        self.calls: list[tuple[Role, list[dict]]] = []

    def call(self, role: Role, messages: list[dict], **kw) -> Response:
        self.calls.append((role, messages))
        queue = self.responses.get(role)
        if not queue:
            raise AssertionError(f"ScriptedLLM: no quedan respuestas para el rol {role!r}")
        text = queue.pop(0)
        prompt = "".join(m["content"] for m in messages)
        return Response(text=text, usage=Usage(estimate_tokens(prompt), estimate_tokens(text)), model="scripted")
