# FreshCode

> **Un coding agent que resuelve tareas reales con el mínimo de tokens, y que nunca escribe código basado en información vieja.**

**Tracks:**
- **Bifrost #01**: *Build a coding agent that gets the job done on the fewest tokens.*
- **Tavily #01**: *Stale-answer detector.*

---

## 1. El problema

### 1.1 Los coding agents desperdician tokens
La mayoría de los coding agents meten archivos completos en el contexto, reescriben archivos enteros para cambiar 3 líneas y pegan logs de tests de cientos de líneas. El resultado es que una tarea simple cuesta decenas de miles de tokens.

### 1.2 Los LLMs escriben código con APIs que ya cambiaron
El conocimiento del modelo se congela en su fecha de corte, pero las librerías siguen avanzando. Algunos ejemplos típicos:

| Librería | Lo que el modelo suele escribir | Lo que es correcto hoy |
|---|---|---|
| Next.js 15 | `params.id` síncrono | `params` es una Promise (`await params`) |
| Pydantic v2 | `.dict()`, `@validator` | `.model_dump()`, `@field_validator` |
| Tailwind v4 | `tailwind.config.js` + `@tailwind base` | `@import "tailwindcss"` + config en CSS |
| OpenAI SDK v1+ | `openai.ChatCompletion.create` | `client.chat.completions.create` |
| React 19 | `forwardRef` obligatorio | `ref` como prop normal |

> ⚠️ Verificar cada fila antes del pitch: precisamente de esto trata el proyecto.

### 1.3 La conexión entre los dos problemas (nuestra tesis)
Cuando el agente usa una API vieja, el código falla. Entonces el agente:
1. ejecuta los tests,
2. lee el error,
3. vuelve a intentarlo,
4. a veces repite el mismo error.

**Cada reintento quema tokens.** Por eso el conocimiento desactualizado es una de las mayores fuentes de desperdicio de tokens.

> ### *"El token más caro es el que gastas corrigiendo código basado en información vieja."*

FreshCode verifica **antes** de escribir, y solo lo que hace falta verificar. Así resolvemos los dos problemas con un solo sistema.

---

## 2. La solución

FreshCode es un **coding agent de CLI** con dos componentes:

1. **Motor de eficiencia de tokens** (track Bifrost): hace que cada llamada al LLM use el mínimo contexto posible, pasando por el gateway de Bifrost para el enrutamiento, la caché y las métricas.
2. **Stale Guard** (track Tavily): antes de generar código, detecta qué afirmaciones del plan pueden estar desactualizadas, las verifica en vivo con Tavily, les asigna un **freshness score** y le pasa al modelo solo los hechos frescos, comprimidos.

### Ejemplo de uso
```bash
freshcode "Agrega una ruta /api/users/[id] que devuelva el usuario por id"
```
```
📂 Repo map: 42 símbolos relevantes (1.1k tokens)
🧠 Plan (modelo rápido): editar app/api/users/[id]/route.ts
🔍 Stale Guard: 3 afirmaciones detectadas
   🟢 0.95  Prisma findUnique({ where: { id } })        prisma.io/docs
   🔴 0.10  params en route handlers es síncrono        nextjs.org/docs (v15: es Promise)
   🟡 0.60  NextResponse.json() acepta status en init   verificado ✔
✏️  Edición por diff (modelo fuerte): +14 −0 líneas
✅ Tests: 3/3 pasan
💰 Total: 4,812 tokens  |  Baseline naive: 31,940 tokens  (−85%)
```

---

## 3. Arquitectura

```
                      ┌──────────────────────────────┐
  tarea del usuario → │        Orquestador CLI       │
                      └──────────────┬───────────────┘
                                     │
          ┌──────────────────────────┼───────────────────────────┐
          ▼                          ▼                           ▼
 ┌─────────────────┐      ┌─────────────────────┐      ┌──────────────────┐
 │  Context Engine │      │     Stale Guard     │      │ Verify Loop      │
 │  - repo map     │      │  - claim extractor  │      │ - corre tests    │
 │  - retrieval    │      │  - version check    │      │ - recorta errores│
 │  - diff edits   │      │  - Tavily search/   │      │ - reintento      │
 └────────┬────────┘      │    extract          │      └────────┬─────────┘
          │               │  - freshness score  │               │
          │               │  - fact cache       │               │
          │               └──────────┬──────────┘               │
          └──────────────────────────┼──────────────────────────┘
                                     ▼
                      ┌──────────────────────────────┐
                      │       BIFROST GATEWAY        │
                      │  - routing (barato/fuerte)   │
                      │  - semantic cache            │
                      │  - métricas de tokens        │
                      └──────────────┬───────────────┘
                                     ▼
                         Proveedores LLM (varios)
```

