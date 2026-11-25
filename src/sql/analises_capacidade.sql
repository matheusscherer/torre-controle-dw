-- 1. Volume diário vs. Capacidade do CD (1.000.000 pacotes/dia) e variação D-1 (LAG)
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
    pacotes_processados,
    pacotes_dia_anterior,
    (pacotes_processados - pacotes_dia_anterior) AS diff_pacotes_d1,
    ocupacao_cd_pct,
    status_capacidade,
    lead_time_medio_h,
    sla_pct,
    custo_total_dia
FROM com_variacao
ORDER BY data_referencia DESC
LIMIT 15;