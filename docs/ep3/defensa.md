# Defensa con el monitor

**Apoyo visual:** abrir `docs/ep3/monitor.html` en el navegador. La exposición dura 10 minutos y se reservan otros 10 para las preguntas del docente. El equipo puede intercambiar los turnos de palabra.

| Tiempo | Quién expone | Acción en pantalla y evidencia |
|---|---|---|
| 0:00–2:00 | Juan | Mostrar el boceto de arquitectura y la procedencia de los datos. Identificar las fronteras entre el modelo guionizado, las herramientas que sí se ejecutan y la evidencia histórica de Groq. |
| 2:00–4:00 | Juan | Mostrar el tablero general. Abrir «agenda breve» y «agenda extensa», leer los tamaños y el P95. Explicar qué mide un acierto funcional y qué casos entran en el denominador. |
| 4:00–5:00 | Juan | Filtrar «fallo de herramienta» y abrir un turno. Identificar la etapa, el timeout y el segundo llamado al modelo. |
| 5:00–7:00 | Iván | Comparar «caída de modelo» con «límite de pasos». Localizar qué turno termina después de cinco llamadas y qué salida recibe el estudiante. Contrastar con AG-06 y AG-07 en el informe. |
| 7:00–9:00 | Iván | Abrir el informe en las decisiones escritas por el equipo. Presentar una mejora elegida, su métrica inicial, la prueba que harían y el umbral que usarían al repetir el experimento. |
| 9:00–10:00 | Iván | Mostrar los campos de una traza y las reglas del historial opcional. Explicar los límites de acceso en una instalación compartida. |
| 10:00–20:00 | Ambos | Contestar preguntas por turnos. Cada integrante puede usar el ID de una traza o una fila del informe para fundamentar su respuesta. |

## Preguntas para ensayar

- ¿Por qué hay 30 turnos funcionales y 48 pares comparables? Mostrar cómo se agrupan tres repeticiones por escenario y variante.
- ¿Cómo puede haber un 100 % de consistencia incluso en escenarios de fallo?
- ¿Cómo cambiaría la interpretación de la latencia con un modelo remoto? ¿Qué tiempos y tokens faltan en el registro de octubre?
- ¿Qué condición permitió que AG-07 aprobara aun cuando se repitieron tareas? ¿Qué prueba podría detectar ese defecto?
- ¿Qué información viaja a Groq, qué datos persisten en MongoDB y qué contiene la traza de SQLite?
- ¿Qué evidencia adicional pediría el equipo antes de abrir el servicio a varios estudiantes?
