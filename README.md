# FreshCode

> Un coding agent que resuelve tareas reales con el mínimo de tokens, y que nunca escribe código basado en información vieja.

Proyecto para los tracks **Bifrost #01** (coding agent con menos tokens) y **Tavily #01** (stale-answer detector).
La idea completa está en [docs/FreshCode-idea.md](docs/FreshCode-idea.md).

## Cómo correrlo

Requisitos: Python 3.11+, Docker.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env            # completar modelos y TAVILY_API_KEY
docker compose up -d            # Bifrost en http://localhost:8080 (cargar ahí las claves de los proveedores)
```

```bash
freshcode run "Implement slugify in textutils.py" --repo benchmark/tasks/example-slugify/repo
freshcode map --repo . --task "trim test output"     # ver lo que recibe el planner
freshcode check respuesta.md                          # Stale Guard standalone (P3)
pytest                                                # tests del proyecto
```

> `freshcode run` edita el repo indicado. Para probar, usar una copia.

## Configs del agente

| Config | Qué hace |
|---|---|
| `naive` | Baseline: todos los archivos completos, reescribe archivos enteros, arrastra el historial |
| `lean` | Repo map + planner + contexto selectivo + SEARCH/REPLACE + errores de tests recortados |
| `full` | `lean` + Stale Guard (hechos frescos verificados con Tavily) |

## Estructura

```
freshcode/
├── contracts.py        contratos compartidos (Response, FreshFact, RunResult...)  ← avisar antes de cambiar
├── cli.py              punto de entrada `freshcode`
├── core/               P1 · agente
│   ├── agent.py          orquestador: plan → stale guard → edición → tests → reintento
│   ├── repo_map.py       mapa de firmas (ast para Python, regex para JS/TS)
│   ├── retrieval.py      ranking de archivos y contexto por ventanas
│   ├── edits.py          parseo y aplicación de bloques SEARCH/REPLACE
│   ├── verify.py         detecta y corre tests, recorta la salida
│   └── prompts.py        prompts de sistema
├── llm/                P2 · cliente Bifrost (+ ScriptedLLM para tests sin gastar tokens)
└── stale_guard/        P3 · detector de afirmaciones obsoletas + Tavily
benchmark/              P4 · tareas y runner (configs A/B/C)
tests/                  tests del proyecto
docs/                   idea y documentación
```

## Equipo y flujo de trabajo

| Persona | Área | Carpeta |
|---|---|---|
| P1 | Núcleo del agente | `freshcode/core/` |
| P2 | Bifrost, routing, métricas, dashboard | `freshcode/llm/`, `docker-compose.yml` |
| P3 | Stale Guard + Tavily | `freshcode/stale_guard/` |
| P4 | Benchmark, demo, pitch | `benchmark/`, `docs/` |

- Una rama corta por persona (`p1-core`, `p2-bifrost`, `p3-stale-guard`, `p4-benchmark`), merge frecuente a `main`.
- Cambios a `freshcode/contracts.py` se avisan al equipo antes de hacer merge.
- `.env` nunca se sube. Las claves se comparten por un canal privado.
- Antes de hacer merge: `pytest` en verde.
