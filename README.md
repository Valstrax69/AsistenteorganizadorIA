# Asistente Organizador Académico · Agente con LangChain + Groq

Agente académico para el ramo **Ingeniería de Soluciones con Inteligencia Artificial** (DuocUC, ISY0101).

No es solo un chatbot: el modelo decide por sí mismo qué herramientas llamar. Puede **consultar** el material institucional y la agenda del estudiante, **escribir** en esa agenda (crear tareas, moverlas de estado, registrar asistencia) y **razonar** sobre ella (priorizar la semana).

Variante propia: LLM servido por **Groq** y **embeddings locales** (sin API de embeddings).

## Stack

| Componente | Tecnología |
|-----------|-----------|
| Framework de agente | LangChain (`langchain-groq`) — `bind_tools` + ciclo ReAct explícito |
| LLM | Groq — configurable vía `GROQ_MODEL` (actual: `openai/gpt-oss-120b`) |
| Embeddings | `intfloat/multilingual-e5-small` (local, 384 dims) |
| Vector DB | MongoDB Atlas (Vector Search) |
| Memoria | Corto plazo: historial de sesión. Largo plazo: colección `conversaciones` en Mongo |
| UI | Streamlit |
| Evaluación | Casos funcionales (`evaluation/run_agente.py`) + RAGAS para el retrieval |
| CI/CD | GitHub Actions |
| Contenedor | Docker |

> **Nota sobre el modelo:** los sistemas `compound` de Groq **no aceptan herramientas propias**, por lo que no sirven para este agente. `GROQ_MODEL` debe apuntar a un modelo con function calling.

## Estructura

```
rag/            config.py · embeddings.py · vectorstore.py · ingest.py
                retriever.py · herramientas.py · agente.py · prompts.py
                generator.py · costs.py        (chatbot previo, lo usa run_eval)
app/            streamlit_app.py · tools.html
scripts/        create_index.py
evaluation/     casos_agente.json · run_agente.py   (evidencia del agente)
                dataset.json · run_eval.py          (calidad del RAG)
docs/           architecture.md
.github/workflows/ci.yml · Dockerfile · requirements*.txt · .env.example
```

## Herramientas del agente

| Herramienta | Tipo | Qué hace |
|---|---|---|
| `buscar_material` | consulta | Búsqueda semántica en el material interno (Atlas Vector Search) |
| `buscar_en_web` | consulta | Fuente externa cuando el material interno no alcanza |
| `listar_tareas` | consulta | Tareas y evaluaciones registradas |
| `estado_asistencia` | consulta | % de asistencia por ramo y alerta bajo el mínimo |
| `crear_tarea` | escritura | Registra una tarea con ramo, fecha y ponderación |
| `mover_tarea` | escritura | Cambia el estado (por_hacer / en_progreso / hecho) |
| `registrar_asistencia` | escritura | Registra asistencia o inasistencia del día |
| `planificar_semana` | razonamiento | Ordena pendientes por ponderación y días restantes |

El criterio de prioridad es determinista (`ponderación / días restantes`), no lo decide el LLM: una prueba de 35% en 2 días gana sobre una de 20% en 20 días.

## Evidencia de pruebas

```bash
python -m evaluation.run_agente
```

Corre los 10 casos de `evaluation/casos_agente.json` (escritura, consulta, razonamiento, encadenado, fuera de dominio, dato faltante y continuidad conversacional) y deja el snapshot con PASS/FAIL en `evaluation/resultados_agente.json`.

Toda la configuración vive en `rag/config.py` (leída desde variables de entorno);
no se hardcodean modelos ni credenciales en el resto del código.

## Herramientas académicas

Además del chat RAG, la interfaz incluye un panel de herramientas (componente HTML/JS con estado en el navegador):

- Clases del día + próximas pruebas y calendario del mes.
- Calculadora de calificaciones y ponderaciones (escala 1–7).
- Control de asistencia y margen de faltas por ramo.
- Temporizador Pomodoro con modo enfoque.
- Adjuntar PDF → resumen y puntos clave.
- Notas adhesivas arrastrables.
- Gestor de trabajos grupales estilo tablero Kanban.

