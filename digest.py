"""
Generador de digest diario.

Consolida todos los datos del día (de las 10 runs) en un informe
HTML que muestra: top apps, apps nuevas, actividad por región, y
comparación vs día anterior.

Uso:
    python digest.py             # Genera digest del día actual
    python digest.py --date 2026-03-10   # Genera digest de fecha específica
"""
import argparse
import glob
import logging
import os
import sys
from datetime import datetime, timedelta

import config
from database import TrendsDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def fetch_digest_data(db: TrendsDatabase, date: str = None) -> dict:
    """
    Obtiene los datos del día una sola vez, para renderizarlos dos veces
    (HTML + Markdown) sin duplicar queries a Turso.

    Args:
        db: TrendsDatabase conectada
        date: Fecha en formato YYYY-MM-DD (default: hoy, día calendario UTC)

    Returns:
        Dict con {date, top_apps, new_apps, region_activity, comparison}
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")

    return {
        'date': date,
        'top_apps': db.get_today_top_apps(limit=15, date=date),
        'new_apps': db.get_today_new_apps(date=date),
        'region_activity': db.get_region_activity(date=date),
        'comparison': db.get_daily_comparison(date=date),
    }


def generate_digest(db: TrendsDatabase, date: str = None) -> str:
    """
    Genera un digest HTML consolidado del día (compatibilidad hacia atrás).

    Args:
        db: TrendsDatabase conectada
        date: Fecha en formato YYYY-MM-DD (default: hoy)

    Returns:
        String HTML del digest
    """
    return generate_digest_html(fetch_digest_data(db, date))


def generate_digest_html(data: dict) -> str:
    """
    Renderiza el digest HTML a partir de los datos ya obtenidos.

    Args:
        data: Dict de fetch_digest_data()

    Returns:
        String HTML del digest
    """
    date = data['date']
    top_apps = data['top_apps']
    new_apps = data['new_apps']
    region_activity = data['region_activity']
    comparison = data['comparison']

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Digest Diario - {date}</title>
<style>
{_digest_css()}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>Digest Diario</h1>
        <div class="meta">{date} | Consolidado de todas las ejecuciones del dia</div>
    </div>

    {_comparison_section(comparison)}
    {_top_apps_section(top_apps)}
    {_new_apps_section(new_apps)}
    {_region_section(region_activity)}

    <div class="footer">
        Generado por Google Trends Monitor | {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
    </div>
</div>
</body>
</html>"""


def _comparison_section(comp: dict) -> str:
    today = comp.get('today', 0)
    yesterday = comp.get('yesterday', 0)
    change = comp.get('change_pct', 0)
    arrow = "+" if change >= 0 else ""
    color = "#00b894" if change >= 0 else "#d63031"
    return f"""
<div class="card">
    <h2>Volumen del Dia</h2>
    <div class="comparison">
        <div class="comp-box">
            <div class="comp-value">{today}</div>
            <div class="comp-label">Hoy</div>
        </div>
        <div class="comp-arrow" style="color: {color}">{arrow}{change}%</div>
        <div class="comp-box">
            <div class="comp-value">{yesterday}</div>
            <div class="comp-label">Ayer</div>
        </div>
    </div>
</div>"""


def _top_apps_section(apps: list) -> str:
    if not apps:
        return '<div class="card"><h2>Top Apps del Dia</h2><p class="empty">Sin datos</p></div>'
    rows = ""
    for i, app in enumerate(apps, 1):
        countries = ', '.join(app['countries'][:5])
        extra = f" +{len(app['countries']) - 5}" if len(app['countries']) > 5 else ""
        has_rising = any('rising' in t for t in app['data_types'])
        badge = '<span class="badge-r">Rising</span>' if has_rising else '<span class="badge-t">Top</span>'
        rows += f"""<tr>
            <td class="rank">#{i}</td>
            <td class="name">{_esc(app['title'])}</td>
            <td>{app['count']}x</td>
            <td>{badge}</td>
            <td class="countries">{_esc(countries)}{extra}</td>
        </tr>"""
    return f"""
<div class="card">
    <h2>Top 15 Apps del Dia</h2>
    <table>
        <tr><th>#</th><th>App</th><th>Apariciones</th><th>Tipo</th><th>Paises</th></tr>
        {rows}
    </table>
</div>"""