### Flujo paso a paso
1. **Entrada:** el usuario da una tarea en lenguaje natural.
2. **Repo map:** se genera un mapa compacto del repo (firmas de funciones y clases, no el código completo).
3. **Planificación (modelo barato vía Bifrost):** decide qué archivos tocar y qué librerías o APIs va a usar.
4. **Stale Guard:**
   1. Extrae las *afirmaciones caducables* del plan ("vamos a usar `params.id` en un route handler de Next").
   2. Las cruza con las versiones reales del repo (`package.json`, `requirements.txt`, lockfiles).
   3. Calcula un **riesgo de obsolescencia** para cada una. Si el riesgo es bajo, la afirmación no se verifica (ahorro).
   4. Las de riesgo medio o alto se verifican con **Tavily Search** (limitado a dominios oficiales de documentación y changelogs) y **Tavily Extract**.
   5. Asigna un **freshness score** (0–1) y adjunta la fuente.
   6. Comprime el resultado en *hechos frescos* de pocas líneas y los guarda en caché.
5. **Edición (modelo fuerte vía Bifrost):** recibe solo los fragmentos relevantes y los hechos frescos, y devuelve **bloques search/replace**, no archivos completos.
6. **Verificación:** se corren los tests. Si fallan, se pasa al modelo solo el fragmento relevante del error y se reintenta, con un máximo de N intentos.
7. **Reporte:** tokens usados, afirmaciones verificadas y comparación con el baseline.

---

## 4. Componentes en detalle

### 4.1 Motor de eficiencia de tokens (Bifrost)

| Técnica | Qué hace | Ahorro esperado |
|---|---|---|
| **Repo map** | Usa tree-sitter para extraer solo firmas y estructura. El modelo pide el código completo de un símbolo solo si lo necesita. | Alto |
| **Retrieval selectivo** | Incluye solo los archivos o fragmentos relacionados con la tarea (grep, símbolos, imports). | Alto |
| **Ediciones por diff** | El modelo responde con bloques `SEARCH/REPLACE`, no con el archivo completo. | Alto en archivos grandes |
| **Cascada de modelos** | Un modelo barato localiza y planea; el fuerte solo edita. El enrutamiento se configura en Bifrost. | Medio (en costo) |
| **Caché semántica (Bifrost)** | Las consultas parecidas no vuelven a llamar al LLM. | Variable |
| **Recorte de errores** | De un log de tests solo se pasa el assertion fallido y el stack trace propio. | Medio |
| **Prompt de sistema mínimo** | Un prompt corto y estable, que además se cachea mejor. | Bajo pero constante |

**Por qué Bifrost es central y no decorativo:** todas las llamadas pasan por el gateway, de donde salen el **enrutamiento entre modelos**, la **caché** y la **telemetría de tokens** que alimenta el benchmark. Revisar en la documentación actual de Bifrost qué funciones están disponibles (caché semántica, routing/fallbacks, observabilidad, presupuestos) y usar las que existan de verdad.

### 4.2 Stale Guard (Tavily)

**a) Claim extractor.** Un prompt pequeño (modelo barato) convierte el plan en una lista estructurada:
```json
[
  {"claim": "params en route handlers es un objeto síncrono",
   "library": "next", "assumed_version": "13", "category": "api_signature"},
  {"claim": "usar @validator para validar campos",
   "library": "pydantic", "assumed_version": "1", "category": "deprecated_api"}
]
```

**b) Riesgo de obsolescencia** (heurística, sin LLM):
- La versión del repo es distinta de la que asume el modelo → riesgo **alto**.
- La librería tuvo un cambio mayor después de la fecha de corte del modelo → riesgo **alto**.
- Categorías volátiles (precios, nombres de modelos, flags de CLI, configuración) → riesgo **medio**.
- Stdlib y APIs estables (`Array.map`, `os.path`) → riesgo **bajo**, no se verifica.

**c) Verificación con Tavily:**
- **Search** con `include_domains` restringido a la documentación oficial y GitHub releases de la librería.
- **Extract** de la página más relevante para obtener el fragmento exacto.
- Un LLM barato compara la afirmación con el fragmento y responde `vigente | cambió | dudosa` más la corrección.

**d) Freshness score por afirmación (0–1):**
```
score = f(coincidencia con la fuente, autoridad del dominio, fecha de la fuente,
          coincidencia de versión)
```
- 🟢 ≥ 0.8: vigente
- 🟡 0.4–0.8: dudosa (se inyecta con advertencia)
- 🔴 < 0.4: cambió (se inyecta la corrección)

