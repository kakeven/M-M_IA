"""Cálculos puros para a criação de fichas; não acessa terminal nem arquivos."""

from copy import deepcopy
from fractions import Fraction
from math import ceil

HABILIDADES = (
    "forca", "agilidade", "destreza", "luta", "intelecto",
    "prontidao", "presenca", "vigor",
)
PONTOS_POR_NP = 15
PONTOS_POR_GRADUACAO_HABILIDADE = 2
GRADUACOES_PERICIA_POR_PONTO = 2
PONTOS_POR_GRADUACAO_VANTAGEM = 1


def _inteiro(valor, nome, minimo=0):
    if type(valor) is not int or valor < minimo:
        raise ValueError(f"{nome} deve ser um inteiro maior ou igual a {minimo}")
    return valor


def orcamento(np):
    return _inteiro(np, "np", 1) * PONTOS_POR_NP


def custo_habilidade(graduacao):
    if graduacao is None:
        return -10
    return _inteiro(graduacao, "graduacao da habilidade", -5) * PONTOS_POR_GRADUACAO_HABILIDADE


def custo_pericia(pontos):
    return _inteiro(pontos, "pontos da pericia")


def graduacoes_pericia(pontos):
    return custo_pericia(pontos) * GRADUACOES_PERICIA_POR_PONTO


def custo_graduacoes_pericia(graduacao):
    """Mantém meias compras; duas graduações custam um ponto no total."""
    return _inteiro(graduacao, "graduação da perícia") / GRADUACOES_PERICIA_POR_PONTO


def limite_graduacoes_pericia(np):
    return _inteiro(np, "np", 1) + 10


def custo_vantagem(graduacao):
    return _inteiro(graduacao, "graduacao da vantagem") * PONTOS_POR_GRADUACAO_VANTAGEM


def custo_componente(custo_base, graduacao, modificadores=()):
    """Soma custos por graduação e modificadores, com intervalos inclusivos 1..N."""
    _inteiro(custo_base, "custo_base", 1)
    _inteiro(graduacao, "graduacao", 1)
    por_graduacao = [custo_base] * graduacao
    custo_fixo = 0
    for modificador in modificadores:
        tipo = modificador["tipo"]
        valor = modificador["valor"]
        if type(valor) is not int:
            raise ValueError("valor do modificador deve ser inteiro")
        if tipo == "fixo":
            custo_fixo += valor
        elif tipo == "por_graduacao":
            inicio = modificador.get("inicio")
            fim = modificador.get("fim")
            inicio = 1 if inicio is None else _inteiro(inicio, "inicio", 1)
            fim = graduacao if fim is None else _inteiro(fim, "fim", 1)
            if inicio > fim or fim > graduacao:
                raise ValueError("intervalo fora das graduações do componente")
            for indice in range(inicio - 1, fim):
                por_graduacao[indice] += valor
        else:
            raise ValueError(f"tipo de modificador não calculável: {tipo}")
    # Abaixo de 1 ponto por graduação, a progressão passa a ser 1:2, 1:3...
    custo_graduacoes = sum(
        Fraction(valor, 1) if valor >= 1 else Fraction(1, 2 - valor)
        for valor in por_graduacao
    )
    total = ceil(custo_graduacoes) + custo_fixo
    return max(1, total)


def modificadores_componente(componente):
    """Obtém os modificadores persistidos, sem depender dos totais em cache."""
    return [
        modificador
        for grupo in ("extras", "falhas")
        for modificador in componente.get(grupo, {}).values()
    ]


def custo_poder(poder, eh_alternativa=False):
    total = sum(
        custo_componente(
            componente["custo_base"],
            componente["graduacao"],
            modificadores_componente(componente),
        )
        for componente in poder.get("componentes", [])
    )
    for alternativa in poder.get("alternativas", []):
        if custo_poder(alternativa, eh_alternativa=True) > total:
            raise ValueError("o efeito alternativo excede o custo do efeito primário")
    total += sum(2 if a.get("dinamico") else 1 for a in poder.get("alternativas", []))
    if poder.get("dinamico") and not eh_alternativa:
        total += 1
    total += sum(
        item["valor"] for grupo in ("extras", "falhas")
        for nome, item in poder.get(grupo, {}).items()
        if nome != "removivel" and isinstance(item, dict) and item["tipo"] == "fixo"
    )
    removivel = poder.get("falhas", {}).get("removivel")
    if removivel is not None:
        intensidade = removivel.get("valor") if isinstance(removivel, dict) else removivel
        _inteiro(intensidade, "intensidade de removivel", 1)
        if intensidade not in (1, 2):
            raise ValueError("intensidade de removivel deve ser 1 ou 2")
        desconto = ceil(total / 5) * intensidade
        if poder.get("indestrutivel"):
            desconto = max(0, desconto - 1)
        total -= desconto
    return max(1, total) if poder.get("componentes") else 0


def componente_com_modificador(componente, grupo, nome, modificador):
    """Devolve uma cópia recalculada, preservando a entrada em caso de erro."""
    if grupo not in ("extras", "falhas"):
        raise ValueError("grupo de modificador inválido")
    novo = deepcopy(componente)
    novo.setdefault(grupo, {})[nome] = modificador
    novo["custo_total"] = custo_componente(
        novo["custo_base"], novo["graduacao"], modificadores_componente(novo)
    )
    novo["mod_por_graduacao"] = sum(
        item["valor"] for item in modificadores_componente(novo)
        if item["tipo"] == "por_graduacao" and item.get("inicio") is None
        and item.get("fim") is None
    )
    novo["mod_fixo"] = sum(
        item["valor"] for item in modificadores_componente(novo)
        if item["tipo"] == "fixo"
    )
    return novo


def poder_com_modificador(poder, grupo, nome, modificador):
    """Aplica um modificador global sem alterar o poder original."""
    if grupo not in ("extras", "falhas"):
        raise ValueError("grupo de modificador invalido")
    novo = deepcopy(poder)
    if nome == "efeito alternativo":
        raise ValueError("adicione uma alternativa ao arranjo, com seus próprios componentes")
    novo.setdefault(grupo, {})[nome] = modificador
    if nome == "removivel":
        if grupo != "falhas":
            raise ValueError("removivel so pode ser falha")
        custo_poder(novo)
        return novo
    for variante in [novo, *novo.get("alternativas", [])]:
        for componente in variante.get("componentes", []):
            componente.setdefault(grupo, {}).pop(f"poder:{nome}", None)
            if modificador["tipo"] == "por_graduacao":
                atualizado = componente_com_modificador(
                    componente, grupo, f"poder:{nome}", modificador
                )
                componente.update(atualizado)
    return novo
