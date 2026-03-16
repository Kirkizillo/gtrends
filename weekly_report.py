"""
Generador de informe semanal por mercado.

Consolida los datos de los ultimos 7 dias en un informe HTML con:
- Top apps por mercado (20 paises)
- Apps nuevas de la semana por region
- Tendencias cross-market (3+ paises)
- Comparacion vs semana anterior

Se ejecuta los domingos desde digest.py, antes del cleanup de pestanas antiguas.

Uso directo:
    python weekly_report.py                    # Genera informe de los ultimos 7 dias
    python weekly_report.py --days 14          # Ultimos 14 dias
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


def generate_weekly_report(db: TrendsDatabase, days: int = 7) -> str:
    """
    Genera un informe semanal HTML consolidado por mercado.

    Args:
        db: TrendsDatabase conectada
        days: Numero de dias a consolidar (default: 7)

    Returns:
        String HTML del informe semanal
    """
    date = datetime.utcnow().strftime("%Y-%m-%d")

    top_by_country = db.get_weekly_top_by_country(days=days, limit=10)
    new_apps = db.get_weekly_new_apps(days=days)
    cross_market = db.get_weekly_cross_market(days=days, min_countries=3)
    comparison = db.get_weekly_comparison()

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Informe Semanal - {date}</title>
<style>
{_weekly_css()}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>Informe Semanal</h1>
        <div class="meta">{date} | Ultimos {days} dias | {len(top_by_country)} mercados activos</div>
    </div>

    {_comparison_section(comparison)}
    {_cross_market_section(cross_market)}
    {_new_apps_section(new_apps)}
    {_top_by_country_section(top_by_country)}
    {_region_comparison_section(comparison.get('region_activity', []))}

    <div class="footer">
        Generado por Google Trends Monitor | {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
    </div>
</div>
</body>
</html>"""


def save_weekly_report(db: TrendsDatabase, days: int = 7, output_dir: str = None) -> str:
    """
    Genera y guarda el informe semanal.

    Returns:
        Ruta del archivo generado
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(output_dir, exist_ok=True)

    html = generate_weekly_report(db, days=days)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = os.path.join(output_dir, f"weekly_{date_str}.html")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.info(f"Informe semanal guardado: {filepath}")
    return filepath


# =============================================================================
# Secciones HTML
# =============================================================================

def _comparison_section(comp: dict) -> str:
    tw = comp.get('this_week', 0)
    lw = comp.get('last_week', 0)
    change = comp.get('change_pct', 0)
    tw_new = comp.get('this_week_new', 0)
    lw_new = comp.get('last_week_new', 0)
    arrow = "+" if change >= 0 else ""
    color = "#00b894" if change >= 0 else "#d63031"

    new_change = ((tw_new - lw_new) / lw_new * 100) if lw_new > 0 else 0.0
    new_arrow = "+" if new_change >= 0 else ""
    new_color = "#00b894" if new_change >= 0 else "#d63031"

    return f"""
<div class="card">
    <h2>Resumen Semanal</h2>
    <div class="comparison-grid">
        <div class="comp-group">
            <div class="comp-title">Volumen Total</div>
            <div class="comparison">
                <div class="comp-box">
                    <div class="comp-value">{tw:,}</div>
                    <div class="comp-label">Esta semana</div>
                </div>
                <div class="comp-arrow" style="color: {color}">{arrow}{change}%</div>
                <div class="comp-box">
                    <div class="comp-value">{lw:,}</div>
                    <div class="comp-label">Semana anterior</div>
                </div>
            </div>
        </div>
        <div class="comp-group">
            <div class="comp-title">Apps Nuevas</div>
            <div class="comparison">
                <div class="comp-box">
                    <div class="comp-value">{tw_new}</div>
                    <div class="comp-label">Esta semana</div>
                </div>
                <div class="comp-arrow" style="color: {new_color}">{new_arrow}{new_change:.0f}%</div>
                <div class="comp-box">
                    <div class="comp-value">{lw_new}</div>
                    <div class="comp-label">Semana anterior</div>
                </div>
            </div>
        </div>
    </div>
