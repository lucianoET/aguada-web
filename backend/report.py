# backend/report.py
"""Geração de relatório HTML + PDF com WeasyPrint."""
from __future__ import annotations
import aiosqlite
from .db import get_all_states, get_readings_for_date, get_manual_hydrometer_summary_for_date
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


def _build_html(date: str, reservoirs: list[dict], hydrom_summary: list[dict] | None = None) -> str:
    by_alias = {r.get("alias"): r for r in reservoirs}

    # 1) Consumo estimado por delta volume (foco no CON, conforme modelo anexado)
    con = by_alias.get("CON", {})
    con_events = con.get("events", []) or []
    consumo_rows_html = ""
    ton_points: list[float] = []

    for e in con_events:
        hour = e.get("hour", "--:--")
        ton = _to_tons(e.get("vol_end"))
        ton_points.append(ton)
        delta = 0 if len(ton_points) == 1 else ton_points[-1] - ton_points[-2]
        consumo_rows_html += f"""
        <tr>
          <td>Castelo de Consumo | {hour}</td>
          <td class="num">{_fmt_ton(ton)}</td>
          <td class="num">{_fmt_signed(delta)}</td>
        </tr>
        """

    if not consumo_rows_html:
        consumo_rows_html = """
        <tr>
          <td>Castelo de Consumo | --:--</td>
          <td class="num">0</td>
          <td class="num">0</td>
        </tr>
        """

    abastecimento_t = sum(max(0.0, ton_points[i] - ton_points[i - 1]) for i in range(1, len(ton_points)))
    consumo_t = sum(min(0.0, ton_points[i] - ton_points[i - 1]) for i in range(1, len(ton_points)))
    balanco_t = abastecimento_t + consumo_t

    # 2) Quadro Local | anterior | atual | diferença
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

    # 3) Hidrômetros (dados manuais)
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
          <tr><td colspan='4' style='text-align:center;color:#6b7280'>Sem lançamentos manuais de hidrômetros para o período.</td></tr>
        """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; font-size: 12px; }}
    h1 {{ font-size: 18px; margin: 0 0 6px 0; }}
    .subtitle {{ color: #4b5563; margin-bottom: 12px; }}
    h2 {{ font-size: 14px; margin: 16px 0 8px 0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 4px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; }}
    th {{ background: #f3f4f6; text-align: left; }}
    td.num, th.num {{ text-align: right; font-family: 'Courier New', monospace; }}
    .sep {{ border-top: 2px solid #9ca3af; margin: 12px 0; }}
    .mini-summary {{ margin-top: 6px; width: 320px; }}
    .mini-summary td {{ border: none; border-bottom: 1px dashed #d1d5db; padding: 3px 0; }}
    .footer {{ margin-top: 24px; font-size: 10px; color: #6b7280; }}
  </style>
</head>
<body>
  <h1>Relatório Diário de Serviço</h1>
  <div class="subtitle">Data de referência: <strong>{date}</strong></div>

  <h2>Consumo (estimado por delta volume)</h2>
  <table>
    <thead>
      <tr>
        <th>Local / Hora</th>
        <th class="num">Ton</th>
        <th class="num">Delta</th>
      </tr>
    </thead>
    <tbody>
      {consumo_rows_html}
    </tbody>
  </table>

  <table class="mini-summary">
    <tbody>
      <tr><td>Abastecimento estimado</td><td class="num">{_fmt_signed(abastecimento_t)}</td></tr>
      <tr><td>Consumo estimado</td><td class="num">{_fmt_signed(consumo_t)}</td></tr>
      <tr><td>Balanço estimado</td><td class="num">{_fmt_signed(balanco_t)}</td></tr>
    </tbody>
  </table>

  <div class="sep"></div>

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

  <div class="sep"></div>

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

  <div class="footer">Gerado automaticamente por Aguada Web — formato tabular operacional.</div>
</body>
</html>"""


async def generate_daily_report_pdf(
    conn: aiosqlite.Connection, date: str, out_path: str
) -> None:
    from weasyprint import HTML
    states = await get_all_states(conn)
    enriched = []
    for s in states:
        readings = await get_readings_for_date(conn, alias=s["alias"], date_str=date)
        events = calc_consumption_events(readings, date=date) if readings else []
        enriched.append({**s, "events": events})

    hydrom_summary = await get_manual_hydrometer_summary_for_date(conn, date)
    html = _build_html(date, enriched, hydrom_summary=hydrom_summary)
    HTML(string=html).write_pdf(out_path)
