"""Cliente mínimo para el endpoint compatible con OpenAI de Bifrost.

Versión inicial para que P1 y P3 puedan trabajar. P2 es dueño de este archivo:
enrutamiento, caché, reintentos y métricas detalladas van aquí.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from freshcode.contracts import Response, Role, Usage

_ROLE_ENV = {
    "planner": "FRESHCODE_MODEL_PLANNER",
    "editor": "FRESHCODE_MODEL_EDITOR",
    "judge": "FRESHCODE_MODEL_JUDGE",
}


def load_dotenv(path: Path = Path(".env")) -> None:
    """Carga KEY=VALUE de .env sin pisar variables ya definidas."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class BifrostClient:
    def __init__(self, base_url: str | None = None, timeout: int = 120):
        self.base_url = (base_url or os.environ.get("BIFROST_URL", "http://localhost:8080")).rstrip("/")
        self.timeout = timeout

    def model_for(self, role: Role) -> str:
        model = os.environ.get(_ROLE_ENV[role])
        if not model:
            raise RuntimeError(f"Falta {_ROLE_ENV[role]} en el entorno (.env)")
        return model

    def call(self, role: Role, messages: list[dict], **kw) -> Response:
        payload = {"model": self.model_for(role), "messages": messages, **kw}
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Bifrost respondió {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"No se pudo conectar a Bifrost en {self.base_url}: {e.reason}") from e

        usage = data.get("usage") or {}
        return Response(
            text=data["choices"][0]["message"].get("content") or "",
            usage=Usage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            model=data.get("model", payload["model"]),
        )


def get_client() -> BifrostClient:
    load_dotenv()
    return BifrostClient()
