import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "torre_controle.db"
CAPACIDADE_DIARIA_CD = 1_000_000


def criar_dimensao_capacidade() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "unidade": "HUB_LOGISTICO_PRINCIPAL",
            "turno": "T1_MANHA",
            "pct_share": 0.30,
            "capacidade_nominal_pacotes": int(CAPACIDADE_DIARIA_CD * 0.30),
            "capacidade_segura_pacotes": int(CAPACIDADE_DIARIA_CD * 0.30 * 0.88),
            "meta_vazao_hora": int((CAPACIDADE_DIARIA_CD * 0.30) / 8),
        },
        {
            "unidade": "HUB_LOGISTICO_PRINCIPAL",
            "turno": "T2_TARDE",
            "pct_share": 0.40,
            "capacidade_nominal_pacotes": int(CAPACIDADE_DIARIA_CD * 0.40),
            "capacidade_segura_pacotes": int(CAPACIDADE_DIARIA_CD * 0.40 * 0.88),
            "meta_vazao_hora": int((CAPACIDADE_DIARIA_CD * 0.40) / 8),
        },
        {
            "unidade": "HUB_LOGISTICO_PRINCIPAL",
            "turno": "T3_NOITE",
            "pct_share": 0.30,
            "capacidade_nominal_pacotes": int(CAPACIDADE_DIARIA_CD * 0.30),
            "capacidade_segura_pacotes": int(CAPACIDADE_DIARIA_CD * 0.30 * 0.88),
            "meta_vazao_hora": int((CAPACIDADE_DIARIA_CD * 0.30) / 8),
        },
    ])


