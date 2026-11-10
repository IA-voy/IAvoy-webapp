# benchmark (P4)

Cada tarea vive en `tasks/<id>/`:

```
tasks/<id>/
├── task.json   {"id", "prompt", "test_cmd", "tags"}
└── repo/       proyecto mínimo con tests que fallan hasta resolver la tarea
```

`tasks/example-slugify` es una tarea de **control** (no depende de APIs que cambiaron) y sirve de plantilla.

El runner debe, para cada tarea y cada config (`naive`, `lean`, `full`):
1. Copiar `repo/` a un directorio temporal (el agente edita en el lugar).
2. Llamar `freshcode.core.agent.run_task(prompt, copia, llm, AgentOptions(config=..., test_cmd=...))`.
3. Guardar el `RunResult` en `results/<fecha>/<id>-<config>.json`.

Métricas: tasa de éxito, tokens totales, tokens por tarea resuelta, reintentos, hechos verificados.

Pendiente:
- [ ] `run.py` (runner) y tabla resumen.
- [ ] 8–10 tareas sobre APIs que cambiaron (verificar cada una contra la doc oficial).
- [ ] Al menos una tarea de control más.
