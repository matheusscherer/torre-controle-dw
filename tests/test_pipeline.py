import sqlite3
import unittest
from pathlib import Path
import pandas as pd
from src.etl.pipeline_ingestao import gerar_dados_brutos, validar_e_separar


class TestTorreControleDW(unittest.TestCase):
    def test_quarentena_separa_anomalias_sem_perder_registros(self):
        df_bruto = gerar_dados_brutos(n_lotes=1000, seed=42)
        limpos, quarentena = validar_e_separar(df_bruto)

        self.assertEqual(len(limpos) + len(quarentena), len(df_bruto))
        self.assertGreater(len(quarentena), 0)
        self.assertTrue((limpos["lead_time_horas"] >= 0).all())
        self.assertTrue(limpos["lote_id"].is_unique)

    def test_views_existem_no_data_warehouse(self):
        db_path = Path("data/torre_controle.db")
        self.assertTrue(db_path.exists(), "Banco torre_controle.db nao encontrado.")

        with sqlite3.connect(db_path) as conn:
            df_cap = pd.read_sql_query("SELECT * FROM vw_capacidade_diaria LIMIT 5", conn)
            df_gar = pd.read_sql_query("SELECT * FROM vw_gargalos_estouro_1m LIMIT 5", conn)

        self.assertFalse(df_cap.empty)
        self.assertFalse(df_gar.empty)
        self.assertIn("ocupacao_cd_pct", df_cap.columns)
        self.assertIn("rank_gargalo_lead_time", df_gar.columns)


if __name__ == "__main__":
    unittest.main()