def _new_apps_section(apps: list) -> str:
    if not apps:
        return '<div class="card"><h2>Apps Nuevas Hoy</h2><p class="empty">Sin apps nuevas</p></div>'
    rows = ""
    for app in apps[:20]:
        countries = ', '.join(app['countries'][:5])
        rows += f"""<tr>
            <td class="name">{_esc(app['display_name'] or app['title_normalized'])}</td>
            <td class="countries">{_esc(countries)}</td>
            <td>{_esc(app['first_seen'][:16])}</td>
        </tr>"""
    extra = f"<p class='more'>...y {len(apps) - 20} mas</p>" if len(apps) > 20 else ""
    return f"""
<div class="card">
    <h2>Apps Nuevas Hoy <span class="count">{len(apps)}</span></h2>
    <table>
        <tr><th>App</th><th>Paises</th><th>Primera vez</th></tr>
        {rows}
    </table>
    {extra}
</div>"""


def _region_section(regions: list) -> str:
    if not regions:
        return '<div class="card"><h2>Actividad por Region</h2><p class="empty">Sin datos de regiones</p></div>'
    max_count = regions[0]['count'] if regions else 1
    cells = ""
    for r in regions:
        ratio = r['count'] / max_count if max_count > 0 else 0
        if ratio > 0.7:
            bg = "#00b894"
            fg = "white"
        elif ratio > 0.4:
            bg = "#55efc4"
            fg = "#2d3436"
        elif ratio > 0.2:
            bg = "#ffeaa7"
            fg = "#2d3436"
        else:
            bg = "#dfe6e9"
            fg = "#636e72"
        cells += f'<div class="region-cell" style="background:{bg};color:{fg}"><div class="region-code">{r["country_code"]}</div><div class="region-count">{r["count"]}</div></div>'
    return f"""
<div class="card">
    <h2>Actividad por Region</h2>
    <div class="region-grid">{cells}</div>
</div>"""


