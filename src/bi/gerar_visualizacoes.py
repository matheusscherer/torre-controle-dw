from pathlib import Path
import sqlite3
import matplotlib.pyplot as plt
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "torre_controle.db"
EXPORTS_DIR = BASE_DIR / "exports"
LIMITE_DIARIO = 1_000_000


def carregar_views(db_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with sqlite3.connect(db_path) as conn:
        df_diario = pd.read_sql_query("SELECT * FROM vw_capacidade_diaria", conn)
        df_gargalos = pd.read_sql_query("SELECT * FROM vw_gargalos_estouro_1m", conn)
    return df_diario, df_gargalos


def exportar_csvs(df_diario: pd.DataFrame, df_gargalos: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df_diario.to_csv(out_dir / "capacidade_diaria.csv", index=False)
    df_gargalos.to_csv(out_dir / "gargalos_estouro_1m.csv", index=False)


def plotar_volume_diario(df_diario: pd.DataFrame, out_dir: Path) -> None:
    col_data = next((c for c in df_diario.columns if "data" in c.lower()), df_diario.columns[0])
    col_vol = next((c for c in df_diario.columns if any(k in c.lower() for k in ["pacote", "volume", "total"])), df_diario.columns[1])

    serie = df_diario.groupby(col_data, as_index=False)[col_vol].sum().sort_values(col_data)
    cores = ["#e11d48" if v > LIMITE_DIARIO else "#2563eb" for v in serie[col_vol]]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(serie[col_data].astype(str), serie[col_vol], color=cores, width=0.65)
    ax.axhline(LIMITE_DIARIO, color="#dc2626", linestyle="--", linewidth=1.8, label="Teto 1.000.000 pacotes/dia")
    ax.set_title("Volume Diario vs. Teto de 1.000.000 de Pacotes")
    ax.set_xlabel("Data")
    ax.set_ylabel("Pacotes")
    ax.legend()
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(out_dir / "volume_diario_vs_1m.png", dpi=150)
    plt.close(fig)


def plotar_gargalos_turno(df_gargalos: pd.DataFrame, out_dir: Path) -> None:
    if df_gargalos.empty or "turno" not in df_gargalos.columns:
        return

    metrificar = "lead_time_medio_h" if "lead_time_medio_h" in df_gargalos.columns else df_gargalos.select_dtypes(include="number").columns[0]
    resumo = df_gargalos.groupby("turno", as_index=False)[metrificar].mean().sort_values(metrificar, ascending=True)
    cores = ["#dc2626" if "NOITE" in str(t).upper() else "#475569" for t in resumo["turno"]]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(resumo["turno"].astype(str), resumo[metrificar], color=cores)
    ax.set_title(f"Gargalos por Turno ({metrificar})")
    ax.set_xlabel(metrificar)
    ax.set_ylabel("Turno")
    plt.tight_layout()
    fig.savefig(out_dir / "gargalos_por_turno.png", dpi=150)
    plt.close(fig)


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco SQLite nao encontrado em {DB_PATH}. Rode antes o ETL e criar_views.py.")
    df_diario, df_gargalos = carregar_views(DB_PATH)
    exportar_csvs(df_diario, df_gargalos, EXPORTS_DIR)
    plotar_volume_diario(df_diario, EXPORTS_DIR)
    plotar_gargalos_turno(df_gargalos, EXPORTS_DIR)
    print(f"Arquivos salvos em: {EXPORTS_DIR}")


if __name__ == "__main__":
    main()
