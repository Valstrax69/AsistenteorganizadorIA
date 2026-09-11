# RAG DuocUC · Groq

Chatbot RAG para el ramo **Ingeniería de Soluciones con Inteligencia Artificial** (DuocUC).
Responde preguntas de estudiantes de Duoc UC usando material institucional en Markdown (carpeta `data/`) y una fuente externa de búsqueda web. Incluye además un panel de herramientas académicas.

Variante propia: LLM servido por **Groq** y **embeddings locales** (sin API de embeddings).

## Stack

| Componente | Tecnología |
|-----------|-----------|
| LLM | Groq — configurable vía `GROQ_MODEL` (actual: `groq/compound-mini`) |
| Embeddings | `intfloat/multilingual-e5-small` (local, 384 dims) |
| Vector DB | MongoDB Atlas (Vector Search) |
| UI | Streamlit |
| Evaluación | RAGAS (juez Groq + embeddings locales) con fallback léxico |
| CI/CD | GitHub Actions |
| Contenedor | Docker |

## Estructura

```
rag/            config.py · embeddings.py · vectorstore.py · ingest.py
                retriever.py · generator.py · costs.py · prompts.py
app/            streamlit_app.py
scripts/        create_index.py
evaluation/     dataset.json · run_eval.py
docs/           architecture.md
.github/workflows/ci.yml · Dockerfile · requirements*.txt · .env.example
```

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
