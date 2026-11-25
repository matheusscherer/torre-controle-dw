import json
from pathlib import Path
import sqlite3
import webbrowser
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "torre_controle.db"
EXPORTS_DIR = BASE_DIR / "exports"
HTML_PATH = EXPORTS_DIR / "dashboard.html"
LIMITE_DIARIO = 1_000_000


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco SQLite nao encontrado em {DB_PATH}. Rode antes o ETL e criar_views.py.")

    with sqlite3.connect(DB_PATH) as conn:
        df_diario = pd.read_sql_query("SELECT * FROM vw_capacidade_diaria", conn)
        df_gargalos = pd.read_sql_query("SELECT * FROM vw_gargalos_estouro_1m", conn)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    df_diario.to_csv(EXPORTS_DIR / "capacidade_diaria.csv", index=False)
    df_gargalos.to_csv(EXPORTS_DIR / "gargalos_estouro_1m.csv", index=False)

    col_data = next((c for c in df_diario.columns if "data" in c.lower()), df_diario.columns[0])
    col_vol = next(
        (c for c in df_diario.columns if any(k in c.lower() for k in ["pacote", "volume", "total"])),
        df_diario.columns[1],
    )

    serie = df_diario.groupby(col_data, as_index=False)[col_vol].sum().sort_values(col_data)
    dias_estouro = int((serie[col_vol] > LIMITE_DIARIO).sum())
    total_pacotes = int(serie[col_vol].sum())

    resumo_turno = (
        df_gargalos.groupby("turno", as_index=False)
        .agg(
            lead_time_medio_h=("lead_time_medio_h", "mean"),
            sla_pct=("sla_pct", "mean"),
            total_hora_extra=("total_hora_extra", "sum"),
        )
        .sort_values("lead_time_medio_h", ascending=False)
    )

    dados = {
        "datas": serie[col_data].astype(str).tolist(),
        "volumes": [int(v) for v in serie[col_vol].tolist()],
        "limite": LIMITE_DIARIO,
        "turnos": resumo_turno["turno"].astype(str).tolist(),
        "lead_times": [round(float(v), 2) for v in resumo_turno["lead_time_medio_h"].tolist()],
        "slas": [round(float(v), 2) for v in resumo_turno["sla_pct"].tolist()],
        "horas_extras": [round(float(v), 2) for v in resumo_turno["total_hora_extra"].tolist()],
        "top_gargalos": df_gargalos.head(10).to_dict(orient="records"),
        "kpis": {
            "total_pacotes": f"{total_pacotes:,}".replace(",", "."),
            "dias_estouro": dias_estouro,
            "total_dias": len(serie),
            "pior_turno": str(resumo_turno.iloc[0]["turno"]) if not resumo_turno.empty else "-",
            "pior_lt": f"{resumo_turno.iloc[0]['lead_time_medio_h']:.2f}h" if not resumo_turno.empty else "-",
        },
    }

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Torre de Controle DW - BI</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{
      margin: 0; padding: 24px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0b0f17; color: #e5e7eb;
    }}
    h1 {{ margin: 0 0 6px; font-size: 22px; color: #f9fafb; }}
    .sub {{ color: #9ca3af; font-size: 13px; margin-bottom: 20px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .card {{ background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px 16px; }}
    .card .lbl {{ font-size: 12px; color: #9ca3af; text-transform: uppercase; }}
    .card .val {{ font-size: 22px; font-weight: 700; margin-top: 4px; color: #f59e0b; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 16px; margin-bottom: 20px; }}
    .panel {{ background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 16px; }}
    .panel h2 {{ margin: 0 0 12px; font-size: 15px; color: #f3f4f6; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #1f2937; }}
    th {{ color: #9ca3af; font-weight: 600; }}
    .tag-noite {{ color: #f87171; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Torre de Controle Logística — Capacidade & Gargalos</h1>
  <div class="sub">Monitoramento de estouro acima de 1.000.000 pacotes/dia e impacto operacional por turno</div>

  <div class="kpis" id="kpis"></div>

  <div class="grid">
    <div class="panel">
      <h2>Volume Diário vs. Teto de 1.000.000 Pacotes</h2>
      <canvas id="chartDiario"></canvas>
    </div>
    <div class="panel">
      <h2>Lead Time Médio (h) por Turno</h2>
      <canvas id="chartTurno"></canvas>
    </div>
  </div>

  <div class="panel">
    <h2>Top Gargalos (Turno x Transportadora)</h2>
    <table>
      <thead>
        <tr>
          <th>Rank</th><th>Turno</th><th>Transportadora</th>
          <th>Dias Estouro</th><th>Pacotes Estouro</th>
          <th>Lead Time (h)</th><th>SLA (%)</th><th>Hora Extra</th>
        </tr>
      </thead>
      <tbody id="tbodyGargalos"></tbody>
    </table>
  </div>

  <script>
    const DADOS = {json.dumps(dados, ensure_ascii=False)};

    document.getElementById("kpis").innerHTML = `
      <div class="card"><div class="lbl">Volume Total</div><div class="val">${{DADOS.kpis.total_pacotes}}</div></div>
      <div class="card"><div class="lbl">Dias Estouro (> 1M)</div><div class="val">${{DADOS.kpis.dias_estouro}} / ${{DADOS.kpis.total_dias}}</div></div>
      <div class="card"><div class="lbl">Turno Crítico</div><div class="val">${{DADOS.kpis.pior_turno}}</div></div>
      <div class="card"><div class="lbl">Maior Lead Time</div><div class="val">${{DADOS.kpis.pior_lt}}</div></div>
    `;

    new Chart(document.getElementById("chartDiario"), {{
      type: "bar",
      data: {{
        labels: DADOS.datas,
        datasets: [
          {{
            label: "Volume Diário",
            data: DADOS.volumes,
            backgroundColor: DADOS.volumes.map(v => v > DADOS.limite ? "#ef4444" : "#3b82f6")
          }},
          {{
            type: "line",
            label: "Teto 1.000.000",
            data: DADOS.datas.map(() => DADOS.limite),
            borderColor: "#f59e0b",
            borderDash: [6, 4],
            pointRadius: 0
          }}
        ]
      }},
      options: {{ plugins: {{ legend: {{ labels: {{ color: "#d1d5db" }} }} }}, scales: {{ x: {{ ticks: {{ color: "#9ca3af" }} }}, y: {{ ticks: {{ color: "#9ca3af" }} }} }} }}
    }});

    new Chart(document.getElementById("chartTurno"), {{
      type: "bar",
      data: {{
        labels: DADOS.turnos,
        datasets: [{{
          label: "Lead Time Médio (h)",
          data: DADOS.lead_times,
          backgroundColor: DADOS.turnos.map(t => t.includes("NOITE") ? "#ef4444" : "#64748b")
        }}]
      }},
      options: {{ indexAxis: "y", plugins: {{ legend: {{ labels: {{ color: "#d1d5db" }} }} }}, scales: {{ x: {{ ticks: {{ color: "#9ca3af" }} }}, y: {{ ticks: {{ color: "#9ca3af" }} }} }} }}
    }});

    document.getElementById("tbodyGargalos").innerHTML = DADOS.top_gargalos.map(r => `
      <tr>
        <td>${{r.rank_gargalo_lead_time}}</td>
        <td class="${{String(r.turno).includes("NOITE") ? "tag-noite" : ""}}">${{r.turno}}</td>
        <td>${{r.transportadora}}</td>
        <td>${{r.dias_estouro}}</td>
        <td>${{Number(r.pacotes_em_estouro).toLocaleString("pt-BR")}}</td>
        <td>${{Number(r.lead_time_medio_h).toFixed(2)}}h</td>
        <td>${{Number(r.sla_pct).toFixed(2)}}%</td>
        <td>${{Number(r.total_hora_extra).toLocaleString("pt-BR")}}</td>
      </tr>
    `).join("");
  </script>
</body>
</html>
"""

    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard gerado em: {HTML_PATH}")
    webbrowser.open(HTML_PATH.resolve().as_uri())


if __name__ == "__main__":
    main()
