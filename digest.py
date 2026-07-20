"""
Generador de digest diario.

Consolida todos los datos del día (de las 10 runs) en un informe
HTML/Markdown/Slack que muestra: top apps, apps nuevas, actividad por
región, y comparación vs día anterior.

Cron: 07:00 UTC (~9h Madrid) — consolida el día UTC ANTERIOR completo,
ya cerrado a esa hora. Sin --date, el default es "ayer", no "hoy".

Uso:
    python digest.py                      # Genera digest de AYER (default)
    python digest.py --date 2026-03-10    # Genera digest de fecha específica
    python digest.py --preview-slack      # Preview de Slack sin enviar nada
"""
import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import config
import render_utils
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

    # Cada query se protege individualmente: Turso puede aceptar la conexión
    # pero rechazar las lecturas (p.ej. "reads are blocked" por cuota agotada).
    # El digest NUNCA debe tumbar el run: sin datos → digest degradado, pero
    # el commit de keepalive se produce igualmente.
    # Sin conexión las queries devuelven vacío sin lanzar excepción → el modo
    # degradado debe activarse ya desde aquí.
    degraded = not db.is_connected

    def _safe(fetch, default):
        nonlocal degraded
        try:
            return fetch()
        except Exception as e:
            logger.warning(f"Query de digest falló (modo degradado): {e}")
            degraded = True
            return default

    data = {
        'date': date,
        # Límite compartido por HTML/Markdown/Slack. 25 en vez de 18 (el cap
        # de Slack) para tener margen: los items casino se separan después
        # y no deben restar cupo a las apps normales mostradas.
        'top_apps': _safe(lambda: db.get_today_top_apps(limit=25, date=date), []),
        'new_apps': _safe(lambda: db.get_today_new_apps(date=date), []),
        'region_activity': _safe(lambda: db.get_region_activity(date=date), []),
        'comparison': _safe(lambda: db.get_daily_comparison(date=date),
                            {'today': 0, 'yesterday': 0, 'change_pct': 0.0}),
        'history_7d': _safe(lambda: db.get_volume_last_n_days(7), []),
    }
    data['degraded'] = degraded
    return data


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
    <h2>Top {len(apps)} Apps del Dia</h2>
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
    ]

    if data.get('degraded'):
        lines += [
            "> ⚠️ **Modo degradado**: Turso no estaba disponible al generar este "
            "digest (cuota agotada o servicio caído). Los datos del día están en "
            "Google Sheets; este informe se emite igualmente para mantener vivo "
            "el workflow.",
            "",
        ]

    lines += [
        "## Volumen del Dia",
        "",
        f"| Hoy | Ayer | Cambio |",
        f"|-----|------|--------|",
        f"| {today} | {yesterday} | {sign}{change}% |",
        "",
        f"## Top {len(top_apps)} Apps del Dia" if top_apps else "## Top Apps del Dia",
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
# Digest para Slack (Block Kit) — canal privado, NO el repo público
# =============================================================================

# Repo privado gemelo que archiva el digest completo (con nombres de apps).
# Nunca el repo público — ver Push digest to private archive en el workflow.
PRIVATE_ARCHIVE_URL = "https://github.com/Kirkizillo/gtrends-archive-private/blob/main/reports/latest.md"

# Cabe de sobra dentro del límite de 3000 caracteres por section de Slack
# (~18 líneas de ~70 chars y ~15 de ~40 chars quedan muy por debajo).
TOP_APPS_CAP = 18
NEW_APPS_CAP = 15
CASINO_CAP = 5  # sección demotada a propósito: se mantiene compacta
REGIONS_CAP = 5


def _slack_esc(text: str) -> str:
    """Escapa los caracteres especiales de Slack mrkdwn (&, <, >)."""
    if not text:
        return ""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _slack_tldr(data: dict, app_items: list, casino_items: list) -> str:
    """Una frase con el hallazgo más relevante del día."""
    if data.get('degraded'):
        return (":warning: *Modo degradado* — Turso no disponible hoy. "
                "Los datos siguen llegando a Google Sheets con normalidad.")

    new_apps = data.get('new_apps') or []
    if app_items:
        top = app_items[0]
        countries = ", ".join(render_utils.flag_or_code(c) for c in top['countries'][:3])
        extra = f" (+{len(top['countries']) - 3} más)" if len(top['countries']) > 3 else ""
        return (f":fire: *{_slack_esc(top['title'])}* lidera hoy con {top['count']}x "
                f"en {countries}{extra} — {len(new_apps)} apps nuevas detectadas.")
    if casino_items:
        return (f":slot_machine: Sin apps destacadas hoy, pero {len(casino_items)} "
                f"términos de casino/apuestas en alta actividad.")
    return "Sin actividad destacada hoy."


def build_slack_digest_blocks(data: dict, history_7d: list = None,
                               full_report_url: str = None) -> list:
    """
    Construye el mensaje de Slack (Block Kit) para el digest diario.

    A diferencia del Markdown/HTML (pensados para archivo/histórico), este
    formato prioriza legibilidad para alguien sin acceso a Sheets: TL;DR
    arriba, sparkline de 7 días, banderas por país, sección casino demotada.

    Args:
        data: Dict de fetch_digest_data()
        history_7d: Lista de {date, count} de db.get_volume_last_n_days(7).
                    Si es None, se usa data['history_7d'] (fetch_digest_data
                    ya la incluye); sin ninguna de las dos se omite el sparkline.
        full_report_url: URL del informe completo en el repo privado
                         (opcional; sin ella se omite el enlace)

    Returns:
        Lista de blocks de Slack Block Kit
    """
    if history_7d is None:
        history_7d = data.get('history_7d')
    comp = data.get('comparison') or {'today': 0, 'yesterday': 0, 'change_pct': 0.0}
    top_apps = data.get('top_apps') or []
    new_apps = data.get('new_apps') or []
    regions = data.get('region_activity') or []
    date = data.get('date', '?')

    # Reutiliza la misma clasificación casino que los informes por-run
    # (report_generator.CASINO_PATTERNS) para no duplicar la regex ni
    # divergir en qué cuenta como casino/apuestas.
    from report_generator import CASINO_PATTERNS
    app_items, casino_items = [], []
    for item in top_apps:
        is_casino = CASINO_PATTERNS.search(item['title'].lower())
        (casino_items if is_casino else app_items).append(item)

    blocks = [
        {"type": "header", "text": {"type": "plain_text",
         "text": f"📊 Digest Trends — {date}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": _slack_tldr(data, app_items, casino_items)}},
        {"type": "divider"},
    ]

    if not data.get('degraded'):
        # Volumen + sparkline de 7 días
        arrow = render_utils.trend_arrow(comp['change_pct'])
        vol_lines = [
            f"*Volumen del día:* {comp['today']} registros {arrow} "
            f"({comp['change_pct']:+.1f}% vs ayer, {comp['yesterday']} ayer)"
        ]
        if history_7d:
            values = [d['count'] for d in history_7d]
            spark = render_utils.sparkline(values)
            vol_lines.append(f"`{spark}` _(últimos {len(values)} días)_")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": "\n".join(vol_lines)}})

        # Top apps (banderas, marcador rising/top, sin casino)
        if app_items:
            lines = ["*🔥 Top apps de hoy:*"]
            for item in app_items[:TOP_APPS_CAP]:
                countries = ", ".join(render_utils.flag_or_code(c) for c in item['countries'][:3])
                extra = f" +{len(item['countries']) - 3}" if len(item['countries']) > 3 else ""
                url = item.get('link', '')
                name = _slack_esc(item['title'])
                name_fmt = f"<{url}|{name}>" if url else name
                marker = "🔥" if any('rising' in dt for dt in item.get('data_types') or []) else "📈"
                lines.append(f"• {marker} *{name_fmt}* — {item['count']}x ({countries}{extra})")
            if len(app_items) > TOP_APPS_CAP:
                lines.append(f"_+{len(app_items) - TOP_APPS_CAP} más en el informe completo_")
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
        else:
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                           "text": "_Sin apps detectadas hoy._"}})

        # Apps nuevas
        if new_apps:
            lines = [f"*🆕 Apps nuevas hoy ({len(new_apps)}):*"]
            for item in new_apps[:NEW_APPS_CAP]:
                countries = ", ".join(render_utils.flag_or_code(c) for c in (item.get('countries') or [])[:3])
                lines.append(f"• {_slack_esc(item['display_name'])} ({countries})")
            if len(new_apps) > NEW_APPS_CAP:
                lines.append(f"_+{len(new_apps) - NEW_APPS_CAP} más_")
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})

        # Regiones más activas (una línea compacta como contexto)
        if regions:
            top_regions = regions[:REGIONS_CAP]
            region_line = " · ".join(
                f"{render_utils.flag_or_code(r['country_code'])} {r['count']}" for r in top_regions
            )
            blocks.append({"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"*Regiones más activas:* {region_line}"}
            ]})

        # Casino/Betting — demotado a propósito: divisor + sección aparte al
        # final, capada corta (no forma parte del pedido de "más nombres",
        # que aplica solo a apps normales/nuevas).
        if casino_items:
            blocks.append({"type": "divider"})
            lines = [f"*🎰 Casino / Betting ({len(casino_items)}) — informativo, no editorial:*"]
            for item in casino_items[:CASINO_CAP]:
                countries = ", ".join(render_utils.flag_or_code(c) for c in item['countries'][:2])
                lines.append(f"• {_slack_esc(item['title'])} — {item['count']}x ({countries})")
            if len(casino_items) > CASINO_CAP:
                lines.append(f"_+{len(casino_items) - CASINO_CAP} más_")
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})

    blocks.append({"type": "divider"})
    footer = f"Digest generado {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    if full_report_url:
        footer += f" · <{full_report_url}|Ver informe completo>"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})

    return blocks


