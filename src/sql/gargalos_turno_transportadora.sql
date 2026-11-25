-- Gargalos de lead time, SLA e custo por turno e transportadora nos dias de estouro (> 1.000.000 pacotes)
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
    f.transportadora
ORDER BY
    rank_gargalo_lead_time ASC,
    total_hora_extra DESC;