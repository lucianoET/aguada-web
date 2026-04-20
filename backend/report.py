# backend/report.py
"""Geração de relatório HTML + PDF com WeasyPrint."""
from __future__ import annotations
import datetime
from html import escape
import aiosqlite
from .db import (
    get_all_states,
    get_readings_for_date,
    get_manual_hydrometer_summary_for_date,
    get_pump_states_for_date,
    get_valve_states_for_date,
    get_report_daily_data,
    get_report_notes,
)
from .calc import calc_consumption_events


def _to_tons(volume_l: float | int | None) -> float:
    if volume_l is None:
        return 0.0
    return float(volume_l) / 1000.0


def _fmt_ton(v: float | int) -> str:
    return str(int(round(float(v))))


def _fmt_signed(v: float | int) -> str:
    n = int(round(float(v)))
    if n > 0:
        return f"+{n}"
    return str(n)


def _fmt_decimal(v: float | int | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{float(v):.{decimals}f}".replace('.', ',')


def _saved_volume_total(values: dict | None) -> float | None:
    values = values or {}
    keys = ("CON", "CAV", "CB3", "CIE1", "CIE2", "CBIF")
    numeric_values = [values.get(key) for key in keys if values.get(key) is not None]
    if not numeric_values:
        return None
    return sum(numeric_values)


def _fmt_date_br(date_str: str) -> str:
    try:
        return datetime.date.fromisoformat(date_str).strftime("%d/%m/%Y")
    except ValueError:
        return date_str


def _signature_block_html(electrician: str, ose: str) -> str:
    electrician_value = escape((electrician or "").strip())
    ose_value = escape((ose or "").strip())
    return f"""
    <section class='section signature-section'>
      <table class='signature-grid'>
        <tr>
          <td>
            <div class='signature-line'></div>
            <div class='signature-name'>{electrician_value or '&nbsp;'}</div>
            <div class='signature-role'>Eletricista</div>
          </td>
          <td>
            <div class='signature-line'></div>
            <div class='signature-name'>{ose_value or '&nbsp;'}</div>
            <div class='signature-role'>OSE</div>
          </td>
        </tr>
      </table>
    </section>
    """


def _two_column_section(left_title: str, left_table: str, right_title: str, right_table: str) -> str:
    return f"""
    <section class='section'>
      <table class='dual-grid'>
        <tr>
          <td>
            <h2>{left_title}</h2>
            {left_table}
          </td>
          <td>
            <h2>{right_title}</h2>
            {right_table}
          </td>
        </tr>
      </table>
    </section>
    """


def _pdf_styles() -> str:
    return """
    @page { size: A4 portrait; margin: 15mm; }
    html { font-size: 11px; }
    body {
      margin: 0;
      color: #111827;
      font-family: Calibri, Arial, sans-serif;
      font-size: 11px;
      line-height: 1.35;
    }
    .report-shell {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #111827;
      padding: 10mm 8mm 9mm;
    }
    .report-header {
      text-align: center;
      margin-bottom: 18px;
      padding-bottom: 8px;
      border-bottom: 1px solid #111827;
    }
    h1 {
      font-size: 20px;
      line-height: 1.15;
      margin: 0 0 6px 0;
      font-weight: 700;
      text-transform: uppercase;
    }
    .subtitle {
      margin: 0;
      color: #374151;
      font-size: 11px;
      font-weight: 600;
    }
    .section {
      margin-top: 12px;
      page-break-inside: avoid;
    }
    h2 {
      font-size: 12px;
      margin: 0 0 6px 0;
      page-break-after: avoid;
      text-transform: uppercase;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-top: 4px;
    }
    thead { display: table-header-group; }
    tr { page-break-inside: avoid; }
    th, td {
      border: 1px solid #d1d5db;
      padding: 5px 7px;
      vertical-align: middle;
      word-wrap: break-word;
    }
    th {
      background: #f3f4f6;
      text-align: left;
      font-size: 11px;
      font-weight: 700;
    }
    td.num, th.num {
      text-align: right;
      white-space: nowrap;
    }
    td.center, th.center {
      text-align: center;
    }
    .muted-empty {
      text-align: center;
      color: #6b7280;
    }
    .dual-grid {
      border-collapse: separate;
      border-spacing: 8px 0;
      margin-top: 0;
    }
    .dual-grid td {
      width: 50%;
      border: none;
      padding: 0;
      vertical-align: top;
    }
    ul.notes {
      margin: 6px 0 0 18px;
      padding: 0;
    }
    ul.notes li {
      margin: 3px 0;
    }
    .signature-section {
      margin-top: 24px;
    }
    .signature-section::before {
      content: "Eletricista        OSE";
      display: block;
      text-align: center;
      font-weight: 700;
      margin-bottom: 10px;
      color: #111827;
    }
    .signature-grid {
      width: 100%;
      border-collapse: separate;
      border-spacing: 24px 0;
      table-layout: fixed;
    }
    .signature-grid td {
      border: none;
      padding: 0;
      text-align: center;
      vertical-align: top;
    }
    .signature-line {
      border-top: 1px solid #111827;
      height: 20px;
      margin-top: 10px;
    }
    .signature-name {
      min-height: 16px;
      font-weight: 600;
    }
    .signature-role {
      color: #4b5563;
    }
    """


def _build_saved_report_html(date: str, report_data: dict, notes: list[dict]) -> str:
    volume_rows = report_data.get("volume_rows") or []
    hydrometer_rows = report_data.get("hydrometer_rows") or []
    pump_rows = report_data.get("pump_rows") or []
    valve_rows = report_data.get("valve_rows") or []
    electrician = (report_data.get("electrician") or "").strip() or "—"
    ose = (report_data.get("ose") or "").strip() or "—"

    volume_rows_html = "".join(
        f"<tr><td>{row.get('label', '—')}</td>"
        f"<td class='num'>{_fmt_decimal((row.get('values') or {}).get('CON'))}</td>"
        f"<td class='num'>{_fmt_decimal((row.get('values') or {}).get('CAV'))}</td>"
        f"<td class='num'>{_fmt_decimal((row.get('values') or {}).get('CB3'))}</td>"
        f"<td class='num'>{_fmt_decimal((row.get('values') or {}).get('CIE1'))}</td>"
        f"<td class='num'>{_fmt_decimal((row.get('values') or {}).get('CIE2'))}</td>"
        f"<td class='num'>{_fmt_decimal((row.get('values') or {}).get('CBIF'))}</td>"
        f"<td class='num'>{_fmt_decimal(_saved_volume_total(row.get('values')))}</td></tr>"
        for row in volume_rows
    ) or "<tr><td colspan='8' class='muted-empty'>Sem dados salvos.</td></tr>"

    hydrometer_rows_html = "".join(
        f"<tr><td>{row.get('meterName', '—')}</td>"
        f"<td class='num'>{_fmt_decimal(row.get('previous'), 2)}</td>"
        f"<td class='num'>{_fmt_decimal(row.get('current'), 2)}</td>"
        f"<td class='num'>{_fmt_decimal(row.get('diff'), 2)}</td></tr>"
        for row in hydrometer_rows
    ) or "<tr><td colspan='4' class='muted-empty'>Sem dados salvos.</td></tr>"

    pump_rows_html = "".join(
        f"<tr><td>{row.get('label', '—')}</td><td>{row.get('ELE', '—')}</td><td>{row.get('DIE', '—')}</td></tr>"
        for row in pump_rows
    ) or "<tr><td colspan='3' class='muted-empty'>Sem dados salvos.</td></tr>"

    valve_rows_html = "".join(
        f"<tr><td>{row.get('label', '—')}</td><td>{row.get('CON', '—')}</td><td>{row.get('CAV', '—')}</td></tr>"
        for row in valve_rows
    ) or "<tr><td colspan='3' class='muted-empty'>Sem dados salvos.</td></tr>"

    notes_html = "".join(
        f"<li>{escape(item.get('note', ''))}</li>"
        for item in notes
    ) or "<li>Sem observações ativas.</li>"

    valves_table = f"""
    <table>
      <thead><tr><th>Linha</th><th>CON</th><th>CAV</th></tr></thead>
      <tbody>{valve_rows_html}</tbody>
    </table>
    """
    pumps_table = f"""
    <table>
      <thead><tr><th>Conjunto</th><th class='center'>ELE</th><th class='center'>DIE</th></tr></thead>
      <tbody>{pump_rows_html}</tbody>
    </table>
    """

    return f"""<!DOCTYPE html>
<html lang='pt-BR'>
<head>
  <meta charset='UTF-8'>
  <style>
    {_pdf_styles()}
  </style>
</head>
<body>
  <div class='report-shell'>
    <div class='report-header'>
      <h1>Relatorio Aguada</h1>
      <p class='subtitle'>CMASM, {_fmt_date_br(date)}</p>
    </div>

    <section class='section'>
      <h2>Reservatórios</h2>
      <table>
        <thead><tr><th>Hora</th><th class='num'>CON</th><th class='num'>CAV</th><th class='num'>CB3</th><th class='num'>CIE1</th><th class='num'>CIE2</th><th class='num'>CBIF</th><th class='num'>Total</th></tr></thead>
        <tbody>{volume_rows_html}</tbody>
      </table>
    </section>

    <section class='section'>
      <h2>Hidrômetros</h2>
      <table>
        <thead><tr><th>Hidrômetro</th><th class='num'>Anterior</th><th class='num'>Atual</th><th class='num'>Diferença</th></tr></thead>
        <tbody>{hydrometer_rows_html}</tbody>
      </table>
    </section>

    {_two_column_section('Válvulas', valves_table, 'Bombas', pumps_table)}

    <section class='section'>
      <h2>Observações</h2>
      <ul class='notes'>{notes_html}</ul>
    </section>

    {_signature_block_html(electrician if electrician != '—' else '', ose if ose != '—' else '')}
  </div>
</body>
</html>"""


def _build_html(date: str, reservoirs: list[dict], hydrom_summary: list[dict] | None = None,
                pump_states: list[dict] | None = None, valve_states: list[dict] | None = None,
                notes: list[dict] | None = None) -> str:
    by_alias = {r.get("alias"): r for r in reservoirs}

    # 1) Quadro Local | anterior | atual | diferença
    def _first_last_ton(alias: str) -> tuple[float, float]:
        events = (by_alias.get(alias) or {}).get("events", []) or []
        if not events:
            v = _to_tons((by_alias.get(alias) or {}).get("volume_l"))
            return (v, v)
        start = _to_tons(events[0].get("vol_start"))
        end = _to_tons(events[-1].get("vol_end"))
        return (start, end)

    cav_start, cav_end = _first_last_ton("CAV")
    cbif1_start, cbif1_end = _first_last_ton("CBIF1")
    cbif2_start, cbif2_end = _first_last_ton("CBIF2")
    cb31_start, cb31_end = _first_last_ton("CB31")
    cb32_start, cb32_end = _first_last_ton("CB32")
    cie1_start, cie1_end = _first_last_ton("CIE1")
    cie2_start, cie2_end = _first_last_ton("CIE2")

    table2 = [
        ("Castelo de Incêndio", cav_start, cav_end),
        ("Casa de Bombas IF", cbif1_start + cbif2_start, cbif1_end + cbif2_end),
        ("Casa de Bombas nº3", cb31_start + cb32_start, cb31_end + cb32_end),
        ("Cisterna nº1", cie1_start, cie1_end),
        ("Cisterna nº2", cie2_start, cie2_end),
    ]

    table2_rows_html = ""
    for name, prev_t, curr_t in table2:
        diff_t = curr_t - prev_t
        table2_rows_html += f"""
        <tr>
          <td>{name}</td>
          <td class="num">{_fmt_ton(prev_t)}</td>
          <td class="num">{_fmt_ton(curr_t)}</td>
          <td class="num">{_fmt_signed(diff_t)}</td>
        </tr>
        """

    # 2) Hidrômetros (dados manuais)
    hydrom_rows_html = ""
    if hydrom_summary:
        for h in hydrom_summary:
            prev = "—" if h.get("previous") is None else f"{h.get('previous'):.2f}".replace('.', ',')
            curr = "—" if h.get("current") is None else f"{h.get('current'):.2f}".replace('.', ',')
            diff = "—" if h.get("diff") is None else f"{h.get('diff'):+.2f}".replace('.', ',')
            unit = h.get("unit") or "m3"
            hydrom_rows_html += f"""
              <tr>
                <td>{h.get('meter_name')} ({unit})</td>
                <td class='num'>{prev}</td>
                <td class='num'>{curr}</td>
                <td class='num'>{diff}</td>
              </tr>
            """
    else:
        hydrom_rows_html = """
          <tr><td colspan='4' class='muted-empty'>Sem lançamentos manuais de hidrômetros para o período.</td></tr>
        """

    # 3) Bombas
    _PUMP_LABELS = {"ligada": "LIGADA", "desligada": "DESLIGADA", "falha": "FALHA", "manutencao": "MANUTENÇÃO"}
    _PUMP_COLORS = {"ligada": "#16a34a", "desligada": "#6b7280", "falha": "#dc2626", "manutencao": "#d97706"}
    pump_rows_html = ""
    if pump_states:
        for p in pump_states:
            st = p.get("state", "")
            label = _PUMP_LABELS.get(st, st or "—")
            color = _PUMP_COLORS.get(st, "#6b7280")
            ts_str = datetime.datetime.fromtimestamp(p["ts"]).strftime("%H:%M") if p.get("ts") else "—"
            mode = p.get("mode") or "manual"
            note = escape(p.get("note") or "—")
            pump_rows_html += (
                f"<tr><td>{escape(p['pump_name'])}</td>"
                f"<td style='color:{color};font-weight:600'>{label}</td>"
                f"<td>{mode}</td><td class='num'>{ts_str}</td>"
                f"<td>{note}</td></tr>"
            )
    else:
        pump_rows_html = "<tr><td colspan='5' class='muted-empty'>Sem registros de bombas.</td></tr>"

    # 4) Válvulas
    _VALVE_LABELS = {"aberta": "ABERTA", "fechada": "FECHADA", "parcial": "PARCIAL", "falha": "FALHA"}
    _VALVE_COLORS = {"aberta": "#16a34a", "fechada": "#6b7280", "parcial": "#d97706", "falha": "#dc2626"}
    valve_rows_html = ""
    if valve_states:
        for v in valve_states:
            st = v.get("state", "")
            label = _VALVE_LABELS.get(st, st or "—")
            color = _VALVE_COLORS.get(st, "#6b7280")
            ts_str = datetime.datetime.fromtimestamp(v["ts"]).strftime("%H:%M") if v.get("ts") else "—"
            note = escape(v.get("note") or "—")
            valve_rows_html += (
                f"<tr><td>{escape(v['valve_name'])}</td>"
                f"<td style='color:{color};font-weight:600'>{label}</td>"
                f"<td class='num'>{ts_str}</td>"
                f"<td>{note}</td></tr>"
            )
    else:
        valve_rows_html = "<tr><td colspan='4' class='muted-empty'>Sem registros de válvulas.</td></tr>"

    notes_html = "".join(
        f"<li>{escape(item.get('note', ''))}</li>"
        for item in (notes or [])
    ) or "<li>Sem observações ativas.</li>"

    valves_table = f"""
    <table>
      <thead>
        <tr>
          <th>Válvula</th>
          <th>Estado</th>
          <th class="num">Hora</th>
          <th>Nota</th>
        </tr>
      </thead>
      <tbody>
        {valve_rows_html}
      </tbody>
    </table>
    """
    pumps_table = f"""
    <table>
      <thead>
        <tr>
          <th>Bomba</th>
          <th>Estado</th>
          <th>Modo</th>
          <th class="num">Hora</th>
          <th>Nota</th>
        </tr>
      </thead>
      <tbody>
        {pump_rows_html}
      </tbody>
    </table>
    """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <style>
    {_pdf_styles()}
  </style>
</head>
<body>
  <div class="report-shell">
    <div class="report-header">
      <h1>Relatorio Aguada</h1>
      <p class="subtitle">CMASM, {_fmt_date_br(date)}</p>
    </div>

    <section class="section">
      <h2>Reservatórios</h2>
      <table>
        <thead>
          <tr>
            <th>Local</th>
            <th class="num">Anterior (T)</th>
            <th class="num">Atual (T)</th>
            <th class="num">Diferença (T)</th>
          </tr>
        </thead>
        <tbody>
          {table2_rows_html}
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>Hidrômetros</h2>
      <table>
        <thead>
          <tr>
            <th>Hidrômetro</th>
            <th class="num">Anterior</th>
            <th class="num">Atual</th>
            <th class="num">Diferença</th>
          </tr>
        </thead>
        <tbody>
          {hydrom_rows_html}
        </tbody>
      </table>
    </section>

    {_two_column_section('Válvulas', valves_table, 'Bombas', pumps_table)}

    <section class="section">
      <h2>Observações</h2>
      <ul class="notes">{notes_html}</ul>
    </section>

    {_signature_block_html('', '')}
  </div>
</body>
</html>"""


async def generate_daily_report_pdf(
    conn: aiosqlite.Connection, date: str, out_path: str
) -> None:
    from weasyprint import HTML

    saved_report = await get_report_daily_data(conn, date)
    active_notes = await get_report_notes(conn, date, active_only=True)
    if saved_report:
        html = _build_saved_report_html(date, saved_report, active_notes)
        HTML(string=html).write_pdf(out_path)
        return

    states = await get_all_states(conn)
    enriched = []
    for s in states:
        readings = await get_readings_for_date(conn, alias=s["alias"], date_str=date)
        events = calc_consumption_events(readings, date=date) if readings else []
        enriched.append({**s, "events": events})

    hydrom_summary = await get_manual_hydrometer_summary_for_date(conn, date)
    pump_states = await get_pump_states_for_date(conn, date)
    valve_states = await get_valve_states_for_date(conn, date)
    html = _build_html(date, enriched, hydrom_summary=hydrom_summary,
               pump_states=pump_states, valve_states=valve_states,
               notes=active_notes)
    HTML(string=html).write_pdf(out_path)
