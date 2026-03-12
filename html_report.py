"""
Generador de informes HTML para el equipo de contenidos.

Genera un archivo HTML autocontenido (CSS inline) con secciones visuales:
- Resumen ejecutivo
- Apps nuevas
- Tendencias globales
- Top apps (con novelty y velocity)
- Heatmap de regiones
- Watchlist
- Estadísticas
"""
import os
import logging
from datetime import datetime
from typing import List

from report_generator import ContentReport, ReportItem

logger = logging.getLogger(__name__)


def generate_html_report(report: ContentReport) -> str:
    """
    Genera un informe HTML completo autocontenido.

    Args:
        report: ContentReport con datos clasificados

    Returns:
        String HTML completo
    """
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trends Report - {report.timestamp}</title>
<style>
{_css()}
</style>
</head>
<body>
<div class="container">
    {_header(report)}
    {_executive_summary(report)}
    {_new_apps_section(report)}
    {_global_trends_section(report)}
    {_top_apps_section(report)}
    {_region_heatmap(report)}
    {_watchlist_section(report)}
    {_stats_section(report)}
    {_footer()}
</div>
</body>
</html>"""


def save_html_report(report: ContentReport, output_dir: str = None) -> str:
    """
    Genera y guarda el informe HTML.

    Args:
        report: ContentReport
        output_dir: Directorio de salida (default: logs/)

    Returns:
        Ruta del archivo generado
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(output_dir, exist_ok=True)

    html = generate_html_report(report)
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    logger.info(f"Informe HTML guardado: {filepath}")
    return filepath


# =============================================================================
# Componentes HTML
# =============================================================================

def _css() -> str:
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f6fa; color: #2d3436; line-height: 1.5;
}
.container { max-width: 960px; margin: 0 auto; padding: 20px; }