**e) Hechos frescos comprimidos.** En lugar de pegar la documentación entera, se inyecta algo como:
```
FRESH FACTS (verificado 2026-11-03):
- next@15: en route handlers `params` es Promise → `const { id } = await params` [nextjs.org/docs/...]
```
Unos 50 tokens en lugar de unos 5,000.

**f) Fact cache.** Los hechos se guardan por `(librería, versión, afirmación)` en un JSON o SQLite local, así que la siguiente tarea no vuelve a gastar en Tavily ni en el LLM.

**g) Modo standalone (extra para el track Tavily).** El Stale Guard también funciona sobre **cualquier respuesta de un LLM**, no solo dentro del agente:
```bash
freshcode check respuesta.md
```
Esto cumple al pie de la letra el enunciado de Tavily: *"takes any LLM answer, flags claims likely to have gone stale, re-verifies them against live sources with a freshness score per claim"*.

---

## 5. Benchmark (la prueba de que funciona)

### Diseño
- **8–10 tareas** pequeñas en repos de ejemplo, **elegidas a propósito sobre APIs que cambiaron recientemente**.
- Cada tarea tiene **tests automáticos** que definen "resuelta".
- Se corre cada tarea con 3 configuraciones:

| Config | Descripción |
|---|---|
| **A. Naive** | Archivos completos en contexto, reescritura total, sin Stale Guard |
| **B. FreshCode sin Stale Guard** | Todas las optimizaciones de tokens, sin Tavily |
| **C. FreshCode completo** | Optimizaciones y Stale Guard |

### Métricas
- ✅ **Tasa de éxito** (tests pasan)
- 🔢 **Tokens totales** (input + output, medidos en Bifrost)
- 🎯 **Tokens por tarea resuelta**: la métrica principal
- 🔁 **Número de reintentos**
- 🔍 **Afirmaciones verificadas / detectadas como obsoletas**

### Resultado que queremos mostrar
- **A → B:** las optimizaciones reducen muchísimo los tokens.
- **B → C:** el Stale Guard **sube la tasa de éxito** y **baja los reintentos**, de modo que los tokens por tarea resuelta bajan todavía más, aunque Tavily agregue algunas llamadas.

> Reportar los números **reales**, aunque no sean perfectos. Un resultado honesto con explicación convence más que uno inflado.

### Ideas de tareas
1. Next.js 15: route handler dinámico con `params`
2. Next.js 15: `cookies()` / `headers()` asíncronos
3. Pydantic v2: migrar un modelo con validadores
4. Tailwind v4: configurar un tema personalizado
5. SDK de un proveedor LLM: hacer una llamada con streaming
6. React 19: componente que recibe `ref`
7. Express 5 o FastAPI reciente: algún cambio de API
8. Una tarea de control **sin** API cambiante (para demostrar que el Stale Guard no gasta de más)

---

## 6. Stack sugerido

| Capa | Tecnología |
|---|---|
| Lenguaje del agente | Python (o TypeScript si el equipo lo domina más) |
| Gateway LLM | **Bifrost** (local con Docker o binario), endpoint compatible con OpenAI |
| Búsqueda en vivo | **Tavily API** (Search + Extract) |
| Parsing del repo | tree-sitter (`tree-sitter-languages` en Python) |
| CLI | Typer + Rich (Python) / Commander + Ink (TS) |
| Caché de hechos | SQLite o JSON |
| Dashboard (opcional) | Página web simple que lee los resultados del benchmark |

---

## 7. División del trabajo para 4 personas

### 👤 Persona 1: Núcleo del agente (Agent Core)
**Responsable de:** que el agente resuelva tareas de punta a punta.
- Orquestador: plan → edición → verificación → reintento.
- Repo map con tree-sitter y retrieval selectivo.
- Formato de edición `SEARCH/REPLACE` y aplicador de diffs (con manejo de errores cuando el bloque no coincide).
- Loop de verificación: correr tests y recortar la salida del error.
- Prompts de sistema mínimos.

**Entregable:** `freshcode "tarea"` funciona en un repo de ejemplo.
**Depende de:** P2 (cliente LLM) y P3 (función `check_claims()`); puede empezar con mocks.

### 👤 Persona 2: Bifrost, enrutamiento y métricas
**Responsable de:** que todas las llamadas pasen por Bifrost y de medir todo.
- Levantar Bifrost y configurar proveedores y claves.
- Cliente LLM único (`llm.call(role="planner" | "editor" | "judge", ...)`) que enruta al modelo adecuado.
- Activar y probar la caché semántica y el enrutamiento o fallbacks según lo que ofrezca Bifrost.
- Registrar tokens por llamada, por fase (plan / stale guard / edición / reintento) y por tarea.
- Reporte final de tokens en la CLI.
- **Extra:** dashboard con la tabla y gráficos del benchmark.

