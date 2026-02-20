# TODO - Google Trends Monitor

## Estado Actual (2026-02-20)

El sistema mantiene **100% de éxito** desde el 3 de febrero (Run #83 en adelante, 0 fallos). Los 5 grupos funcionan sin problemas. Los datos se exportan correctamente a Google Sheets en cada ejecución.

**Resumen de estabilidad:**
- Último fallo: 2026-02-02 (Run #82)
- Desde entonces: 0 fallos en ~140+ runs consecutivos
- 5 grupos funcionando correctamente
- Keywords localizadas desplegadas el 18 Feb, dual timeframe el 20 Feb

**Análisis de datos por territorio (18–20 Feb, Related_Queries_Top):**
- Excelentes: PH (290), IN (282), WW (281), BR (193), ID (190), US (171)
- Buenos: VN (127), TR (125), MX (95), NG (95)
- Bajos: GB (64), FR (35), TH (34), IT (33), DE (31), RU (29)
- Muy bajos: AU (13)
- Mínimos: CN (4), JP (4), RO (4)

**Análisis de keywords localizadas (18–20 Feb):**
- `apk indir` (TR): 24 rows — funciona bien con timeframe de 4h
- `baixar apk` (BR): 2 rows — marginal
- Las otras 10 keywords: 0 rows con timeframe de 4h
- Solución aplicada (20 Feb): las 11 keywords con bajo/nulo rendimiento ahora usan `now 1-d` (24h)
- `apk indir` se mantiene con `now 4-H` porque ya funciona

---

## Pendiente

### Evaluar resultados del dual timeframe (~2026-02-25)

**Contexto:** El 20 Feb se cambió el timeframe de las keywords localizadas con 0 resultados de `now 4-H` a `now 1-d`. Hay que evaluar si la ventana de 24h mejora el yield de datos.

**Qué verificar:**
- [ ] ¿Las 10 keywords que daban 0 resultados ahora generan datos con `now 1-d`?
- [ ] ¿`apk indir` (TR) sigue funcionando bien con `now 4-H`?
- [ ] ¿Los tiempos de ejecución se mantienen estables?
- [ ] Si alguna keyword sigue en 0 tras una semana con 24h → considerar eliminarla para ahorrar tiempo
- [ ] Si funciona → considerar si `baixar apk` (BR) debería volver a `now 4-H` o quedarse en `now 1-d`

**Decisiones pendientes sobre mercados débiles:**
- CN: Google bloqueado en China, 4 filas en 3 días. Si `now 1-d` no mejora → evaluar eliminar
- JP: Solo 4 filas en 3 días. Si localización con 24h no mejora → evaluar eliminar
- RO: Solo 4 filas en 3 días. Si localización con 24h no mejora → evaluar eliminar
- AU: 13 filas, sin keyword localizada (anglófono). Rendimiento bajo pero estable

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

### 2026-02-20 — Dual timeframe para keywords localizadas
- [x] Análisis de rendimiento Feb 18-20: solo 2/12 keywords localizadas generan datos con `now 4-H`
- [x] `apk indir` (TR): 24 rows, funciona bien → se mantiene con `now 4-H`
- [x] `baixar apk` (BR): 2 rows, marginal → cambiada a `now 1-d`
- [x] Otras 10 keywords: 0 rows → cambiadas a `now 1-d`
- [x] Añadir `TIMEFRAME_EXTRA_TERMS = "now 1-d"` en config.py
- [x] Añadir parámetro `timeframe` a `_build_payload()` y `scrape_related_queries()` en trends_scraper.py
- [x] Implementar `extra_terms_ok` set en main.py para excluir `apk indir` del cambio
- [x] Verificar que links generados en TrendData usan el timeframe correcto

### 2026-02-18 — Keywords localizadas por país
- [x] Añadir `COUNTRY_EXTRA_TERMS` en config.py (12 países con términos en idioma local)
- [x] Reordenar bucle en main.py de term→region a region→terms
- [x] Ajustar `total_combinations` para suma variable
- [x] Verificar tiempos de ejecución post-deploy (group_4 ~51 min, todos dentro de margen)
- [x] 24 runs exitosos verificados (18-20 Feb, 100% success rate)

### 2026-02-18 — Verificación escalamiento territorial
- [x] Verificar que group_4 (TH, FR, IT, CN) ejecuta correctamente → **11 runs, 0 fallos**
- [x] Verificar que group_5 (JP, TR, RO, NG) ejecuta correctamente → **10 runs, 0 fallos**
- [x] Comparar tasas de éxito/fallo entre grupos antiguos (1-3) y nuevos (4-5) → **100% éxito en todos**
- [x] Decisión: **Mantener los 5 grupos, no se requiere reversión**
- [x] Análisis de datos del spreadsheet por territorio (volumen y calidad)
- [x] Identificación de territorios que necesitan keywords localizadas

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
