# stale_guard (P3)

Dos puntos de entrada, ya conectados al resto (hoy son stubs en `__init__.py`):

- `check_claims(plan, repo_path, llm) -> list[FreshFact]`: lo llama el agente en config `full`,
  después del planner y antes del editor. `plan` incluye la lista de librerías y APIs que el planner piensa usar.
- `check_text(text, llm) -> list[FreshFact]`: modo standalone, `freshcode check respuesta.md`.

Usar el `llm` que llega por parámetro (rol `judge`): así los tokens se cuentan en la fase `stale_guard`.
Cada `FreshFact` se inyecta al editor con `FreshFact.as_prompt_line()`, así que `correction` debe ser corta y accionable.

Pendiente:
- [ ] Claim extractor (rol `judge`, salida JSON).
- [ ] Lector de versiones: `package.json`, `requirements.txt`, `pyproject.toml`, lockfiles.
- [ ] Heurística de riesgo: no verificar lo estable (ahorra tokens y créditos).
- [ ] Tavily Search con `include_domains` a docs oficiales + Extract.
- [ ] Juez + freshness score (0–1) + `source_url`.
- [ ] Caché de hechos en `.freshcode/facts.json` (ya está en `.gitignore`).
- [ ] Tests con respuestas de Tavily guardadas (sin red).