## Puesta en marcha

1. **Variables de entorno**

   ```bash
   cp .env.example .env   # y completa MONGODB_URI y GROQ_API_KEY
   ```

2. **Dependencias**

   ```bash
   pip install -r requirements.txt
   ```

3. **Índice de Atlas Vector Search** (una vez, tras configurar Mongo)

   ```bash
   python -m scripts.create_index
   ```

   Crea el índice `vector_index` sobre `chunks` con las dimensiones de
   `EMBEDDING_DIM` (384). Funciona en el tier gratuito **M0** de Atlas.

4. **Ingestar material**

   Desde la barra lateral de la app, o por CLI:

   ```bash
   python -m rag.ingest                       # desde GITHUB_REPO
   INGEST_LOCAL_DIR=./data python -m rag.ingest    # desde una carpeta local (.md)
   ```

5. **Correr la app**

   ```bash
   streamlit run app/streamlit_app.py
   # o con Docker:
   docker build -t rag-duoc-groq . && docker run --env-file .env -p 8501:8501 rag-duoc-groq
   ```

6. **Evaluar** (opcional, deps aparte)

   ```bash
   pip install -r requirements-eval.txt
   python -m evaluation.run_eval
   ```

## Requisitos del ramo cubiertos

CI/CD (`ci.yml`), historial de sesión (`conversaciones`), feedback 👍/👎 (`feedback`),
trazabilidad de tokens por interacción (guardada en Mongo; el costo NO se muestra en la UI porque el uso es gratuito), diagrama de
arquitectura (`docs/architecture.md`), secretos vía GitHub Secrets, ambientes
`dev`/`qa`/`main` mapeados a bases de datos separadas, **fuentes internas + externa
(búsqueda web)** y **contexto conversacional** (historial enviado al LLM).

## Notas de configuración

- El modelo se define en `GROQ_MODEL`. Se usa un modelo **no-razonador** (`groq/compound-mini`): los modelos de razonamiento (familia qwen3) consumen el presupuesto de tokens del nivel gratuito y truncan la respuesta.
- Para la búsqueda vectorial, la IP debe estar habilitada en el *Network Access* de MongoDB Atlas.
- Las tarifas de referencia en `rag/costs.py` deben verificarse contra el pricing vigente de Groq.


## Docker (para la entrega)

Con un archivo `.env` válido en la raíz (ver `.env.example`), levantar todo es un solo comando:

```bash
docker compose up --build
# abre http://localhost:8501
```

Equivalente sin compose:

```bash
docker build -t rag-duoc-groq .
docker run --env-file .env -p 8501:8501 rag-duoc-groq
```

Detalles pensados para que corra en otra máquina sin sorpresas:

- El **modelo de embeddings se pre-descarga en el build**, así el arranque no depende de bajar ~470 MB. Si cambias `EMBEDDING_MODEL`, reconstruye con `--build-arg EMBEDDING_MODEL=<modelo>`.
- `.dockerignore` deja fuera `.env`, `.venv`, cachés y `.git` (no se filtran secretos ni se infla la imagen).
- Corre como usuario **no root** y expone healthcheck en `/_stcore/health`.
- **Inicialización automática (opcional):** `INIT_ON_START=true docker compose up --build` crea el índice e ingesta al arrancar (idempotente: no re-ingesta si ya hay chunks). Requiere Atlas alcanzable, red y `GITHUB_REPO` con .md.

> **Credenciales al entregar:** `.env` está en `.gitignore`, así que **no viaja en el repo**. Para que el/la docente lo corra tienes dos caminos, y la decisión es tuya: (a) incluir tu `.env` en el ZIP de entrega — corre de inmediato pero expones tus llaves de Atlas y Groq; (b) entregar solo `.env.example` y que complete sus propias credenciales. No decido esto por ti.
