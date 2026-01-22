# Google Trends Monitor

Sistema automatizado para extraer datos de Google Trends y exportarlos a Google Sheets.

## Características

- Extrae Related Queries (Top + Rising) de Google Trends
- Extrae Related Topics (Top + Rising)
- Rate limiting automático para evitar bloqueos
- Retry logic con backoff exponencial
- Exportación a Google Sheets en modo append
- Logging detallado
- Automatización con cron/Task Scheduler

## Estructura del Proyecto

```
trends_monitor/
├── main.py                    # Script principal
├── config.py                  # Configuración
├── trends_scraper.py          # Scraper de Google Trends
├── google_sheets_exporter.py  # Exportador a Sheets
├── rate_limiter.py            # Control de rate limiting
├── scheduler_setup.sh         # Config cron (Linux/Mac)
├── scheduler_setup_windows.bat # Config Task Scheduler (Windows)
├── requirements.txt           # Dependencias
├── .env.example               # Ejemplo de variables de entorno
├── credentials.json           # Credenciales Google (no incluido)
└── logs/                      # Directorio de logs
```

## Instalación

### 1. Clonar/Descargar el proyecto

```bash
cd trends_monitor
```

### 2. Crear entorno virtual (recomendado)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar credenciales de Google Sheets API

**IMPORTANTE: Sigue estos pasos cuidadosamente**

#### Paso 4.1: Crear proyecto en Google Cloud Console

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. Anota el nombre del proyecto

#### Paso 4.2: Habilitar APIs

1. Ve a **APIs & Services > Library**
2. Busca y habilita:
   - **Google Sheets API**
   - **Google Drive API**

#### Paso 4.3: Crear Service Account

1. Ve a **APIs & Services > Credentials**
2. Click en **Create Credentials > Service Account**
3. Completa:
   - Nombre: `trends-monitor` (o el que prefieras)
   - ID: se genera automáticamente
4. Click **Create and Continue**
5. En "Grant this service account access":
   - Rol: **Editor** (o "Basic > Editor")
6. Click **Continue > Done**

#### Paso 4.4: Crear clave JSON

1. En la lista de Service Accounts, click en el que creaste
2. Ve a la pestaña **Keys**
3. Click **Add Key > Create new key**
4. Selecciona **JSON**
5. Click **Create**
6. Se descargará un archivo JSON
7. **Renómbralo a `credentials.json`** y muévelo a la carpeta `trends_monitor/`

#### Paso 4.5: Crear Google Sheet y compartir

