"""Baixa os CSVs do BDG2. O repositório usa Git LFS; o endpoint media.githubusercontent.com
entrega o conteúdo real em vez do ponteiro LFS."""
import urllib.request

from .config import ARQUIVOS, BASE_URL, RAW


def baixar():
    RAW.mkdir(parents=True, exist_ok=True)
    for nome, caminho in ARQUIVOS.items():
        destino = RAW / nome
        if destino.exists() and destino.stat().st_size > 10_000:
            continue
        print(f"  baixando {nome} ...")
        urllib.request.urlretrieve(f"{BASE_URL}/{caminho}", destino)
        if destino.stat().st_size < 10_000:
            raise RuntimeError(f"{nome} parece ser um ponteiro LFS, não o arquivo real")


if __name__ == "__main__":
    baixar()
