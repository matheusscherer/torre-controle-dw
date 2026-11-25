# Torre de Controle Logistica - Data Warehouse (1M Pacotes/Dia)

Pipeline ETL em Python e camada analitica em SQLite para monitorar capacidade de 1.000.000 de pacotes/dia, quarentena de dados e gargalos de SLA/hora extra.

## Como rodar

python src/etl/pipeline_ingestao.py
python src/etl/criar_views.py
python -m unittest tests/test_pipeline.py -v