def gerar_dados_brutos(n_lotes: int = 60000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    datas_base = pd.date_range("2026-10-20", "2026-11-18 23:59:00", freq="min")
    dt_entrada = pd.to_datetime(rng.choice(datas_base, size=n_lotes))

    turnos = np.where(
        dt_entrada.hour.isin(range(6, 14)),
        "T1_MANHA",
        np.where(dt_entrada.hour.isin(range(14, 22)), "T2_TARDE", "T3_NOITE"),
    )
    transportadoras = rng.choice(["TransSul", "RodoExpress", "LogRapida", "FrotaPropria"], size=n_lotes)
    canais = rng.choice(["Ecommerce_Direct", "Marketplace", "B2B_Varejo"], size=n_lotes, p=[0.55, 0.30, 0.15])

    dia_semana = dt_entrada.dayofweek
    fator_pico = np.where(dia_semana.isin([0, 1]), 1.15, 0.96)
    qtd_pacotes = np.maximum(50, np.round(rng.normal(loc=500, scale=95, size=n_lotes) * fator_pico)).astype(int)

    fator_gargalo = np.where(fator_pico > 1.05, 1.38, 1.0)
    fator_turno = np.where(turnos == "T3_NOITE", 1.25, 1.0)

    min_picking = np.round(rng.gamma(shape=3.0, scale=15.0, size=n_lotes) * fator_turno * fator_gargalo, 1)
    min_doca = np.round(rng.gamma(shape=2.5, scale=20.0, size=n_lotes) * fator_turno * fator_gargalo, 1)
    min_expedicao = np.round(rng.gamma(shape=2.0, scale=14.0, size=n_lotes), 1)

    dt_picking = dt_entrada + pd.to_timedelta(min_picking, unit="m")
    dt_doca = dt_picking + pd.to_timedelta(min_doca, unit="m")
    dt_expedicao = dt_doca + pd.to_timedelta(min_expedicao, unit="m")

    sla_meta_horas = np.where(
        canais == "Ecommerce_Direct",
        4.0,
        np.where(canais == "Marketplace", 6.0, 12.0),
    )

    custo_operacional = np.round(qtd_pacotes * rng.uniform(0.18, 0.32, size=n_lotes) * fator_turno, 2)
    custo_hora_extra = np.where(
        (fator_pico > 1.05) | ((turnos == "T3_NOITE") & (rng.random(n_lotes) < 0.30)),
        np.round(qtd_pacotes * rng.uniform(0.05, 0.14, size=n_lotes), 2),
        0.0,
    )

    df = pd.DataFrame({
        "lote_id": [f"LOT-{100000 + i}" for i in range(n_lotes)],
        "unidade": "HUB_LOGISTICO_PRINCIPAL",
        "turno": turnos,
        "canal": canais,
        "transportadora": transportadoras,
        "qtd_pacotes": qtd_pacotes,
        "dt_entrada": dt_entrada,
        "dt_picking": dt_picking,
        "dt_doca": dt_doca,
        "dt_expedicao": dt_expedicao,
        "sla_meta_horas": sla_meta_horas,
        "custo_operacional": custo_operacional,
        "custo_hora_extra": custo_hora_extra,
    })

    duplicados = df.sample(n=150, random_state=seed)
    df = pd.concat([df, duplicados], ignore_index=True)

    idx_invertidos = rng.choice(df.index, size=80, replace=False)
    df.loc[idx_invertidos, "dt_expedicao"] = df.loc[idx_invertidos, "dt_entrada"] - pd.Timedelta(hours=2)

    idx_nulos = rng.choice(df.index, size=60, replace=False)
    df.loc[idx_nulos[:30], "transportadora"] = None
    df.loc[idx_nulos[30:], "qtd_pacotes"] = np.nan

    return df


def validar_e_separar(df: pd.DataFrame):
    df = df.copy()
    df["motivo_rejeicao"] = ""

    mask_dup = df.duplicated(subset=["lote_id"], keep="first")
    df.loc[mask_dup, "motivo_rejeicao"] += "DUPLICIDADE_LOTE; "

    mask_nulo = df[["lote_id", "transportadora", "dt_entrada", "dt_expedicao", "qtd_pacotes"]].isna().any(axis=1)
    df.loc[mask_nulo, "motivo_rejeicao"] += "CAMPO_OBRIGATORIO_NULO; "

    mask_tempo = (
        (df["dt_picking"] < df["dt_entrada"])
        | (df["dt_doca"] < df["dt_picking"])
        | (df["dt_expedicao"] < df["dt_doca"])
    )
    df.loc[mask_tempo, "motivo_rejeicao"] += "INCONSISTENCIA_TEMPORAL; "

    mask_valor = (df["qtd_pacotes"] <= 0) | (df["custo_operacional"] <= 0)
    df.loc[mask_valor, "motivo_rejeicao"] += "VOLUME_OU_CUSTO_INVALIDO; "

    quarentena = df[df["motivo_rejeicao"] != ""].copy()
    limpos = df[df["motivo_rejeicao"] == ""].drop(columns=["motivo_rejeicao"]).copy()

    limpos["qtd_pacotes"] = limpos["qtd_pacotes"].astype(int)
    limpos["lead_time_horas"] = np.round(
        (limpos["dt_expedicao"] - limpos["dt_entrada"]).dt.total_seconds() / 3600.0, 2
    )
    limpos["sla_cumprido"] = np.where(limpos["lead_time_horas"] <= limpos["sla_meta_horas"], 1, 0)
    limpos["data_referencia"] = limpos["dt_entrada"].dt.strftime("%Y-%m-%d")

    return limpos, quarentena


def carregar_no_banco(limpos: pd.DataFrame, quarentena: pd.DataFrame, dim_cap: pd.DataFrame) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        dim_cap.to_sql("dim_capacidade_cd", conn, if_exists="replace", index=False)
        limpos.to_sql("fato_operacoes", conn, if_exists="replace", index=False)
        quarentena.to_sql("pedidos_quarentena", conn, if_exists="replace", index=False)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_fato_data ON fato_operacoes (data_referencia);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fato_turno ON fato_operacoes (turno);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fato_sla ON fato_operacoes (sla_cumprido);")


def main():
    print('1. Gerando operacao em escala de 1.000.000 pacotes/dia...')
    df_bruto = gerar_dados_brutos(n_lotes=60000)
    df_limpos, df_quarentena = validar_e_separar(df_bruto)
    dim_cap = criar_dimensao_capacidade()
    media_diaria = df_limpos.groupby('data_referencia')['qtd_pacotes'].sum().mean()
    print(f'   -> Lotes aprovados: {len(df_limpos):,} | Quarentena: {len(df_quarentena):,}')
    print(f'   -> Volume medio diario: {media_diaria:,.0f} pacotes/dia (Meta CD: 1.000.000)')
    carregar_no_banco(df_limpos, df_quarentena, dim_cap)
    print('   -> Banco SQLite salvo com sucesso!')

if __name__ == '__main__':
    main()
