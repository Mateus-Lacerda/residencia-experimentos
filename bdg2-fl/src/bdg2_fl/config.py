"""Parâmetros do experimento num só lugar."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RAW = RAIZ / "data" / "raw"

BASE_URL = "https://media.githubusercontent.com/media/buds-lab/building-data-genome-project-2/master/data"
ARQUIVOS = {
    "electricity_cleaned.csv": "meters/cleaned/electricity_cleaned.csv",
    "chilledwater_cleaned.csv": "meters/cleaned/chilledwater_cleaned.csv",
    "steam_cleaned.csv": "meters/cleaned/steam_cleaned.csv",
    "hotwater_cleaned.csv": "meters/cleaned/hotwater_cleaned.csv",
    "gas_cleaned.csv": "meters/cleaned/gas_cleaned.csv",
    "weather.csv": "weather/weather.csv",
    "metadata.csv": "metadata/metadata.csv",
}

N_SITES = 6               # clientes da federação
MAX_EDIF_POR_SITE = 20
MIN_PREENCHIMENTO = 0.90  # fração mínima de horas com eletricidade, em 2016 E em 2017
MIN_MEDIANA_KWH = 1.0     # mediana horária mínima, em cada ano

MEDIDORES_OPCIONAIS = ["chilledwater", "steam", "hotwater", "gas"]
LAGS = [1, 24, 168]

SEED = 42
OCULTAS = 64
LR = 1e-3
BATCH = 512
RODADAS = 30
EPOCAS_LOCAIS = 2
EPOCAS_BASELINE = RODADAS * EPOCAS_LOCAIS  # mesmo número de passadas sobre os dados

AMOSTRA_PERDA_LOCAL = 20_000   # linhas usadas para medir a perda local antes/depois