</div>"""


def _cross_market_section(apps: list) -> str:
    if not apps:
        return '<div class="card"><h2>Tendencias Cross-Market</h2><p class="empty">Sin tendencias globales esta semana</p></div>'

    rows = ""
    for app in apps[:20]:
        countries = ', '.join(app['countries'][:8])
        extra = f" +{len(app['countries']) - 8}" if len(app['countries']) > 8 else ""
        has_rising = any('rising' in t for t in app['data_types'])
        badge = '<span class="badge-r">Rising</span>' if has_rising else '<span class="badge-t">Top</span>'
        rows += f"""<tr>
            <td class="name">{_esc(app['title'])}</td>
            <td><span class="spread">{app['n_countries']} paises</span></td>
            <td>{app['count']}x</td>
            <td>{badge}</td>
            <td class="countries">{_esc(countries)}{extra}</td>
        </tr>"""

    extra_msg = f"<p class='more'>...y {len(apps) - 20} mas</p>" if len(apps) > 20 else ""
    return f"""
<div class="card">
    <h2>Tendencias Cross-Market <span class="count">{len(apps)}</span></h2>
    <p class="subtitle">Apps detectadas en 3 o mas paises simultaneamente</p>
    <table>
        <tr><th>App</th><th>Spread</th><th>Apariciones</th><th>Tipo</th><th>Paises</th></tr>
        {rows}
    </table>
    {extra_msg}
</div>"""


def _new_apps_section(apps: list) -> str:
    if not apps:
        return '<div class="card"><h2>Apps Nuevas de la Semana</h2><p class="empty">Sin apps nuevas</p></div>'

    # Agrupar por region
    by_region = {}
    for app in apps:
        for cc in app['countries']:
            if cc not in by_region:
                by_region[cc] = []
            by_region[cc].append(app)

    sections = ""
    for cc in sorted(by_region.keys()):
        region_apps = by_region[cc]
        country_name = config.CURRENT_REGIONS.get(cc, cc)
        app_list = ', '.join(
            _esc(a['display_name'] or a['title_normalized']) for a in region_apps[:10]
        )
        extra = f" +{len(region_apps) - 10}" if len(region_apps) > 10 else ""
        sections += f"""<div class="region-block">
            <div class="region-header">{_esc(cc)} - {_esc(country_name)} <span class="count">{len(region_apps)}</span></div>
            <div class="region-apps">{app_list}{extra}</div>
        </div>"""

    return f"""
<div class="card">
    <h2>Apps Nuevas de la Semana <span class="count">{len(apps)}</span></h2>
    <p class="subtitle">Apps detectadas por primera vez, agrupadas por mercado</p>
    {sections}
</div>"""


def _top_by_country_section(top_by_country: dict) -> str:
    if not top_by_country:
        return '<div class="card"><h2>Top Apps por Mercado</h2><p class="empty">Sin datos</p></div>'

    sections = ""
    for cc in sorted(top_by_country.keys()):
        apps = top_by_country[cc]
        country_name = config.CURRENT_REGIONS.get(cc, cc)

        rows = ""
        for i, app in enumerate(apps[:10], 1):
            has_rising = any('rising' in t for t in app['data_types'])
            badge = '<span class="badge-r">R</span>' if has_rising else '<span class="badge-t">T</span>'
            rows += f"""<tr>
                <td class="rank">#{i}</td>
                <td class="name">{_esc(app['title'])}</td>
                <td>{app['count']}x</td>
                <td>{badge}</td>
            </tr>"""

        sections += f"""<div class="country-card">
            <div class="country-header">{_esc(cc)} - {_esc(country_name)}</div>
            <table>
                <tr><th>#</th><th>App</th><th>Apariciones</th><th>Tipo</th></tr>
                {rows}
            </table>
        </div>"""

    return f"""
<div class="card">
    <h2>Top Apps por Mercado <span class="count">{len(top_by_country)} paises</span></h2>
    <p class="subtitle">Top 10 apps mas frecuentes por cada mercado</p>
    <div class="countries-grid">
        {sections}
    </div>
