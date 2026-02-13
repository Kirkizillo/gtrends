# TODO - Google Trends Monitor

## Estado Actual (2026-02-13)

El sistema lleva **62 runs consecutivos exitosos** (desde el 3 de febrero). Los datos se exportan correctamente a Google Sheets en cada ejecución. El último fallo fue el Run #82 el 2 de febrero.

**Resumen de estabilidad:**
- Runs totales: 144
- Último fallo: 2026-02-02 (Run #82)
- Racha actual: 62 éxitos consecutivos (Runs #83–#144)
- Todos los grupos (1, 2, 3) funcionan sin problemas

---

## Pendiente

### Monitorización de nuevos territorios (semana del 2026-02-13)
- [ ] Verificar que group_4 (TH, FR, IT, CN) ejecuta correctamente
- [ ] Verificar que group_5 (JP, TR, RO, NG) ejecuta correctamente
- [ ] Comparar tasas de éxito/fallo entre grupos antiguos (1-3) y nuevos (4-5)
- [ ] Si hay timeouts o 429 persistentes en nuevos grupos → revertir
- [ ] **Decisión a la semana (~2026-02-20):** Mantener, ajustar o revertir

### Siguiente fase: Keywords localizadas (después de validar territorios)
- [ ] Mapear términos de búsqueda por idioma/región (ej: "télécharger apk" para FR)
- [ ] Evaluar asignar `TERMS` distintos por grupo según relevancia regional
- [ ] "apk" como término ancla en todos los grupos, complementos localizados

### Notificaciones
- [ ] Decidir canal de notificación (Slack, Email, Notion)
- [ ] Configurar credenciales/webhook como secret en GitHub
- [ ] Implementar notificación de éxito con resumen de métricas
- [ ] Ya existe soporte de Slack para fallos; falta notificación de éxitos

### Mejoras opcionales
- [ ] Evaluar reducir `RATE_LIMIT_SECONDS` (actualmente 200s, quizás se pueda bajar ahora que es estable)
- [ ] Evaluar reincorporar más términos (`TERMS_FULL` tiene 7, actualmente se usan 3 en `TERMS_REDUCED`)
- [ ] Evaluar reactivar Topics extraction (desactivado por bug de PyTrends)

---

## Completado

### 2026-02-13 — Escalamiento territorial
- [x] Añadir 8 nuevos territorios: TH, FR, IT, CN, JP, TR, RO, NG
- [x] Pasar de 3 a 5 grupos (4 regiones por grupo, 20 regiones total)
- [x] Redistribuir horarios: 10 runs/día con separación de ~2h25min
- [x] Detección de grupo por minutos (TOTAL_MIN) en vez de hora
- [x] Actualizar argparse en main.py para group_4 y group_5
- [x] Actualizar documentación (CLAUDE.md, README.md, TODO.md)

### 2026-02-05 → 2026-02-13 — Estabilización confirmada
- [x] Analizar tasas de éxito/fallo por grupo tras cambio de horarios → **Resultado: 62 runs sin fallos**
- [x] Comparar con datos anteriores (antes del 2026-01-29) → **Antes: fallos frecuentes a las 12:00/16:00 UTC**
- [x] Verificar si group_3 (08:10, 20:10 UTC) presenta problemas → **Sin problemas, funciona correctamente**
- [x] Confirmar que los horarios actuales son adecuados → **Sí, no se requieren más ajustes**

### 2026-01-30
- [x] Generador de informes para equipo de contenidos (report_generator.py)
- [x] Exportación de informes a pestaña en Google Sheets (formato rico con secciones)
- [x] Auto-posicionamiento de pestañas de informe después de Related_Queries_Rising
- [x] Detección de grupo por rangos de hora (tolerancia a retrasos de GitHub Actions)

### 2026-01-29
- [x] Cambiar horarios de cron para evitar horas pico (12:00, 16:00 UTC → 14:00, 18:00 UTC)
- [x] Reducir MAX_RETRIES de 3 a 2
- [x] Añadir MAX_BACKOFF_SECONDS = 180
- [x] Deduplicación case-insensitive y Unicode-aware
- [x] Clasificación de errores (ErrorType)
- [x] Métricas JSON estructuradas
- [x] Auto-cierre de issues de scraping-failure en runs exitosos
- [x] Validación de configuración con fail-fast
- [x] Mejorar calidad de datos y observabilidad

### 2026-01-22
- [x] Rate limiting mejorado + rotación de user-agents (20 combinaciones)
- [x] Tests unitarios con mocks (sin llamadas reales a API)
- [x] Fix: reconstruir payload después de retry 429
- [x] Añadir Worldwide (WW) y Filipinas (PH)
- [x] Rebalancear grupos de países (4-3-3)
- [x] Cambiar timeframe a 4 horas
- [x] Desactivar Topics (bug PyTrends) e Interest Over Time
- [x] Exportación incremental por combinación term/region

### 2026-01-21
- [x] MVP inicial: "apk" en India, Related Queries
- [x] GitHub Actions con ejecución por grupos de países
- [x] Fase 2 y 3: todos los términos y 12 regiones
- [x] Rate limiting (90s), retry con backoff, proxy support
- [x] CLAUDE.md para guía de desarrollo