1. Ve a [Google Sheets](https://sheets.google.com)
2. Crea un nuevo spreadsheet
3. Dale un nombre (ej: "Google Trends Data")
4. **IMPORTANTE**: Comparte el sheet con el Service Account:
   - Click en **Share** (Compartir)
   - En el archivo `credentials.json`, busca el campo `client_email`
   - Copia ese email (algo como `trends-monitor@proyecto.iam.gserviceaccount.com`)
   - Pega el email en el campo de compartir
   - Dale permisos de **Editor**
   - Click **Send**

#### Paso 4.6: Obtener el ID del Sheet

El ID está en la URL del sheet:
```
https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit
```

### 5. Configurar variables de entorno

```bash
# Copiar archivo de ejemplo
cp .env.example .env

# Editar .env con tu configuración
```

Contenido de `.env`:
```
GOOGLE_SHEET_ID=tu_sheet_id_aqui
GOOGLE_CREDENTIALS_PATH=credentials.json
```

## Uso

### Verificar configuración (recomendado primero)

```bash
# Probar scraper sin exportar
python main.py --test-scraper
```

### Configurar pestañas en Google Sheets

```bash
python main.py --setup
```

### Ejecutar MVP (solo queries)

```bash
python main.py
```

### Ejecutar completo (queries + topics)

```bash
python main.py --full
```

## Workflow de Desarrollo

**⚠️ IMPORTANTE: Siempre hacer push a GitHub después de probar localmente**

Cuando hagas cambios al código del scraper:

1. **Hacer cambios localmente** en la carpeta `trends_monitor/`

2. **Probar con mock scraper** para verificar la lógica sin usar la API de Google:
   ```bash
   python test_mock_scraper.py   # Verifica lógica de extracción
   python test_user_agents.py    # Verifica rotación de user-agents
   ```

3. **SIEMPRE hacer commit y push** después de que los tests mock pasen:
   ```bash
   git add .
   git commit -m "Descripción de los cambios"
   git push origin main
   ```

4. GitHub Actions ejecutará automáticamente con el nuevo código

**Por qué es importante:**
- GitHub Actions ejecuta el scraping real según el horario configurado
- Los cambios locales NO se usan en GitHub Actions hasta que hagas push
- Los tests mock prueban la lógica sin gastar cuota de la API
- Mantener local y GitHub sincronizados evita confusiones y errores

## Fases de Desarrollo

### Fase 1 (MVP) - Actual
- ✅ Término: solo "apk"
- ✅ Región: solo India
- ✅ Datos: solo Related Queries
- ✅ Ejecución: manual

### Fase 2
Para pasar a Fase 2, edita `config.py`:

```python
# Cambiar de:
CURRENT_TERMS = TERMS_MVP
# A:
CURRENT_TERMS = TERMS_FULL
```

Y ejecutar con `--full` para incluir Topics:
```bash
python main.py --full
```

### Fase 3
Para agregar más países, edita `config.py`:

```python
# Cambiar de:
CURRENT_REGIONS = REGIONS_MVP
# A:
CURRENT_REGIONS = REGIONS_FULL
```

## Automatización

### Windows (Task Scheduler)

Ejecutar como administrador:
```batch
scheduler_setup_windows.bat
```

O manualmente:
1. Abrir Task Scheduler
2. Crear tarea básica
3. Trigger: Daily, repetir cada 4 horas
4. Acción: Iniciar programa
   - Programa: `python`
   - Argumentos: `main.py`
   - Iniciar en: `C:\ruta\a\trends_monitor`

### Linux/Mac (cron)

```bash
bash scheduler_setup.sh
```

O manualmente:
```bash
crontab -e

# Agregar línea (cada 4 horas):
0 */4 * * * cd /ruta/a/trends_monitor && python main.py >> logs/cron.log 2>&1
```

### GitHub Actions (Recomendado)

El repositorio incluye un workflow de GitHub Actions que ejecuta automáticamente cada 4 horas.

**Configuración:**

1. Sube el repositorio a GitHub

2. Ve a **Settings > Secrets and variables > Actions**

3. Agrega estos secretos:
   - `GOOGLE_CREDENTIALS`: Contenido completo del archivo `credentials.json`
   - `GOOGLE_SHEET_ID`: El ID de tu Google Sheet

4. El workflow se ejecutará automáticamente cada 4 horas

5. También puedes ejecutar manualmente desde **Actions > Google Trends Monitor > Run workflow**

**Ventajas de GitHub Actions:**
- Gratis para repositorios públicos
- No requiere servidor propio
- Los secretos se almacenan de forma segura
- Logs disponibles en la pestaña Actions

## Estructura de Google Sheets

El sistema crea 4 pestañas:

| Pestaña | Contenido |
|---------|-----------|
| Related_Queries_Top | Top queries relacionados |
| Related_Queries_Rising | Queries en crecimiento |
| Related_Topics_Top | Top topics relacionados |
| Related_Topics_Rising | Topics en crecimiento |

Columnas en cada pestaña:
- `timestamp`: Fecha/hora de extracción (UTC)
- `term`: Término buscado
- `country_code`: Código de país (ej: IN)
- `country_name`: Nombre del país
- `title`: Query o Topic encontrado
- `value`: Valor/score
- `link`: Link a Google Trends

## Troubleshooting

### Error: "credentials.json not found"
- Verifica que descargaste el archivo JSON de Google Cloud
- Verifica que lo renombraste a `credentials.json`
- Verifica que está en la carpeta `trends_monitor/`

### Error: "Spreadsheet not found"
- Verifica que copiaste correctamente el ID del sheet
- Verifica que compartiste el sheet con el email del Service Account

### Error: "Permission denied" en Google Sheets
- Asegúrate de compartir el sheet con el Service Account como **Editor**
- El email está en `credentials.json` campo `client_email`

### Error: "Too many requests" de Google Trends
- El sistema tiene rate limiting de 60 segundos
- Si persiste, aumenta `RATE_LIMIT_SECONDS` en `config.py`

### No se extraen datos
- Google Trends puede no tener datos para ciertos términos/regiones
- Prueba con términos más populares
- Verifica que el timeframe es válido

## Logs

Los logs se guardan en `logs/` con formato:
```
trends_YYYYMMDD_HHMMSS.log
```

Para ver logs recientes:
```bash
# Windows
type logs\trends_*.log | more

# Linux/Mac
tail -f logs/trends_*.log
```

## Configuración Avanzada

Edita `config.py` para ajustar:

```python
# Rate limiting (segundos entre requests)
RATE_LIMIT_SECONDS = 60

# Reintentos en caso de error
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30

# Timeframe de datos
TIMEFRAME = "now 1-d"  # Últimas 24 horas
```

## Licencia

MIT License
