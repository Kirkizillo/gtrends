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
import logging
import os
import sys
from datetime import datetime

import config
from database import TrendsDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def generate_digest(db: TrendsDatabase, date: str = None) -> str:
    """
    Genera un digest HTML consolidado del día.

    Args:
        db: TrendsDatabase conectada
        date: Fecha en formato YYYY-MM-DD (default: hoy)

    Returns:
        String HTML del digest
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")

    # Obtener datos del día
    top_apps = db.get_today_top_apps(limit=15)
    new_apps = db.get_today_new_apps()
    region_activity = db.get_region_activity()
    comparison = db.get_daily_comparison()

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
        return ""
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


def main():
    parser = argparse.ArgumentParser(description="Genera digest diario consolidado")
    parser.add_argument('--date', type=str, help="Fecha YYYY-MM-DD (default: hoy)")
    args = parser.parse_args()

    # Conectar a Turso
    db = TrendsDatabase()
    if not db.connect():
        logger.error("No se pudo conectar a Turso. Verifica credenciales.")
        sys.exit(1)

    # Generar digest
    logger.info("Generando digest diario...")
    html = generate_digest(db, date=args.date)

    # Guardar
    output_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(output_dir, exist_ok=True)

    date_str = args.date or datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(output_dir, f"digest_{date_str}.html")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.info(f"Digest guardado: {filepath}")
    db.close()


if __name__ == "__main__":
    main()
