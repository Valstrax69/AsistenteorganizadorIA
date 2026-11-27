# Asistente Organizador Académico · Agente con LangChain + Groq

Agente académico para el ramo **Ingeniería de Soluciones con Inteligencia Artificial** (DuocUC, ISY0101).

No es solo un chatbot: el modelo decide por sí mismo qué herramientas llamar. Puede **consultar** el material institucional y la agenda del estudiante, **escribir** en esa agenda (crear tareas, moverlas de estado, registrar asistencia) y **razonar** sobre ella (priorizar la semana).

Variante propia: LLM servido por **Groq** y **embeddings locales** (sin API de embeddings).

## Evaluación 3 · Observabilidad del agente

Abra **[el monitor con los resultados](docs/ep3/monitor.html)** desde el explorador de archivos. En GitHub, descargue el repositorio antes de abrir el HTML. Funciona sin conexión. El [informe editable en PDF](docs/ep3/Informe_EP3.pdf) incluye capturas y campos para el trabajo de autoría del equipo. La [defensa](docs/ep3/defensa.md) usa el propio monitor como apoyo visual. Los [bocetos](docs/ep3/diseno.md) muestran la arquitectura y la disposición de los controles.

### Reproducir la evaluación en VS Code

Abra esta carpeta en VS Code. Desde la raíz, en PowerShell con Python 3.12 instalado:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r evaluation/requirements-ep3.txt
.\.venv\Scripts\python.exe -m unittest -v evaluation.test_observabilidad
.\.venv\Scripts\python.exe -m evaluation.test_ciclo_mock
.\.venv\Scripts\python.exe -m evaluation.observabilidad --repeticiones 3 --salida .observabilidad/banco.json
.\.venv\Scripts\python.exe -m scripts.dashboard_ep3 --banco .observabilidad/banco.json --salida .observabilidad/monitor.html
Start-Process .observabilidad/monitor.html
```

En macOS/Linux use `python3.12 -m venv .venv` y `.venv/bin/python`. La demo local ejercita el método `AgenteAcademico.responder`, las herramientas decoradas de LangChain y sus operaciones sobre una base Mongo simulada en memoria. La preparación de datos y la escritura de la traza quedan fuera del intervalo de latencia. El tiempo sí incluye la construcción de los mensajes, las llamadas al modelo y las herramientas.

Para medir inferencia remota, configure su propia `GROQ_API_KEY` en el entorno, instale las dependencias del banco y ejecute `python -m evaluation.observabilidad --groq --salida .observabilidad/groq.json`. Con tres repeticiones genera 30 turnos nominales. Consume cuota del proveedor. Las herramientas operan sobre datos ficticios; se excluyen los tres fallos inyectados y se deshabilitan las llamadas web/RAG de esta batería. Genere el HTML con el mismo comando de exportación y el JSON nuevo.

Para verificar además el recorrido completo desde el chat hasta el monitor, instale `streamlit==1.39.0` en el mismo entorno del banco y ejecute `python -m unittest -v evaluation.test_interfaz_ep3`. La prueba usa un proveedor guionizado y un almacén temporal.

### Monitorizar el chat en uso

1. Configure el chat con la sección «Puesta en marcha» de este README. En la raíz del proyecto, ejecute `python -m streamlit run app/streamlit_app.py --server.address 127.0.0.1`.
2. En otra terminal con el mismo entorno y directorio ejecute `python -m streamlit run app/monitor_ep3.py --server.address 127.0.0.1 --server.port 8502`. Después de conversar, pulse **Actualizar trazas locales**. En «Detalles técnicos» del chat aparece el identificador del turno completado.
3. Para generar una copia estática ejecute `python -m scripts.dashboard_ep3 --salida .observabilidad/monitor-local.html`. El tablero vacío es válido antes del primer turno. Los turnos de uso carecen de un oráculo y repeticiones identificadas, por lo que precisión y consistencia figuran como «s/d».
4. Con Docker Compose las trazas permanecen en el volumen `trazas`. Para exportarlas después de usar el chat: `docker compose exec app python -m scripts.dashboard_ep3 --salida /tmp/monitor.html` y `docker compose cp app:/tmp/monitor.html ./monitor-local.html`.

### Métricas y evidencia

| Indicador | Cálculo y alcance |
|---|---|
| Precisión funcional | Turnos nominales con estado correcto, secuencia exacta de herramientas y comprobación de contenido/estado ÷ turnos etiquetados. Es tasa de acierto en tareas; la batería no califica veracidad general de un LLM. |
| Consistencia operativa | Pares con igual secuencia de herramientas, estado final y veredicto ÷ pares dentro del mismo origen, escenario y variante. Tres repeticiones dan tres pares. Los filtros recalculan los denominadores. |
| Frecuencia de incidencias | Turnos en estado degradado, límite, vacío o error ÷ turnos seleccionados. Los fallos provocados cuentan como incidencias aunque las pruebas de manejo pasen. |
| Latencia | P50 y P95 por rango más próximo sobre milisegundos del reloj monotónico de cada turno. Los tramos muestran por separado memoria, modelo y herramientas. |
| Recursos | CPU del hilo en ms, llamadas de modelo, herramientas y tokens de entrada + salida del proveedor. Sin metadatos de uso se muestra «s/d». La granularidad del reloj de CPU puede producir ceros en turnos breves. |

La [muestra EP3](docs/ep3/trazas-banco.json) contiene 8 escenarios × 2 formulaciones × 3 repeticiones. Compare con el [registro histórico de EP2](evaluation/resultados_agente.json), que usa Groq y Atlas y otro criterio de aprobación. Las [pruebas Python](docs/ep3/pruebas.txt) y las [pruebas de interacción del monitor](docs/ep3/pruebas-dashboard.txt) documentan los resultados obtenidos.

### Privacidad y límites de despliegue

`OBS_ACTIVA=false` suspende nuevas escrituras; `OBS_DB` elige el archivo y `OBS_RETENCION_DIAS` fija la ventana (14 días por defecto). La lectura y la escritura purgan filas vencidas. Las copias de seguridad, las exportaciones y un servicio inactivo requieren gestión de borrado separada. Proteja el directorio con permisos del sistema operativo. La traza conserva ID aleatorio por turno, fecha UTC, etapas, nombres de herramienta permitidos, códigos de estado y contadores. El monitor contiene esos mismos metadatos.

El chat mantiene contexto corto en la sesión. Para una instalación personal se puede activar `MEMORIA_PERSONAL=true` y elegir explícitamente la opción de guardar el chat. Solo se recuperan filas de conversación del perfil configurado; los registros históricos sin propietario quedan fuera de la memoria. La elección controla la persistencia del chat, no las escrituras de tareas y asistencia solicitadas por el usuario. Groq recibe el contenido necesario para inferencia; `USAR_FUENTE_EXTERNA=false` desactiva la búsqueda web del agente. El monitor es una herramienta del operador local. El agente académico usa un perfil único por instalación. Un despliegue multiusuario requiere autenticación y autorización por alumno, retención de datos académicos, cifrado y control de exportaciones antes de una apertura pública.


## Stack

| Componente | Tecnología |
|-----------|-----------|
| Framework de agente | LangChain (`langchain-groq`) — `bind_tools` + ciclo ReAct explícito |
| LLM | Groq — configurable vía `GROQ_MODEL` (actual: `openai/gpt-oss-120b`) |
| Embeddings | `intfloat/multilingual-e5-small` (local, 384 dims) |
| Vector DB | MongoDB Atlas (Vector Search) |
| Memoria | Corto plazo en sesión. Largo plazo opcional en instalación personal |
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

## Requisito de versión de Python

El proyecto requiere **Python 3.11 o 3.12**. En versiones más nuevas (3.13+)
`pandas`, `torch` y `pillow` no tienen wheels precompilados y pip intenta
compilarlos desde fuente, lo que falla sin un toolchain de C configurado.

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Sin `sentence-transformers` el agente igual funciona: `buscar_material`
reporta el fallo y el modelo cae a `buscar_en_web`, pero la búsqueda
semántica sobre el material interno queda inhabilitada.

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
   docker build -t rag-duoc-groq . && docker run --env-file .env -p 127.0.0.1:8501:8501 rag-duoc-groq
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

- El modelo se define en `GROQ_MODEL` y debe admitir llamadas a herramientas.
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
docker run --env-file .env -p 127.0.0.1:8501:8501 rag-duoc-groq
```

Detalles pensados para que corra en otra máquina sin sorpresas:

- El **modelo de embeddings se pre-descarga en el build**, así el arranque no depende de bajar ~470 MB. Si cambias `EMBEDDING_MODEL`, reconstruye con `--build-arg EMBEDDING_MODEL=<modelo>`.
- `.dockerignore` deja fuera `.env`, `.venv`, cachés y `.git` (no se filtran secretos ni se infla la imagen).
- Corre como usuario **no root** y expone healthcheck en `/_stcore/health`.
- **Inicialización automática (opcional):** `INIT_ON_START=true docker compose up --build` crea el índice e ingesta al arrancar (idempotente: no re-ingesta si ya hay chunks). Requiere Atlas alcanzable, red y `GITHUB_REPO` con .md.

> En la entrega se incluye `.env.example`. Cada instalación configura sus propias credenciales en `.env`, fuera de Git y del ZIP.
