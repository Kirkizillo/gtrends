# TODO - Google Trends Monitor

## Estado Actual (2026-02-18)

El sistema lleva **114 runs consecutivos exitosos** (Runs #83–#196, desde el 3 de febrero). Los 5 grupos (incluidos los nuevos group_4 y group_5) funcionan sin fallos. Los datos se exportan correctamente a Google Sheets en cada ejecución.

**Resumen de estabilidad:**
- Runs totales: 196
- Último fallo: 2026-02-02 (Run #82)
- Racha actual: 114 éxitos consecutivos (Runs #83–#196)
- 5 grupos funcionando: 52 runs post-escalamiento sin fallos (13–18 Feb)

**Análisis de datos por territorio (13–18 Feb, Related_Queries_Top):**
- Excelentes (sin tocar): PH (2.081), IN (1.807), ID (1.520), BR (1.236), VN (978), TR (254), NG (286)
- Buenos (mejorarán con localización): MX (950), DE (391), RU (339), TH (79), FR (71), IT (67)
- Necesitan localización urgente: JP (12), RO (8)
- Problemático estructuralmente: CN (3 filas — Google bloqueado en China)

---

## Pendiente

### Keywords localizadas por país (2026-02-18)

**Qué:** Añadir términos de búsqueda en el idioma local de cada país, sin quitar los existentes.

**Por qué:** Los términos en inglés funcionan bien en mercados anglófonos y del sudeste asiático, pero FR (71 filas), IT (67), JP (12), RO (8) y CN (3) devuelven datos escasos porque sus usuarios buscan en su idioma local.

**Cómo — Opción B (términos por país):**

1. Añadir `COUNTRY_EXTRA_TERMS` en `config.py`:
   ```python
   # Términos extra por país (se SUMAN a CURRENT_TERMS)
   COUNTRY_EXTRA_TERMS = {
       "BR": ["baixar apk"],           # Portugués
       "MX": ["descargar apk"],        # Español
       "ID": ["unduh apk"],            # Bahasa Indonesia
       "DE": ["apk herunterladen"],    # Alemán
       "RU": ["скачать apk"],          # Ruso
       "TH": ["ดาวน์โหลด apk"],       # Tailandés
       "FR": ["télécharger apk"],      # Francés
       "IT": ["scaricare apk"],        # Italiano
       "TR": ["apk indir"],            # Turco
       "JP": ["apkダウンロード"],       # Japonés
       "CN": ["下载apk"],              # Chino (intento)
       "RO": ["descărcare apk"],       # Rumano (intento)
   }
   ```
   Países sin entrada (WW, IN, US, GB, PH, AU, VN, NG) siguen con los 3 base.

2. Cambiar el bucle en `main.py` de `term → region` a `region → terms`:
   ```python
   # ANTES:
   for term in terms:
       for geo, country_name in regions.items():
           scrape(term, geo)

   # DESPUÉS:
   for geo, country_name in regions.items():
       country_terms = terms + config.COUNTRY_EXTRA_TERMS.get(geo, [])
       for term in country_terms:
           scrape(term, geo)
   ```

3. Ajustar `total_combinations` para que refleje la suma variable:
   ```python
   total_combinations = sum(
       len(terms) + len(config.COUNTRY_EXTRA_TERMS.get(geo, []))
       for geo in regions
   )
   ```

4. Actualizar el log inicial para mostrar el desglose de términos por país.

**Impacto en tiempo por grupo:**

| Grupo | Requests antes | Requests después | Tiempo estimado |
|-------|---------------|-----------------|-----------------|
| group_1 (WW,IN,US,BR) | 12 | 13 (+1 BR) | ~43 min |
| group_2 (ID,MX,PH,GB) | 12 | 14 (+1 ID, +1 MX) | ~47 min |
| group_3 (AU,VN,DE,RU) | 12 | 14 (+1 DE, +1 RU) | ~47 min |
| group_4 (TH,FR,IT,CN) | 12 | 16 (+1 cada uno) | ~53 min |
| group_5 (JP,TR,RO,NG) | 12 | 15 (+1 JP, +1 TR, +1 RO) | ~50 min |

Todos por debajo del timeout de 90 min. El más cargado es group_4 con ~53 min.

**Archivos a modificar:**
- `config.py` — Añadir `COUNTRY_EXTRA_TERMS`
- `main.py` — Reordenar bucle, ajustar total_combinations y log

**Archivos que NO se tocan:**
- `trends_scraper.py` — No cambia (recibe term + geo, igual que antes)
- `google_sheets_exporter.py` — No cambia (recibe TrendData, igual que antes)
- `report_generator.py` — No cambia
- `.github/workflows/` — No cambia

**Rollback:** Eliminar `COUNTRY_EXTRA_TERMS` de config.py y revertir el bucle en main.py.

**Monitorización post-deploy:**
- [ ] Verificar que los 5 grupos completan dentro del timeout
- [ ] Comparar volumen de datos nuevos vs anterior por país (especialmente FR, IT, JP, RO, CN)
- [ ] Si group_4 (~53 min) se acerca al timeout → quitar 1 extra term del grupo
- [ ] **Revisión a la semana (~2026-02-25):** Evaluar impacto de keywords localizadas

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