/* Header */
.header {
    background: linear-gradient(135deg, #0984e3, #6c5ce7);
    color: white; padding: 24px 32px; border-radius: 12px; margin-bottom: 20px;
}
.header h1 { font-size: 22px; margin-bottom: 4px; }
.header .meta { font-size: 13px; opacity: 0.85; }

/* Cards */
.card {
    background: white; border-radius: 10px; padding: 20px 24px;
    margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.card h2 {
    font-size: 16px; margin-bottom: 12px; padding-bottom: 8px;
    border-bottom: 2px solid #f1f2f6; display: flex; align-items: center; gap: 8px;
}
.card h2 .count {
    background: #dfe6e9; color: #636e72; font-size: 12px;
    padding: 2px 8px; border-radius: 10px; font-weight: 600;
}

/* Executive summary */
.summary-list { list-style: none; }
.summary-list li {
    padding: 8px 12px; margin-bottom: 6px; background: #f8f9fa;
    border-left: 3px solid #0984e3; border-radius: 0 6px 6px 0; font-size: 14px;
}

/* Badges */
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600; text-transform: uppercase;
}
.badge-new { background: #00b894; color: white; }
.badge-resurgent { background: #fdcb6e; color: #2d3436; }
.badge-known { background: #dfe6e9; color: #636e72; }
.badge-rising { background: #e17055; color: white; }
.badge-top { background: #74b9ff; color: white; }
.badge-accel { background: #fd79a8; color: white; }
.badge-stable { background: #dfe6e9; color: #636e72; }
.badge-decay { background: #b2bec3; color: white; }
.badge-watchlist { background: #ffeaa7; color: #2d3436; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
    text-align: left; padding: 8px 10px; background: #f1f2f6;
    font-weight: 600; font-size: 11px; text-transform: uppercase;
    color: #636e72; letter-spacing: 0.5px;
}
td { padding: 8px 10px; border-bottom: 1px solid #f1f2f6; }
tr:hover td { background: #f8f9fa; }
.app-name { font-weight: 600; }
.countries { font-size: 12px; color: #636e72; }
.score { font-weight: 600; }
.score-high { color: #e17055; }
.score-med { color: #fdcb6e; }

/* Heatmap */
.heatmap { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 8px; }
.heatmap-cell {
    padding: 10px; border-radius: 8px; text-align: center; font-size: 12px;
}
.heatmap-cell .code { font-weight: 700; font-size: 14px; }
.heatmap-cell .count { font-size: 11px; opacity: 0.8; }
.heat-5 { background: #00b894; color: white; }
.heat-4 { background: #55efc4; color: #2d3436; }
.heat-3 { background: #ffeaa7; color: #2d3436; }
.heat-2 { background: #fab1a0; color: #2d3436; }
.heat-1 { background: #dfe6e9; color: #636e72; }
.heat-0 { background: #f1f2f6; color: #b2bec3; }

/* Watchlist */
.watchlist-reason { font-size: 11px; color: #d63031; font-style: italic; }

/* Stats */
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
.stat-box {
    background: #f8f9fa; border-radius: 8px; padding: 14px; text-align: center;
}
.stat-box .value { font-size: 24px; font-weight: 700; color: #0984e3; }
.stat-box .label { font-size: 11px; color: #636e72; text-transform: uppercase; }

/* Footer */
.footer { text-align: center; color: #b2bec3; font-size: 11px; padding: 16px 0; }

/* Empty state */
.empty { color: #b2bec3; font-style: italic; padding: 12px 0; }
"""


def _header(report: ContentReport) -> str:
    group_info = f" | Grupo: {report.group}" if report.group else ""
    regions = ', '.join(report.regions) if report.regions else "N/A"
    return f"""
<div class="header">
    <h1>Informe de Tendencias</h1>
    <div class="meta">{report.timestamp}{group_info} | Regiones: {regions}</div>
</div>"""


def _executive_summary(report: ContentReport) -> str:
    if not report.executive_summary:
        return ""
    items = ''.join(f'<li>{_esc(line)}</li>' for line in report.executive_summary)
    return f"""
<div class="card">
    <h2>Resumen Ejecutivo</h2>
    <ul class="summary-list">{items}</ul>
</div>"""


def _new_apps_section(report: ContentReport) -> str:
    if not report.new_apps:
        return ""
    rows = ''.join(_app_row(item, show_novelty=True) for item in report.new_apps[:15])
    return f"""
<div class="card">
    <h2>Apps Nuevas <span class="count">{len(report.new_apps)}</span></h2>
    <table>
        <tr><th>App</th><th>Tipo</th><th>Paises</th><th>Score</th><th>Estado</th></tr>
        {rows}
    </table>
</div>"""


def _global_trends_section(report: ContentReport) -> str:
    if not report.global_trends:
        return ""
    rows = ""
    for item in report.global_trends[:10]:
        countries = ', '.join(list(set(item.countries)))
        vel_badge = _velocity_badge(item.velocity)
        rows += f"""<tr>
            <td class="app-name">{_esc(item.name)}</td>
            <td>{item.spread_score} paises</td>
            <td class="countries">{_esc(countries)}</td>
            <td class="score">{_esc(str(item.max_value))}</td>
            <td>{vel_badge}</td>
        </tr>"""
    return f"""
<div class="card">
    <h2>Tendencias Globales <span class="count">{len(report.global_trends)}</span></h2>
    <table>
        <tr><th>App</th><th>Spread</th><th>Paises</th><th>Score</th><th>Velocidad</th></tr>
        {rows}
    </table>
</div>"""


def _top_apps_section(report: ContentReport) -> str:
    if not report.potential_apps:
        return '<div class="card"><p class="empty">No se detectaron apps en esta ejecucion</p></div>'
    rows = ''.join(_app_row(item, show_novelty=True, show_velocity=True) for item in report.potential_apps[:30])
    return f"""
<div class="card">
    <h2>Todas las Apps <span class="count">{len(report.potential_apps)}</span></h2>
    <table>
        <tr><th>App</th><th>Tipo</th><th>Paises</th><th>Score</th><th>Estado</th><th>Velocidad</th></tr>
        {rows}
    </table>
</div>"""


def _region_heatmap(report: ContentReport) -> str:
    if not report.potential_apps:
        return ""

    # Contar apariciones por país
    country_counts = {}
    for item in report.potential_apps:
        for country in set(item.countries):
            country_counts[country] = country_counts.get(country, 0) + 1

    if not country_counts:
        return ""

    max_count = max(country_counts.values()) if country_counts else 1

    cells = ""
    for country, count in sorted(country_counts.items(), key=lambda x: -x[1]):
        # Heat level 0-5
        ratio = count / max_count
        if ratio > 0.8:
            level = 5
        elif ratio > 0.6:
            level = 4
        elif ratio > 0.4:
            level = 3
        elif ratio > 0.2:
            level = 2
        elif count > 0:
            level = 1
        else:
            level = 0
        cells += f'<div class="heatmap-cell heat-{level}"><div class="code">{_esc(country)}</div><div class="count">{count} apps</div></div>'

    return f"""
<div class="card">
    <h2>Actividad por Region</h2>
    <div class="heatmap">{cells}</div>
</div>"""


def _watchlist_section(report: ContentReport) -> str:
    if not report.watchlist_apps:
        return ""
    rows = ""
    for item in report.watchlist_apps:
        tipo_badge = '<span class="badge badge-rising">Rising</span>' if item.is_rising else '<span class="badge badge-top">Top</span>'
        countries = ', '.join(list(set(item.countries))[:3])
        rows += f"""<tr>
            <td class="app-name">{_esc(item.name)}</td>
            <td>{tipo_badge}</td>
            <td class="countries">{_esc(countries)}</td>
            <td class="score">{_esc(str(item.max_value))}</td>
            <td><span class="watchlist-reason">{_esc(item.review_reason)}</span></td>
        </tr>"""
    return f"""
<div class="card">
    <h2>Requieren Revision <span class="count">{len(report.watchlist_apps)}</span></h2>
    <table>
        <tr><th>App</th><th>Tipo</th><th>Paises</th><th>Score</th><th>Razon</th></tr>
        {rows}
    </table>
</div>"""


def _stats_section(report: ContentReport) -> str:
    new_count = len(report.new_apps)
    global_count = len(report.global_trends)
    accel_count = len(report.accelerating)
    return f"""
<div class="card">
    <h2>Estadisticas</h2>
    <div class="stats-grid">
        <div class="stat-box"><div class="value">{report.total_items_processed}</div><div class="label">Items procesados</div></div>
        <div class="stat-box"><div class="value">{report.total_unique_terms}</div><div class="label">Terminos unicos</div></div>
        <div class="stat-box"><div class="value">{len(report.potential_apps)}</div><div class="label">Apps detectadas</div></div>
        <div class="stat-box"><div class="value">{new_count}</div><div class="label">Apps nuevas</div></div>
        <div class="stat-box"><div class="value">{global_count}</div><div class="label">Tend. globales</div></div>
        <div class="stat-box"><div class="value">{accel_count}</div><div class="label">Acelerando</div></div>
        <div class="stat-box"><div class="value">{len(report.watchlist_apps)}</div><div class="label">Watchlist</div></div>
        <div class="stat-box"><div class="value">{len(report.regions)}</div><div class="label">Regiones</div></div>
    </div>
</div>"""


def _footer() -> str:
    return f'<div class="footer">Generado automaticamente por Google Trends Monitor | {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</div>'


# =============================================================================
# Helpers
# =============================================================================

def _app_row(item: ReportItem, show_novelty: bool = False, show_velocity: bool = False) -> str:
    """Genera una fila de tabla para una app."""
    tipo_badge = '<span class="badge badge-rising">Rising</span>' if item.is_rising else '<span class="badge badge-top">Top</span>'

    countries_unique = list(set(item.countries))
    if len(countries_unique) > 4:
        countries_str = ', '.join(countries_unique[:4]) + f'... (+{len(countries_unique) - 4})'
    else:
        countries_str = ', '.join(countries_unique)

    # Score styling
    val_num, _ = _parse_value_simple(item.max_value)
    score_class = "score-high" if val_num >= 500 else ("score-med" if val_num >= 100 else "")
    score_display = "Breakout" if 'breakout' in str(item.max_value).lower() else str(item.max_value)

    novelty_col = ""
    if show_novelty:
        novelty_col = f"<td>{_novelty_badge(item.novelty)}</td>"

    velocity_col = ""
    if show_velocity:
        velocity_col = f"<td>{_velocity_badge(item.velocity)}</td>"

    return f"""<tr>
        <td class="app-name">{_esc(item.name)}</td>
        <td>{tipo_badge}</td>
        <td class="countries">{_esc(countries_str)}</td>
        <td class="score {score_class}">{_esc(score_display)}</td>
        {novelty_col}
        {velocity_col}
    </tr>"""


def _novelty_badge(novelty: str) -> str:
    if novelty == 'nueva':
        return '<span class="badge badge-new">Nueva</span>'
    elif novelty == 'resurgente':
        return '<span class="badge badge-resurgent">Resurgente</span>'
    elif novelty == 'conocida':
        return '<span class="badge badge-known">Conocida</span>'
    return ''


def _velocity_badge(velocity: str) -> str:
    if velocity == 'acelerando':
        return '<span class="badge badge-accel">Acelerando</span>'
    elif velocity == 'estable':
        return '<span class="badge badge-stable">Estable</span>'
    elif velocity == 'decayendo':
        return '<span class="badge badge-decay">Decayendo</span>'
    return ''


def _parse_value_simple(value: str) -> tuple:
    """Parse simple del valor para styling."""
    import re
    if not value:
        return (0, False)
    value_str = str(value).strip()
    if 'breakout' in value_str.lower():
        return (9999, True)
    numeric = re.sub(r'[^\d]', '', value_str)
    try:
        return (int(numeric) if numeric else 0, value_str.startswith('+'))
    except ValueError:
        return (0, False)


def _esc(text: str) -> str:
    """Escapa HTML."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))