**Entregable:** cliente LLM listo para P1 y P3 el **primer día**, y métricas confiables.

### 👤 Persona 3: Stale Guard (Tavily)
**Responsable de:** detectar, verificar y puntuar lo que puede estar desactualizado.
- Claim extractor (prompt y esquema JSON).
- Lector de versiones del repo (`package.json`, `requirements.txt`, `pyproject.toml`, lockfiles).
- Heurística de riesgo para decidir qué verificar y qué no.
- Integración con Tavily: Search con `include_domains` y Extract.
- Juez que compara la afirmación con la fuente y produce el freshness score.
- Compresor de hechos frescos y fact cache.
- Modo standalone `freshcode check respuesta.md`.

**Entregable:** función `check_claims(plan, repo) -> [FreshFact]` y el comando `check`.

### 👤 Persona 4: Benchmark, demo y pitch
**Responsable de:** demostrar que funciona y contarlo bien.
- Crear de 8 a 10 repos de ejemplo pequeños, cada uno con su tarea y sus tests.
- **Verificar manualmente** la "verdad" de cada API cambiada (documentación oficial).
- Script que corre las configuraciones A, B y C y guarda resultados (JSON/CSV).
- Implementar la configuración **A (naive)** como baseline.
- Guion de la demo en vivo y un **video de respaldo** por si algo falla.
- Slides: problema → tesis → arquitectura → demo → números → por qué gana.
- README del repositorio.

**Entregable:** tabla de resultados, video y presentación.

---

## 8. Cronograma sugerido (ajustar a la duración real)

| Fase | % del tiempo | Objetivo |
|---|---|---|
| **Setup** | 10% | Repo, Bifrost corriendo, Tavily probado, cliente LLM compartido, contratos entre módulos |
| **MVP** | 40% | Agente resuelve 1 tarea de punta a punta, Stale Guard verifica 1 afirmación, primeras tareas del benchmark |
| **Integración** | 25% | Stale Guard dentro del agente, las 3 configs corriendo, métricas completas |
| **Benchmark** | 10% | Correr todo y obtener números reales |
| **Pulido y pitch** | 15% | Salida bonita de la CLI, dashboard, video, slides, ensayo |

### Contratos entre módulos (definir en la primera hora)
```python
# P2 → todos
llm.call(role: str, messages: list, **kw) -> Response   # Response incluye .usage

# P3 → P1
check_claims(plan: str, repo_path: str) -> list[FreshFact]
# FreshFact: claim, verdict, score, correction, source_url

# P1 → P4
run_task(task_path: str, config: Literal["naive", "lean", "full"]) -> RunResult
# RunResult: success, total_tokens, tokens_by_phase, retries, facts
```

---

## 9. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| El agente no resuelve bien las tareas | Tareas pequeñas y bien acotadas; tests claros |
| Tavily devuelve resultados ruidosos | Limitar con `include_domains` a la documentación oficial; usar Extract |
| El Stale Guard gasta más tokens de los que ahorra | Heurística de riesgo para verificar poco, fact cache y hechos comprimidos |
| La demo en vivo falla | Video grabado de respaldo y resultados del benchmark precalculados |
| Poco tiempo | Priorizar: agente + Stale Guard + benchmark. Dashboard y cascada de modelos son extras |

---

## 10. Pitch en 30 segundos

> Los coding agents tienen dos problemas: gastan demasiados tokens y escriben código con APIs que ya no existen. Descubrimos que están conectados: **el código obsoleto falla, y cada reintento quema tokens**.
>
> **FreshCode** es un coding agent que usa contexto mínimo, ediciones por diff y enrutamiento inteligente a través de **Bifrost**, y que antes de escribir código detecta lo que puede estar desactualizado y lo verifica en vivo con **Tavily**, con un freshness score por afirmación.
>
> En nuestro benchmark de APIs que cambiaron recientemente, FreshCode resuelve **X% más tareas** usando **Y% menos tokens por tarea resuelta**.

---

## 11. Por qué esta idea puede ganar

- **Una sola historia coherente** para los dos tracks, no dos proyectos pegados.
- **Bifrost es una pieza central**: enrutamiento, caché y métricas pasan por el gateway.
- **Cumple el enunciado de Tavily al pie de la letra**: detecta afirmaciones caducables, las re-verifica contra fuentes en vivo y les da un freshness score por afirmación, además del modo standalone.
- **Resultados medibles** con un benchmark propio y honesto.
- **Problema real** que cualquier developer que usa IA ha vivido.
