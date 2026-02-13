# Plan de Escalamiento — Google Trends Monitor

> Fecha: 2026-02-13
> Base: 62 runs exitosos consecutivos, sistema estable

---

## Restricciones actuales (lo que nos limita)

| Componente | Valor actual | Límite real |
|------------|-------------|-------------|
| Términos | 3 (`TERMS_REDUCED`) | ~6 por grupo antes de timeout |
| Regiones | 12 en 3 grupos (4 por grupo) | ~5-6 por grupo antes de timeout |
| Rate limit | 200s entre requests | <60s = errores 429 frecuentes |
| Timeout GitHub Actions | 90 min | Fórmula: `términos × regiones_grupo × 200s` |
| Google Sheets API | ~36 calls/día | 500/100s (sobra 13×) |

**Fórmula de tiempo por grupo:** `términos × regiones_por_grupo × 200s`
- Actual: 3 × 4 × 200s = **40 min** (margen de 50 min)
- Si subimos a 6 términos: 6 × 4 × 200s = **80 min** (al límite)

---

## Vía 1: Escalar territorios

### Opción A — Más grupos (recomendada)

Pasar de 3 a 4-5 grupos. Cada grupo nuevo = 2 ejecuciones más al día.

**Ejemplo con 5 grupos (20 regiones):**

| Grupo | Países | Horarios UTC |
|-------|--------|-------------|
| group_1 | WW, IN, US, BR | 00:00, 12:00 |
| group_2 | ID, MX, PH, GB | 02:30, 14:30 |
| group_3 | AU, VN, DE, RU | 05:00, 17:00 |
| group_4 | NG, KE, EG, ZA | 07:30, 19:30 |
| group_5 | JP, KR, TH, TR | 10:00, 22:00 |

- Tiempo por grupo: 3 × 4 × 200s = 40 min (sin cambios)
- Costo: pasa de 6 a 10 runs/día en GitHub Actions (free tier aguanta)
- Impacto: de 12 a 20 regiones sin tocar rate limits

**Territorios candidatos por potencial de tráfico APK:**
- Africa: Nigeria (NG), Kenia (KE), Egipto (EG), Sudáfrica (ZA)
- Asia: Japón (JP), Corea del Sur (KR), Tailandia (TH), Turquía (TR)
- LATAM: Colombia (CO), Argentina (AR), Perú (PE), Chile (CL)

### Opción B — Workflows paralelos

Crear un segundo workflow en GitHub Actions que corra en paralelo:
- `trends_monitor_americas.yml` → WW, US, BR, MX, CO, AR
- `trends_monitor_apac.yml` → IN, ID, PH, AU, VN, JP, KR, TH
- `trends_monitor_emea.yml` → GB, DE, RU, NG, KE, EG, ZA, TR

Cada workflow tiene su propio timeout de 90 min. Se multiplica capacidad ×3.

### Opción C — Reducir rate limit selectivamente

Algunos territorios tienen menos tráfico y Google es menos agresivo con el rate limiting. Se podría usar un `RATE_LIMIT_SECONDS` dinámico:
- Regiones tier 1 (US, IN, BR): 200s (conservador)
- Regiones tier 2 (PH, VN, AU): 150s
- Regiones tier 3 (NG, KE, EG): 120s

---

## Vía 2: Escalar keywords

### Opción A — Términos por grupo (recomendada)

En vez de que todos los grupos scrapeen los mismos 3 términos, asignar términos distintos por grupo:

```
group_1 (WW, IN, US, BR):  ["apk", "download apk", "app download"]
group_2 (ID, MX, PH, GB):  ["apk", "mod apk", "free games"]
group_3 (AU, VN, DE, RU):  ["apk", "android apk", "apk games"]
```

- "apk" en todos (core term), los otros 2 varían por relevancia regional
- Mismo tiempo de ejecución (3 × 4 × 200s = 40 min)
- Cobertura: pasa de 3 a 7 términos únicos sin aumentar tiempo

### Opción B — Rotación de términos por día

Mantener 3 términos por ejecución, pero rotar cuáles se usan:

```
Lunes/Jueves:   ["apk", "download apk", "app download"]
Martes/Viernes: ["apk", "mod apk", "android apk"]
Miércoles/Sáb:  ["apk", "apk games", "latest apk version"]
Domingo:        ["apk", "obb file download", "free games"]
```

- Sin impacto en tiempo ni en tasa de errores
- Cobertura semanal de 8+ términos
- "apk" siempre presente como ancla

### Opción C — Términos dinámicos (descubrimiento)

Usar los propios resultados del scraper para alimentar nuevos términos:
1. El scraper detecta "terraria apk" como rising query para "apk" en India
2. En la siguiente ejecución, "terraria" se añade automáticamente como término temporal
3. Después de N días sin aparecer en trending, se descarta

