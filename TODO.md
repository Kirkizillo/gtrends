# TODO - Google Trends Monitor

## Estado Actual (2026-03-06)

El sistema mantiene **100% de éxito** desde el 3 de febrero (Run #83 en adelante, 0 fallos). En el periodo Feb 23 - Mar 6 se ejecutaron 100 runs (99 exitosos, 0 fallos, 1 en progreso al momento del análisis).

**Resumen de estabilidad:**
- Último fallo: 2026-02-02 (Run #82)
- Desde entonces: 0 fallos en ~200+ runs consecutivos
- 5 grupos funcionando correctamente
- Keywords localizadas desplegadas el 18 Feb, dual timeframe el 20 Feb
- 6 keywords muertas eliminadas el 6 Mar, CN reemplazado por CO

**Análisis Feb 23 – Mar 6 (100 runs):**
- Volumen promedio: **1,375 filas/día** (+5.1% vs baseline pre-localización de ~1,308/día)
- Los términos base en inglés generan ~98.9% de los datos
- Las keywords localizadas aportan ~53 filas/día extra (3.8% del total)

**Rendimiento por país (promedio diario, Feb 23 – Mar 6):**
- Excelentes: PH (~150), IN (~145), WW (~140), BR (~110), ID (~100)
- Buenos: US (~95), VN (~80), TR (~75), MX (~65), NG (~55)
- Moderados: RU (~50), GB (~26), TH (~22), FR (~20), IT (~18)
- Bajos: DE (~16), AU (~12)
- Mínimos: JP (~6), RO (~5), CN (~3) — CN eliminado, reemplazado por CO

**Rendimiento de keywords localizadas (promedio diario, Feb 23 – Mar 6):**
- `apk indir` (TR): 22.9/día — excelente, usa timeframe 4h
- `descargar apk` (MX): 14.6/día — fuerte
- `скачать apk` (RU): 10.0/día — bueno
- `baixar apk` (BR): 4.4/día — moderado
- `unduh apk` (ID): 1.3/día — bajo pero activo
- `ดาวน์โหลด apk` (TH): 0.2/día — marginal, se mantiene por ahora
- 6 keywords muertas (FR, IT, DE, JP, CN, RO): 0 resultados en 2+ semanas → eliminadas

**Cambios notables vs baseline pre-localización:**
- RU: +95.7% (скачать apk funcionando bien)
- MX: +30.4% (descargar apk contribuyendo)
- NG: +33.5% (crecimiento orgánico, sin keyword localizada)
- GB: -41.6% con alta variabilidad (bajo investigación)

---

## Pendiente

### Monitorear CO (Colombia) rendimiento (~2026-03-20)

**Contexto:** El 6 Mar se reemplazó CN (China) por CO (Colombia). CO usa `descargar apk` como keyword localizada (mismo que MX, que genera 14.6/día). Google está completamente accesible en Colombia, por lo que debería rendir mucho mejor que CN (~3/día).

**Qué verificar:**
- [ ] ¿CO genera datos con los 3 términos base (apk, download apk, app download)?
- [ ] ¿`descargar apk` genera datos para CO? (referencia: MX genera 14.6/día con la misma keyword)
- [ ] Comparar rendimiento CO vs el que tenía CN
- [ ] Si CO rinde bien → considerar agregar más mercados LATAM (AR, PE, CL)

### Investigar GB underperformance

**Contexto:** GB promedia solo ~26 filas/día, lo que parece bajo para un mercado anglófono grande. Ha caído -41.6% vs baseline con alta variabilidad entre runs. No hay issues a nivel de código (confirmado: flujo idéntico a todos los demás países).

**Hipótesis:**
- Google Trends puede tener menos granularidad para UK en términos APK (menor cultura de sideloading)
- Los usuarios UK pueden usar terminología distinta ("app store" vs "download apk")
- La ventana de 4h puede ser insuficiente para el menor volumen de UK
- Comparar con AU (~12/día, otro anglófono) para contextualizar si es el volumen natural

**Posibles acciones:**
- [ ] Evaluar añadir términos específicos UK (aunque es anglófono, podría haber patrones distintos)
- [ ] Evaluar probar timeframe 24h para GB específicamente
- [ ] Comparar tendencia GB vs AU para ver si ambos anglófonos muestran patrones similares
- [ ] Decidir si ~26/día es el techo natural para GB o si hay margen de mejora

### Notificaciones
- [ ] Decidir canal de notificación (Slack, Email, Notion)
- [ ] Configurar credenciales/webhook como secret en GitHub
- [ ] Implementar notificación de éxito con resumen de métricas
- [ ] Ya existe soporte de Slack para fallos; falta notificación de éxitos

### Mejoras opcionales
- [ ] Evaluar reducir `RATE_LIMIT_SECONDS` (actualmente 200s, quizás se pueda bajar ahora que es estable)
- [ ] Evaluar reincorporar más términos (`TERMS_FULL` tiene 7, actualmente se usan 3 en `TERMS_REDUCED`)
- [ ] Evaluar reactivar Topics extraction (desactivado por bug de PyTrends)
- [ ] Evaluar keywords para NG (buen volumen orgánico +33.5%, podría beneficiarse de pidgin/local terms)

---

## Completado

### 2026-03-06 — Análisis Feb 23 – Mar 6 y optimización de keywords
- [x] Análisis completo de 100 runs (99 éxitos, 0 fallos): 1,375 filas/día promedio (+5.1%)
- [x] Identificadas 6 keywords muertas: FR, IT, DE, JP, CN, RO (0 resultados en 2+ semanas con 24h)
- [x] Eliminadas las 6 keywords muertas de COUNTRY_EXTRA_TERMS en config.py
- [x] CN (China) reemplazado por CO (Colombia) en REGIONS_FULL, COUNTRY_GROUPS y COUNTRY_EXTRA_TERMS
- [x] CO añadido con keyword localizada `descargar apk` (mismo que MX)
- [x] Investigación GB: confirmado sin issues de código, posible volumen natural bajo
- [x] Requests por grupo reducidos de 13-16 a 13-14 (ahorro ~17 min/día de API)
- [x] Actualizada documentación (CLAUDE.md, README.md, TODO.md)

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
