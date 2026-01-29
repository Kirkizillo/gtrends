# TODO - Google Trends Monitor

## Pendiente

### Revisión de horarios (Semana del 2026-02-05)
- [ ] Analizar tasas de éxito/fallo por grupo tras cambio de horarios
- [ ] Comparar con datos anteriores (antes del 2026-01-29)
- [ ] Verificar si group_3 (08:10, 20:10 UTC) presenta problemas
- [ ] Ajustar horarios si es necesario
- [ ] Evaluar implementar "Skip términos baja prioridad" si tasa de 429 sigue alta

**Contexto:** El 2026-01-29 se cambiaron los horarios para evitar 12:00 y 16:00 UTC (66% tasa de fallo):
- group_1: 00:00, 12:00 → 00:00, 14:00
- group_2: 04:05, 16:05 → 04:05, 18:05
- group_3: sin cambios (08:10, 20:10)

**Comando para análisis:**
```bash
gh run list --repo [owner]/[repo] --limit 50 --json conclusion,createdAt,displayTitle
```

---

## Completado

### 2026-01-29
- [x] Cambiar horarios de cron para evitar horas pico
- [x] Reducir MAX_RETRIES de 3 a 2
- [x] Añadir MAX_BACKOFF_SECONDS = 180
- [x] Deduplicación case-insensitive y Unicode-aware
- [x] Clasificación de errores (ErrorType)
- [x] Métricas JSON estructuradas