# =============================================================================
# Dashboard en README.md (bloque entre marcadores, actúa como keepalive:
# el commit diario evita que GitHub desactive el workflow por inactividad)
# =============================================================================

DASHBOARD_START = "<!-- DASHBOARD:START -->"
DASHBOARD_END = "<!-- DASHBOARD:END -->"


def update_readme_dashboard(data: dict, readme_path: str = None) -> bool:
    """
    Reescribe el bloque de estado del README.md entre los marcadores
    DASHBOARD:START y DASHBOARD:END.

    IMPORTANTE: este repo es PÚBLICO. El bloque debe mostrar solo estado
    operativo (última ejecución, salud) — NUNCA nombres de apps, volúmenes
    ni ningún dato de negocio. El digest completo va al canal privado de
    Slack y al repo privado gemelo (gtrends-archive-private); nunca aquí.
    El propio commit de este bloque sigue actuando como keepalive.

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

    status_line = (
        "⚠️ Modo degradado (Turso no disponible)" if data.get('degraded')
        else "✅ Operativo"
    )

    block = f"""{DASHBOARD_START}
## Estado

**{status_line}** — última ejecución: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

📬 Los informes detallados se envían al equipo por Slack (canal privado).
{DASHBOARD_END}"""

    start_idx = content.index(DASHBOARD_START)
    end_idx = content.index(DASHBOARD_END) + len(DASHBOARD_END)
    new_content = content[:start_idx] + block + content[end_idx:]

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    logger.info("Estado del README.md actualizado (neutro, sin datos de negocio)")
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


# =============================================================================
# Reevaluación mensual de tiers de frecuencia de escaneo
# =============================================================================

def compute_tier(rows_day: float, thresholds: dict = None) -> str:
    """
    Asigna tier según filas/día:
      high   → >= high_min_rows_day (default 15)
      medium → >= medium_min_rows_day (default 4)
      low    → resto
    """
    if thresholds is None:
        thresholds = getattr(config, 'TIER_THRESHOLDS',
                             {"high_min_rows_day": 15, "medium_min_rows_day": 4})
    if rows_day >= thresholds.get("high_min_rows_day", 15):
        return "high"
    if rows_day >= thresholds.get("medium_min_rows_day", 4):
        return "medium"
    return "low"


def retier_countries(db: TrendsDatabase, tiers_path: str = None) -> list:
    """
    Reevalúa el tier de cada país de config.CURRENT_REGIONS con el volumen
    real de los últimos 30 días en Turso y reescribe country_tiers.json.

    Una sola query agregada (get_country_volumes_30d); países sin filas
    cuentan como 0 → low.

    Args:
        db: TrendsDatabase conectada
        tiers_path: Ruta al JSON de tiers (default: junto a este script)

    Returns:
        Lista de cambios [(country, old_tier, new_tier, rows_day)]
    """
    if tiers_path is None:
        tiers_path = os.path.join(os.path.dirname(__file__),
                                  getattr(config, 'TIERS_FILE', 'country_tiers.json'))

    thresholds = getattr(config, 'TIER_THRESHOLDS',
                         {"high_min_rows_day": 15, "medium_min_rows_day": 4})

    volumes = db.get_country_volumes_30d()

    # Tiers actuales (para calcular cambios); fichero ausente/corrupto →
    # se asume 'high' (el mismo fail-safe que should_scan_country)
    old_tiers = {}
    try:
        with open(tiers_path, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        if isinstance(old_data, dict):
            old_tiers = old_data.get('tiers', {}) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        logger.warning(f"No se pudo leer {tiers_path} — se asume tier 'high' previo")

    changes = []
    new_tiers = {}
    stats = {}
    for geo in config.CURRENT_REGIONS:
        rows_30d = int(volumes.get(geo, 0))
        rows_day_raw = rows_30d / 30.0
        tier = compute_tier(rows_day_raw, thresholds)
        rows_day = round(rows_day_raw, 1)
        new_tiers[geo] = tier
        stats[geo] = {"rows_30d": rows_30d, "rows_day": rows_day}
        old_tier = old_tiers.get(geo, 'high')
        if old_tier != tier:
            changes.append((geo, old_tier, tier, rows_day))

    payload = {
        "updated": datetime.utcnow().strftime("%Y-%m-%d"),
        "source": "reevaluación mensual desde Turso (filas 30d, sin trending_rss)",
        "thresholds": thresholds,
        "tiers": new_tiers,
        "stats": stats,
    }
    with open(tiers_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    logger.info(f"Tiers reevaluados: {len(changes)} cambios — {tiers_path} actualizado")
    return changes


def format_retier_section(changes: list) -> str:
    """
    Sección Markdown '## Cambios de frecuencia de escaneo' para el digest.

    Args:
        changes: Lista de retier_countries() (puede ser vacía)

    Returns:
        String Markdown (empieza y termina con salto de línea)
    """
    lines = ["", "## Cambios de frecuencia de escaneo", ""]
    if changes:
        lines.append("| Pais | Tier anterior | Tier nuevo | Filas/dia (30d) |")
        lines.append("|------|---------------|------------|-----------------|")
        for geo, old_tier, new_tier, rows_day in changes:
            lines.append(f"| {geo} | {old_tier} | {new_tier} | {rows_day} |")
    else:
        lines.append("Sin cambios de tier este mes.")
    lines.append("")
    return "\n".join(lines)


def _mock_digest_data(date: str) -> dict:
    """
    Dataset de ejemplo (basado en patrones reales observados en producción,
    jul-2026) para previsualizar el digest de Slack sin depender de Turso.
    Ejercita todas las secciones: top apps, nuevas, casino, regiones, sparkline.
    """
    return {
        'date': date,
        'degraded': False,
        'comparison': {'today': 878, 'yesterday': 761, 'change_pct': 15.4},
        'top_apps': [
            {'title': 'minecraft', 'count': 13, 'countries': ['WW', 'IN', 'US'],
             'data_types': ['queries_rising'], 'link': 'https://trends.google.com/trends/explore?q=minecraft&geo=WW'},
            {'title': 'instagram download apk', 'count': 11, 'countries': ['IN', 'BR', 'ID'],
             'data_types': ['queries_top'], 'link': 'https://trends.google.com/trends/explore?q=instagram+download+apk&geo=IN'},
            {'title': 'youtube download apk', 'count': 9, 'countries': ['WW', 'IN', 'BR'],
             'data_types': ['queries_top'], 'link': 'https://trends.google.com/trends/explore?q=youtube+download+apk&geo=WW'},
            {'title': 'capcut apk download', 'count': 9, 'countries': ['WW', 'IN', 'US'],
             'data_types': ['queries_rising'], 'link': 'https://trends.google.com/trends/explore?q=capcut+apk+download&geo=IN'},
            {'title': 'whatsapp download', 'count': 8, 'countries': ['WW', 'IN', 'US'],
             'data_types': ['queries_top'], 'link': 'https://trends.google.com/trends/explore?q=whatsapp+download&geo=WW'},
            {'title': 'roblox apk indir', 'count': 6, 'countries': ['TR'],
             'data_types': ['queries_rising'], 'link': 'https://trends.google.com/trends/explore?q=roblox+apk+indir&geo=TR'},
            {'title': '789 jackpots apk', 'count': 5, 'countries': ['IN'],
             'data_types': ['queries_rising'], 'link': ''},
            {'title': 'fire kirin xyz apk', 'count': 4, 'countries': ['US'],
             'data_types': ['queries_rising'], 'link': ''},
            {'title': 'winzo app download', 'count': 3, 'countries': ['IN'],
             'data_types': ['queries_rising'], 'link': ''},
        ],
        'new_apps': [
            {'display_name': 'Alight Motion Pro', 'countries': ['ID']},
            {'display_name': 'Mobile Legends Bang Bang', 'countries': ['PH']},
            {'display_name': 'GBWhatsApp APK', 'countries': ['NG']},
            {'display_name': 'Pinduoduo', 'countries': ['NG']},
        ],
        'region_activity': [
            {'country_code': 'IN', 'count': 145}, {'country_code': 'PH', 'count': 98},
            {'country_code': 'BR', 'count': 87}, {'country_code': 'US', 'count': 76},
            {'country_code': 'TR', 'count': 54}, {'country_code': 'ID', 'count': 41},
        ],
        'history_7d': [
            {'date': '2026-07-14', 'count': 720}, {'date': '2026-07-15', 'count': 878},
            {'date': '2026-07-16', 'count': 0}, {'date': '2026-07-17', 'count': 0},
            {'date': '2026-07-18', 'count': 0}, {'date': '2026-07-19', 'count': 0},
            {'date': '2026-07-20', 'count': 0},
        ],
    }


def preview_slack_digest(date_str: str = None, output_path: str = None) -> str:
    """
    Genera los blocks del digest de Slack SIN enviar nada y SIN tocar git,
    para revisar el diseño antes de crear el webhook real.

    Intenta usar datos reales de Turso si está disponible; si no (como
    durante el bloqueo de cuota de jul-2026), usa un dataset de ejemplo
    representativo para poder revisar el diseño completo igualmente.

    Returns:
        Ruta del archivo JSON escrito (pegable en app.slack.com/block-builder)
    """
    # Mismo default que main(): "ayer", coherente con el cron a las 07:00 UTC
    date_str = date_str or (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    output_path = output_path or os.path.join(os.path.dirname(__file__), "logs", "slack_blocks_preview.json")

    db = TrendsDatabase()
    connected = db.connect(remote_only=True)
    data = fetch_digest_data(db, date=date_str) if connected else None
    if connected:
        db.close()

    used_mock = not data or data.get('degraded') or not data.get('top_apps')
    if used_mock:
        logger.info("Turso no disponible o sin datos del día — usando dataset de ejemplo para la previsualización")
        data = _mock_digest_data(date_str)

    blocks = build_slack_digest_blocks(
        data, full_report_url=PRIVATE_ARCHIVE_URL
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"blocks": blocks}, f, ensure_ascii=False, indent=2)

    logger.info(f"Preview de Slack generado: {output_path}")
    logger.info("Datos: %s", "EJEMPLO (mock)" if used_mock else "reales de Turso")
    logger.info("Pégalo en https://app.slack.com/block-builder para ver el render exacto de Slack")
    return output_path


def notify_slack_success(data: dict, full_report_url: str = None) -> bool:
    """
    Envía el digest completo (Block Kit) al canal privado de Slack.
    Solo actúa si SLACK_WEBHOOK_URL está definida. Nunca lanza excepciones.

    IMPORTANTE: full_report_url debe apuntar al repo PRIVADO gemelo, nunca
    al repo público — ese fue precisamente el problema de la versión anterior
    (enlazaba de vuelta a github.com/Kirkizillo/gtrends, público).
    """
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        logger.info("SLACK_WEBHOOK_URL no definida, se omite notificación de éxito")
        return False

    blocks = build_slack_digest_blocks(data, full_report_url=full_report_url)
    # "text" es el fallback recomendado por Slack para notificaciones/lectores
    # de pantalla, y lo que se muestra si algún bloque no renderiza.
    comp = data.get('comparison') or {}
    fallback_text = (
        f"Digest degradado {data.get('date')}" if data.get('degraded')
        else f"Digest {data.get('date')} — {comp.get('today', 0)} registros "
             f"({comp.get('change_pct', 0.0):+.1f}% vs ayer)"
    )
    try:
        import requests
        resp = requests.post(webhook, json={"blocks": blocks, "text": fallback_text}, timeout=15)
        ok = resp.status_code < 300
        if not ok:
            logger.warning(f"Slack devolvió {resp.status_code}: {resp.text[:200]}")
        return ok
    except Exception as e:
        logger.warning(f"No se pudo notificar a Slack: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Genera digest diario consolidado")
    parser.add_argument('--date', type=str, help="Fecha YYYY-MM-DD (default: hoy)")
    parser.add_argument('--weekly', action='store_true', help="Forzar generacion de informe semanal")
    parser.add_argument('--retier', action='store_true', help="Forzar reevaluacion mensual de tiers de escaneo")
    parser.add_argument('--preview-slack', action='store_true',
                        help="Genera logs/slack_blocks_preview.json sin enviar nada ni tocar git")
    args = parser.parse_args()

    if args.preview_slack:
        preview_slack_digest(date_str=args.date)
        return

    # Conectar a Turso en modo remoto: sin replica local ni sync completo.
    # El embedded replica descargaba la BD entera (~107k filas) y agotaba
    # la cuota mensual del plan free de Turso hacia el día 9-10 del mes.
    db = TrendsDatabase()
    connected = db.connect(remote_only=True)
    if not connected:
        # NO abortamos: un Turso caído/bloqueado no debe tumbar el digest.
        # Se genera un digest degradado y el commit de keepalive se produce
        # igualmente (si abortáramos, el repo dejaría de tener actividad y
        # GitHub desactivaría el workflow a los 60 días — lo que mató el
        # proyecto en mayo de 2026).
        logger.error("Turso no disponible — generando digest degradado sin datos")

    # Retención: acota el tamaño de la BD y el egress de sync de las replicas
    if connected:
        db.purge_old_trends(days=config.TRENDS_RETENTION_DAYS)
        size_mb = db.get_db_size_mb()
        if size_mb > 0:
            logger.info(f"Tamaño actual de la BD Turso: {size_mb} MB")
            if size_mb > 400:
                logger.warning(
                    f"CAPACIDAD TURSO: la BD ocupa {size_mb} MB — revisar el "
                    f"plan free y considerar bajar TRENDS_RETENTION_DAYS "
                    f"(actual: {config.TRENDS_RETENTION_DAYS})"
                )

    # Obtener datos una vez, renderizar dos veces (HTML + Markdown)
    logger.info("Generando digest diario...")
    # El cron corre a las 07:00 UTC (~9h Madrid) y consolida el día UTC
    # ANTERIOR completo (ya cerrado a esa hora) — briefing tipo "periódico
    # matutino", no el día en curso (que a las 07:00 UTC apenas ha arrancado).
    date_str = args.date or (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    data = fetch_digest_data(db, date=date_str)
    html = generate_digest_html(data)
    markdown = generate_digest_markdown(data)

    # Reevaluación mensual de tiers: día 1 de cada mes o --retier.
    # Mismo patrón que el informe semanal: solo con Turso conectado y sin
    # modo degradado. Cualquier fallo conserva el country_tiers.json anterior.
    is_first_of_month = datetime.utcnow().day == 1
    if (is_first_of_month or args.retier) and connected and not data.get('degraded'):
        logger.info("Reevaluando tiers de frecuencia de escaneo (mensual)...")
        try:
            tier_changes = retier_countries(db)
            section = format_retier_section(tier_changes)
            # Insertar la sección antes del pie del digest (si existe)
            footer = "\n---\nGenerado por Google Trends Monitor\n"
            if markdown.endswith(footer):
                markdown = markdown[:-len(footer)] + section + footer
            else:
                markdown += section
        except Exception as e:
            logger.warning(f"Reevaluación de tiers falló — se conserva el JSON anterior: {e}")
    elif is_first_of_month or args.retier:
        logger.warning("Reevaluación de tiers omitida: Turso no disponible o modo degradado")

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

    # Actualizar dashboard del README y limpiar reports antiguos.
    # En modo degradado NO se pisa el dashboard: conserva los últimos
    # datos buenos en vez de mostrar ceros.
    if not data.get('degraded'):
        update_readme_dashboard(data)
    else:
        logger.warning("Modo degradado: se conserva el dashboard anterior del README")
    prune_old_reports(reports_dir, days=90)

    # Notificación de éxito (opcional, requiere SLACK_WEBHOOK_URL)
    notify_slack_success(data, full_report_url=PRIVATE_ARCHIVE_URL)

    # Informe semanal: se genera cuando el DÍA REPORTADO (date_str) es domingo
    # o con --weekly. Con el digest corriendo a las 07:00 UTC del día
    # siguiente, "hoy" (el día del job) ya es lunes cuando date_str es el
    # domingo que se está consolidando.
    is_sunday = datetime.strptime(date_str, "%Y-%m-%d").weekday() == 6
    if (is_sunday or args.weekly) and connected and not data.get('degraded'):
        logger.info("Generando informe semanal...")
        try:
            from weekly_report import save_weekly_report
            weekly_path = save_weekly_report(db, days=7, output_dir=output_dir)
            logger.info(f"Informe semanal guardado: {weekly_path}")
        except Exception as e:
            logger.error(f"Error generando informe semanal: {e}")
    elif is_sunday or args.weekly:
        logger.warning("Informe semanal omitido: Turso no disponible")

    if connected:
        db.close()


if __name__ == "__main__":
    main()