</div>"""


def _region_comparison_section(regions: list) -> str:
    if not regions:
        return '<div class="card"><h2>Actividad por Region</h2><p class="empty">Sin datos</p></div>'

    max_count = max(r['this_week'] for r in regions) if regions else 1
    cells = ""
    for r in regions:
        tw = r['this_week']
        lw = r['last_week']
        change = ((tw - lw) / lw * 100) if lw > 0 else 0.0
        ratio = tw / max_count if max_count > 0 else 0

        if ratio > 0.7:
            bg, fg = "#00b894", "white"
        elif ratio > 0.4:
            bg, fg = "#55efc4", "#2d3436"
        elif ratio > 0.2:
            bg, fg = "#ffeaa7", "#2d3436"
        else:
            bg, fg = "#dfe6e9", "#636e72"

        arrow = "+" if change >= 0 else ""
        cells += f'<div class="region-cell" style="background:{bg};color:{fg}"><div class="region-code">{r["country_code"]}</div><div class="region-count">{tw}</div><div class="region-change">{arrow}{change:.0f}%</div></div>'

    return f"""
<div class="card">
    <h2>Actividad por Region (semana actual vs anterior)</h2>
    <div class="region-grid">{cells}</div>
</div>"""


# =============================================================================
# CSS
# =============================================================================

def _weekly_css() -> str:
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; color: #2d3436; line-height: 1.5; }
.container { max-width: 960px; margin: 0 auto; padding: 20px; }
.header { background: linear-gradient(135deg, #e17055, #fdcb6e); color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 20px; }
.header h1 { font-size: 22px; margin-bottom: 4px; }
.header .meta { font-size: 13px; opacity: 0.85; }
.card { background: white; border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card h2 { font-size: 16px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 2px solid #f1f2f6; }
.subtitle { font-size: 12px; color: #636e72; margin-bottom: 12px; }
.count { background: #dfe6e9; color: #636e72; font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 8px 10px; background: #f1f2f6; font-weight: 600; font-size: 11px; text-transform: uppercase; color: #636e72; }
td { padding: 8px 10px; border-bottom: 1px solid #f1f2f6; }
tr:hover td { background: #f8f9fa; }
.rank { font-weight: 700; color: #0984e3; width: 32px; }
.name { font-weight: 600; }
.countries { font-size: 12px; color: #636e72; }
.spread { background: #6c5ce7; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.badge-r { background: #e17055; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.badge-t { background: #74b9ff; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; font-weight: 600; }
.comparison-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.comp-group { }
.comp-title { font-size: 13px; font-weight: 600; color: #636e72; text-transform: uppercase; margin-bottom: 8px; text-align: center; }
.comparison { display: flex; align-items: center; justify-content: center; gap: 20px; padding: 8px 0; }
.comp-box { text-align: center; }
.comp-value { font-size: 28px; font-weight: 700; color: #0984e3; }
.comp-label { font-size: 11px; color: #636e72; text-transform: uppercase; }
.comp-arrow { font-size: 20px; font-weight: 700; }
.countries-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.country-card { background: #f8f9fa; border-radius: 8px; padding: 12px; }
.country-header { font-weight: 700; font-size: 14px; margin-bottom: 8px; color: #0984e3; }
.country-card table { font-size: 12px; }
.country-card th { padding: 4px 8px; font-size: 10px; }
.country-card td { padding: 4px 8px; }
.region-block { padding: 10px 0; border-bottom: 1px solid #f1f2f6; }
.region-block:last-child { border-bottom: none; }
.region-header { font-weight: 700; font-size: 13px; color: #0984e3; margin-bottom: 4px; }
.region-apps { font-size: 12px; color: #636e72; }
.region-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 8px; }
.region-cell { padding: 10px; border-radius: 8px; text-align: center; }
.region-code { font-weight: 700; font-size: 14px; }
.region-count { font-size: 11px; opacity: 0.8; }
.region-change { font-size: 10px; font-weight: 600; }
.empty { color: #b2bec3; font-style: italic; padding: 12px 0; }
.more { color: #636e72; font-size: 12px; margin-top: 8px; }
.footer { text-align: center; color: #b2bec3; font-size: 11px; padding: 16px 0; }
"""


def _esc(text: str) -> str:
    if not text:
        return ""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


# =============================================================================
# Ejecucion directa
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Genera informe semanal por mercado")
    parser.add_argument('--days', type=int, default=7, help="Dias a consolidar (default: 7)")
    args = parser.parse_args()

    db = TrendsDatabase()
    if not db.connect():
        logger.error("No se pudo conectar a Turso. Verifica credenciales.")
        sys.exit(1)

    filepath = save_weekly_report(db, days=args.days)
    logger.info(f"Informe semanal generado: {filepath}")
    db.close()


if __name__ == "__main__":
    main()
