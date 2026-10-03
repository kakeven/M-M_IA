"""Persistência atômica do criador manual e leitura compatível com fichas antigas."""
import json
import os
import re
import uuid
from shutil import copy2
from pathlib import Path

FICHAS_DIR = Path(__file__).resolve().parents[1] / ".local" / "fichas"
MOTOR_DIR = Path(__file__).resolve().parent

def _nome(arquivo, extensao=".json"):
    if not isinstance(arquivo, str):
        raise ValueError("Informe um nome de arquivo.")
    nome = arquivo.strip()
    if nome.lower().endswith(extensao):
        nome = nome[:-len(extensao)]
    if not nome or len(nome) > 150 or nome in (".", "..") or re.search(r'[<>:"/\\|?*\x00-\x1f]', nome):
        raise ValueError("Use somente o nome do arquivo, sem caminho ou caracteres especiais.")
    if nome.endswith((".", " ")) or nome.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError("Nome de arquivo inválido no Windows.")
    return nome + extensao

def _caminho_ficha(arquivo, escrita=False):
    nome = _nome(arquivo)
    destino = FICHAS_DIR / nome
    if not escrita and not destino.is_file():
        antigo = MOTOR_DIR / nome
        if antigo.is_file():
            return antigo
    return destino

def _gravar(destino, conteudo):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f".{destino.stem}.{uuid.uuid4().hex}.tmp")
    try:
        with temporario.open("w", encoding="utf-8") as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)

def salvar(ficha, arquivo="ficha.json"):
    destino = _caminho_ficha(arquivo, escrita=True)
    conteudo = json.dumps(ficha.para_dict(), ensure_ascii=False, indent=2)
    if destino.is_file():
        historico = destino.parent / ".historico"
        historico.mkdir(parents=True, exist_ok=True)
        copy2(destino, historico / f"{destino.stem}.{uuid.uuid4().hex}.json")
    _gravar(destino, conteudo)
    print(f"Ficha salva: {destino}")
    return destino

def carregar_ficha(caminho):
    from ficha import Ficha
    dados = json.loads(_caminho_ficha(caminho).read_text(encoding="utf-8-sig"))
    return Ficha.de_dict(dados)

def listar_fichas():
    fichas = {}
    for diretorio in (MOTOR_DIR, FICHAS_DIR):
        for caminho in diretorio.glob("*.json"):
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8-sig"))
                if isinstance(dados, dict) and "nomePersonagem" in dados and "np" in dados:
                    fichas[caminho.name] = {"nome": dados["nomePersonagem"],
                        "arquivo": caminho.name, "np": dados["np"]}
            except (ValueError, OSError):
                continue
    return sorted(fichas.values(), key=lambda item: item["nome"].casefold())

def exportar_texto(ficha, arquivo):
    from ficha_utilitarios import resumo_texto
    destino = FICHAS_DIR / _nome(arquivo, ".txt")
    _gravar(destino, resumo_texto(ficha))
    return destino