def _digest_css() -> str:
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; color: #2d3436; line-height: 1.5; }
.container { max-width: 800px; margin: 0 auto; padding: 20px; }
.header { background: linear-gradient(135deg, #6c5ce7, #a29bfe); color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 20px; }
.header h1 { font-size: 22px; margin-bottom: 4px; }
.header .meta { font-size: 13px; opacity: 0.85; }
.card { background: white; border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card h2 { font-size: 16px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid #f1f2f6; }
.count { background: #dfe6e9; color: #636e72; font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 8px 10px; background: #f1f2f6; font-weight: 600; font-size: 11px; text-transform: uppercase; color: #636e72; }
td { padding: 8px 10px; border-bottom: 1px solid #f1f2f6; }
tr:hover td { background: #f8f9fa; }
.rank { font-weight: 700; color: #0984e3; width: 40px; }
.name { font-weight: 600; }
.countries { font-size: 12px; color: #636e72; }
.badge-r { background: #e17055; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.badge-t { background: #74b9ff; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.comparison { display: flex; align-items: center; justify-content: center; gap: 32px; padding: 16px 0; }
.comp-box { text-align: center; }
.comp-value { font-size: 32px; font-weight: 700; color: #0984e3; }
.comp-label { font-size: 12px; color: #636e72; text-transform: uppercase; }
.comp-arrow { font-size: 24px; font-weight: 700; }
.region-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 8px; }
.region-cell { padding: 10px; border-radius: 8px; text-align: center; }
.region-code { font-weight: 700; font-size: 14px; }
.region-count { font-size: 11px; opacity: 0.8; }
.empty { color: #b2bec3; font-style: italic; padding: 12px 0; }
.more { color: #636e72; font-size: 12px; margin-top: 8px; }
.footer { text-align: center; color: #b2bec3; font-size: 11px; padding: 16px 0; }
"""


def _esc(text: str) -> str:
    if not text:
        return ""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# =============================================================================
# Digest en Markdown (versión compacta para commitear al repo)
# =============================================================================

def _md_esc(text: str) -> str:
    """Escapa el carácter pipe para no romper tablas Markdown."""
    if not text:
        return ""
    return str(text).replace('|', '\\|')


def generate_digest_markdown(data: dict) -> str:
    """
    Genera la versión Markdown compacta del digest diario.

    Reutiliza los datos ya obtenidos por fetch_digest_data() — misma fuente
    que el HTML, render distinto.

    Args:
        data: Dict de fetch_digest_data()

    Returns:
        String Markdown del digest
    """
    date = data['date']
    comp = data['comparison']
    top_apps = data['top_apps']
    new_apps = data['new_apps']
    regions = data['region_activity']

    today = comp.get('today', 0)
    yesterday = comp.get('yesterday', 0)
    change = comp.get('change_pct', 0)
    sign = "+" if change >= 0 else ""

    lines = [
        f"# Digest Diario - {date}",
        "",
        f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Volumen del Dia",
        "",
        f"| Hoy | Ayer | Cambio |",
        f"|-----|------|--------|",
        f"| {today} | {yesterday} | {sign}{change}% |",
        "",
        "## Top 15 Apps del Dia",
        "",
    ]

    if top_apps:
        lines.append("| # | App | Apariciones | Tipo | Paises |")
        lines.append("|---|-----|-------------|------|--------|")
        for i, app in enumerate(top_apps, 1):
            countries = ', '.join(app['countries'][:5])
            extra = f" +{len(app['countries']) - 5}" if len(app['countries']) > 5 else ""
            has_rising = any('rising' in t for t in app['data_types'])
            badge = "Rising" if has_rising else "Top"
            lines.append(
                f"| {i} | {_md_esc(app['title'])} | {app['count']}x | {badge} | {_md_esc(countries)}{extra} |"
            )
    else:
        lines.append("Sin datos")

    lines += ["", f"## Apps Nuevas Hoy ({len(new_apps)})", ""]
    if new_apps:
        for app in new_apps[:20]:
            name = app['display_name'] or app['title_normalized']
            countries = ', '.join(app['countries'][:5])
            first_seen = (app['first_seen'] or "")[:16]
            lines.append(f"- **{_md_esc(name)}** ({_md_esc(countries)}) — {first_seen}")
        if len(new_apps) > 20:
            lines.append(f"- ...y {len(new_apps) - 20} mas")
    else:
        lines.append("Sin apps nuevas")

    lines += ["", "## Actividad por Region", ""]
    if regions:
        lines.append("| Region | Registros |")
        lines.append("|--------|-----------|")
        for r in regions:
            lines.append(f"| {r['country_code']} | {r['count']} |")
    else:
        lines.append("Sin datos de regiones")

    lines += ["", "---", "Generado por Google Trends Monitor", ""]
    return "\n".join(lines)


# =============================================================================
# Dashboard en README.md (bloque entre marcadores, actúa como keepalive:
# el commit diario evita que GitHub desactive el workflow por inactividad)
# =============================================================================

DASHBOARD_START = "<!-- DASHBOARD:START -->"
DASHBOARD_END = "<!-- DASHBOARD:END -->"


def update_readme_dashboard(data: dict, readme_path: str = None) -> bool:
    """
    Reescribe el bloque de dashboard del README.md entre los marcadores
    DASHBOARD:START y DASHBOARD:END.

    Args:
        data: Dict de fetch_digest_data()
        readme_path: Ruta al README.md (default: junto a este script)

    Returns:
        True si se actualizó correctamente
    """
    if readme_path is None:
        readme_path = os.path.join(os.path.dirname(__file__), "README.md")

    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.warning(f"README.md no encontrado: {readme_path}")
        return False

    if DASHBOARD_START not in content or DASHBOARD_END not in content:
        logger.warning("Marcadores de dashboard no encontrados en README.md")
        return False

    comp = data['comparison']
    change = comp.get('change_pct', 0)
    sign = "+" if change >= 0 else ""

    top5 = ""
    for i, app in enumerate(data['top_apps'][:5], 1):
        countries = ', '.join(app['countries'][:3])
        top5 += f"{i}. **{_md_esc(app['title'])}** — {app['count']}x ({_md_esc(countries)})\n"
    if not top5:
        top5 = "Sin datos\n"

    block = f"""{DASHBOARD_START}
## Dashboard

**Ultima actualizacion:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

**Volumen hoy:** {comp.get('today', 0)} registros ({sign}{change}% vs ayer)

**Top 5 apps del dia:**

{top5}
[Ver digest completo](reports/latest.md)
{DASHBOARD_END}"""

    start_idx = content.index(DASHBOARD_START)
    end_idx = content.index(DASHBOARD_END) + len(DASHBOARD_END)
    new_content = content[:start_idx] + block + content[end_idx:]

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    logger.info("Dashboard del README.md actualizado")
    return True


def prune_old_reports(reports_dir: str, days: int = 90):
    """Elimina reports/digest_*.md con más de N días de antigüedad."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    for path in glob.glob(os.path.join(reports_dir, "digest_*.md")):
        name = os.path.basename(path)
        try:
            file_date = datetime.strptime(name, "digest_%Y-%m-%d.md")
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                os.remove(path)
                logger.info(f"Report antiguo eliminado: {name}")
            except OSError as e:
                logger.warning(f"No se pudo eliminar {name}: {e}")


def notify_slack_success(data: dict) -> bool:
    """
    Notificación de éxito a Slack con resumen del digest (TODO.md pendiente).
    Solo actúa si SLACK_WEBHOOK_URL está definida. Nunca lanza excepciones.
    """
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        logger.info("SLACK_WEBHOOK_URL no definida, se omite notificación de éxito")
        return False

    comp = data.get('comparison') or {}
    top = data.get('top_apps') or []
    new_apps = data.get('new_apps') or []
    top_names = ", ".join(str(a.get('display_name', a.get('title', '?'))) for a in top[:5])
    text = (
        f":chart_with_upwards_trend: *Digest {data.get('date')}* — "
        f"{comp.get('today', 0)} filas ({comp.get('change_pct', 0.0):+.1f}% vs ayer), "
        f"{len(new_apps)} apps nuevas.\n"
        f"Top: {top_names or 'sin datos'}\n"
        f"<https://github.com/Kirkizillo/gtrends/blob/main/reports/latest.md|Ver informe completo>"
    )
    try:
        import requests
        resp = requests.post(webhook, json={"text": text}, timeout=15)
        ok = resp.status_code < 300
        if not ok:
            logger.warning(f"Slack devolvió {resp.status_code}")
        return ok
    except Exception as e:
        logger.warning(f"No se pudo notificar a Slack: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Genera digest diario consolidado")
    parser.add_argument('--date', type=str, help="Fecha YYYY-MM-DD (default: hoy)")
    parser.add_argument('--weekly', action='store_true', help="Forzar generacion de informe semanal")
    args = parser.parse_args()

    # Conectar a Turso en modo remoto: sin replica local ni sync completo.
    # El embedded replica descargaba la BD entera (~107k filas) y agotaba
    # la cuota mensual del plan free de Turso hacia el día 9-10 del mes.
    db = TrendsDatabase()
    if not db.connect(remote_only=True):
        logger.error("No se pudo conectar a Turso. Verifica credenciales.")
        sys.exit(1)

    # Retención: acota el tamaño de la BD y el egress de sync de las replicas
    db.purge_old_trends(days=365)

    # Obtener datos una vez, renderizar dos veces (HTML + Markdown)
    logger.info("Generando digest diario...")
    date_str = args.date or datetime.utcnow().strftime("%Y-%m-%d")
    data = fetch_digest_data(db, date=date_str)
    html = generate_digest_html(data)
    markdown = generate_digest_markdown(data)

    # Guardar HTML en logs/ (artifact efímero)
    output_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, f"digest_{date_str}.html")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.info(f"Digest guardado: {filepath}")

    # Guardar Markdown en reports/ (se commitea al repo — mantiene el
    # historial navegable y actúa como keepalive del workflow)
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    md_path = os.path.join(reports_dir, f"digest_{date_str}.md")
    latest_path = os.path.join(reports_dir, "latest.md")
    for path in (md_path, latest_path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(markdown)
    logger.info(f"Digest Markdown guardado: {md_path} (+ latest.md)")

    # Actualizar dashboard del README y limpiar reports antiguos
    update_readme_dashboard(data)
    prune_old_reports(reports_dir, days=90)

    # Notificación de éxito (opcional, requiere SLACK_WEBHOOK_URL)
    notify_slack_success(data)

    # Informe semanal: se genera los domingos o con --weekly
    is_sunday = datetime.utcnow().weekday() == 6
    if is_sunday or args.weekly:
        logger.info("Generando informe semanal...")
        try:
            from weekly_report import save_weekly_report
            weekly_path = save_weekly_report(db, days=7, output_dir=output_dir)
            logger.info(f"Informe semanal guardado: {weekly_path}")
        except Exception as e:
            logger.error(f"Error generando informe semanal: {e}")

    db.close()


if __name__ == "__main__":
    main()