Esto convierte el sistema de estático a adaptativo.

---

## Vía 3: Escalar en profundidad (datos más ricos)

### 3A — Frecuencia temporal

Actualmente se scrapea con `TIMEFRAME = "now 4-H"`. Opciones:
- **Doble frecuencia:** Pasar de 2 a 3 ejecuciones por grupo/día (8h completas de cobertura)
- **Timeframes complementarios:** Una ejecución diaria extra con `"now 7-d"` para capturar tendencias semanales que se pierden en las ventanas de 4h

### 3B — Interest Over Time

Actualmente desactivado. Reactivarlo daría:
- Curvas de tendencia por término/región
- Detección de picos y caídas
- **Costo:** +1 request por combinación (+33% tiempo)
- **Cuándo hacerlo:** Cuando el rate limit sea más holgado

### 3C — Comparación entre regiones

Cruzar datos entre países para detectar:
- Apps que están trending en India pero no en Brasil → oportunidad
- Apps que crecen simultáneamente en 5+ regiones → tendencia global
- Apps que solo son relevantes en 1 región → nicho local

Esto no requiere más scraping, solo procesamiento de datos existentes.

---

## Vía 4: Escalar en inteligencia (análisis)

### 4A — Scoring de oportunidades

Asignar un score a cada app detectada basado en:
- Número de regiones donde aparece (globalidad)
- Rising vs Top (momentum)
- Valor del score de Google Trends
- Frecuencia de aparición en los últimos N días
- Categoría (juegos, utilidades, social, etc.)

Output: ranking diario de "Top 10 oportunidades" en vez de lista plana.

### 4B — Alertas por umbral

Configurar alertas cuando:
- Una app nueva aparece en 3+ regiones simultáneamente
- Un término rising sube más de X% entre ejecuciones
- Una app de la watchlist cambia de categoría
- Se detectan más de N apps nuevas en una sola ejecución

Canal: Slack webhook (ya soportado para fallos, extender a alertas de contenido).

### 4C — Historial y tendencias

Los datos en Google Sheets son append-only. Explotar eso:
- Dashboard de evolución: ¿qué apps aparecen consistentemente?
- Detección de estacionalidad: ¿hay patrones por día de la semana/hora?
- Lifecycle tracking: primera aparición → pico → declive de cada app

---

## Vía 5: Escalar la infraestructura

### 5A — Base de datos

Google Sheets funciona ahora, pero tiene límites:
- 10 millones de celdas por spreadsheet
- Estimado actual: ~36 combinaciones × ~20 resultados × 7 columnas × 6 runs/día = ~30,000 celdas/día
- **Límite teórico:** ~333 días antes de llenar un sheet

Opciones de migración (cuando se acerque):
- **SQLite** en el repo (simple, gratis, sin infraestructura)
- **Supabase/PlanetScale** (PostgreSQL gratis, API REST)
- Mantener Sheets como frontend, DB como almacén

### 5B — Ejecución distribuida real

Si la demanda crece más allá de GitHub Actions:
- **GitHub Actions matrix:** Ejecutar grupos como jobs paralelos en un solo workflow
- **Self-hosted runner:** Elimina timeout de 90 min, permite control total
- **Cloud Functions:** Cada grupo como una función independiente con su propio schedule

### 5C — Múltiples fuentes de datos

Google Trends no es la única señal. Complementar con:
- **Google Play Store:** Trending apps por categoría/país (scraping o API)
- **APKPure/APKMirror:** Most downloaded, nuevos uploads
- **App Annie / Sensor Tower:** Si hay presupuesto, APIs de market intelligence
- **Reddit/Twitter/X:** Menciones de apps en comunidades de Android

---

## Priorización sugerida

| # | Acción | Impacto | Esfuerzo | Riesgo |
|---|--------|---------|----------|--------|
| 1 | Términos por grupo (2A) | Alto | Bajo | Nulo |
| 2 | Más grupos de países (1A) | Alto | Bajo | Bajo |
| 3 | Comparación entre regiones (3C) | Alto | Medio | Nulo |
| 4 | Scoring de oportunidades (4A) | Alto | Medio | Nulo |
| 5 | Rotación de términos (2B) | Medio | Bajo | Nulo |
| 6 | Alertas Slack (4B) | Medio | Bajo | Bajo |
| 7 | Timeframes complementarios (3A) | Medio | Bajo | Bajo |
| 8 | Términos dinámicos (2C) | Alto | Alto | Medio |
| 9 | Historial y tendencias (4C) | Alto | Alto | Nulo |
| 10 | Reactivar Interest Over Time (3B) | Medio | Bajo | Medio |
