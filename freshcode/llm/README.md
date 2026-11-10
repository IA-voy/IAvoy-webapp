# llm (P2)

Todas las llamadas del agente pasan por `LLMClient.call(role, messages) -> Response` (ver `freshcode/contracts.py`).
Roles: `planner` (barato), `editor` (fuerte), `judge` (barato, lo usa el Stale Guard).

Ya existe:
- `client.py`: `BifrostClient` mínimo contra `POST {BIFROST_URL}/v1/chat/completions`, modelo por rol desde `.env`.
- `fake.py`: `ScriptedLLM` para tests y desarrollo sin gastar tokens.

Pendiente:
- [ ] Confirmar imagen, puerto y formato de modelos en `docker-compose.yml` contra la doc de Bifrost.
- [ ] Routing/fallbacks y caché semántica configurados en Bifrost; marcar `Response.cached` cuando aplique.
- [ ] Reintentos ante errores transitorios.
- [ ] Exportar métricas por llamada (rol, modelo, tokens, latencia, cacheado) para el benchmark y el dashboard.
- [ ] (Extra) Dashboard con los resultados de `benchmark/results/`.

El agente ya suma tokens por fase (`planner`, `stale_guard`, `editor`, `retry`) en `RunResult.tokens_by_phase`
usando `Response.usage`, así que es importante que `usage` venga siempre lleno.
