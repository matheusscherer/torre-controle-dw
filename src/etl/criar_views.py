import sqlite3
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "torre_controle.db"

SQL_VIEWS = """
DROP VIEW IF EXISTS vw_capacidade_diaria;
CREATE VIEW vw_capacidade_diaria AS
WITH diario AS (
    SELECT
        data_referencia,
        COUNT(*) AS total_lotes,
        SUM(qtd_pacotes) AS pacotes_processados,
        ROUND(AVG(lead_time_horas), 2) AS lead_time_medio_h,
        ROUND(AVG(sla_cumprido) * 100.0, 2) AS sla_pct,
        ROUND(SUM(custo_operacional + custo_hora_extra), 2) AS custo_total_dia
    FROM fato_operacoes
    GROUP BY data_referencia
),
com_variacao AS (
    SELECT
        data_referencia,
        total_lotes,
        pacotes_processados,
        LAG(pacotes_processados) OVER (ORDER BY data_referencia) AS pacotes_dia_anterior,
        ROUND((pacotes_processados / 1000000.0) * 100.0, 1) AS ocupacao_cd_pct,
        CASE
            WHEN pacotes_processados > 1000000 THEN 'ESTOURO_ACIMA_1M'
            WHEN pacotes_processados >= 880000 THEN 'ZONA_SEGURA_ALTA'
            ELSE 'ABAIXO_META_SEGURA'
        END AS status_capacidade,
        lead_time_medio_h,
        sla_pct,
        custo_total_dia
    FROM diario
)
SELECT
    data_referencia,
    total_lotes,
    pacotes_processados,
    pacotes_dia_anterior,
    (pacotes_processados - pacotes_dia_anterior) AS diff_pacotes_d1,
    ocupacao_cd_pct,
    status_capacidade,
    lead_time_medio_h,
    sla_pct,
    custo_total_dia
FROM com_variacao;

DROP VIEW IF EXISTS vw_gargalos_estouro_1m;
CREATE VIEW vw_gargalos_estouro_1m AS
WITH volume_diario AS (
    SELECT
        data_referencia,
        SUM(qtd_pacotes) AS pacotes_dia
    FROM fato_operacoes
    GROUP BY data_referencia
),
dias_criticos AS (
    SELECT
        data_referencia,
        pacotes_dia,
        ROUND((pacotes_dia / 1000000.0) * 100.0, 1) AS ocupacao_cd_pct
    FROM volume_diario
    WHERE pacotes_dia > 1000000
)
SELECT
    f.turno,
    f.transportadora,
    COUNT(DISTINCT f.data_referencia) AS dias_estouro,
    SUM(f.qtd_pacotes) AS pacotes_em_estouro,
    ROUND(AVG(f.lead_time_horas), 2) AS lead_time_medio_h,
    ROUND(AVG(f.sla_cumprido) * 100.0, 2) AS sla_pct,
    ROUND(SUM(f.custo_hora_extra), 2) AS total_hora_extra,
    RANK() OVER (ORDER BY AVG(f.lead_time_horas) DESC) AS rank_gargalo_lead_time
FROM fato_operacoes f
INNER JOIN dias_criticos d
    ON f.data_referencia = d.data_referencia
GROUP BY
    f.turno,
    f.transportadora;
"""


def main():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SQL_VIEWS)
        print("Views criadas com sucesso em:", DB_PATH)
        print("\n--- Top 5 Gargalos (vw_gargalos_estouro_1m) ---")
        df_gargalos = pd.read_sql_query(
            "SELECT * FROM vw_gargalos_estouro_1m ORDER BY rank_gargalo_lead_time ASC LIMIT 5",
            conn,
        )
        print(df_gargalos.to_string())


if __name__ == "__main__":
    main()