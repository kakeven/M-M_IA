"""Adaptador para o motor de regras incluído na pasta local do projeto."""

from __future__ import annotations

import importlib.util
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from mm_ia.config import PROJECT_ROOT

MOTOR_DIR = PROJECT_ROOT / "Motor de regras"


def _key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in text if not unicodedata.combining(c)))


ALIASES = {"sorte": "controledasorte", "moverobjetos": "moverobjeto"}


def canonical_id(value: str) -> str:
    """Identificador estável para nomes e chaves dos JSONs locais."""
    key = _key(value)
    return ALIASES.get(key, key)


def _load_local_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Não foi possível carregar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def load_engine() -> tuple[dict[str, tuple[str, dict[str, Any]]], Any] | None:
    """Carrega o motor de regras quando seus arquivos estão disponíveis."""
    powers_file = MOTOR_DIR / "poderes.py"
    calculations_file = MOTOR_DIR / "calculos.py"
    if not powers_file.is_file() or not calculations_file.is_file():
        return None
    powers = _load_local_module("mm_ia_local_powers", powers_file)
    calculations = _load_local_module("mm_ia_local_calculations", calculations_file)
    catalog = {
        canonical_id(name): (name, entry)
        for name, entry in powers.efeitos_poderes_dicionario.items()
    }
    return catalog, calculations


@lru_cache(maxsize=1)
def rule_options() -> dict[str, Any] | None:
    """Expõe somente nomes e custos da instalação privada para a interface."""
    engine = load_engine()
    if engine is None:
        return None
    catalog, calculations = engine
    powers = _load_local_module("mm_ia_local_options", MOTOR_DIR / "poderes.py")
    return {
        "habilidades": list(calculations.HABILIDADES),
        "pericias": dict(powers.pericias_por_habilidade),
        "vantagens": list(powers.vantagens),
        "efeitos": [
            {"id": identifier, "nome": name,
             "custo_base": entry.get("custo") if type(entry.get("custo")) is int else None}
            for identifier, (name, entry) in catalog.items()
        ],
        "custos": {
            "habilidade": calculations.PONTOS_POR_GRADUACAO_HABILIDADE,
            "pericia_graduacoes_por_ponto": calculations.GRADUACOES_PERICIA_POR_PONTO,
            "vantagem": calculations.PONTOS_POR_GRADUACAO_VANTAGEM,
            "pontos_por_np": calculations.PONTOS_POR_NP,
        },
    }


def _gradations_by_id(gradations: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for name, proposal in gradations.items():
        if isinstance(proposal, dict):
            result[canonical_id(name)] = proposal
    return result


def calculate_proposal(
    confirmed: dict[str, Any], gradations: dict[str, Any]
) -> dict[str, Any]:
    """Calcula apenas custos base de efeitos confirmados e graduações explícitas."""
    engine = load_engine()
    if engine is None:
        return {
            "disponivel": False,
            "itens": [],
            "total_calculado": 0,
            "custos_base_completos": False,
            "motivo": "Motor de regras local não encontrado.",
        }
    catalog, calculations = engine
    proposed = _gradations_by_id(gradations)
    items = []
    seen = set()
    for effect in confirmed.get("efeitos_confirmados", []):
        if not isinstance(effect, dict) or not isinstance(effect.get("nome"), str):
            continue
        identifier = canonical_id(effect["nome"])
        if identifier in seen:
            continue
        seen.add(identifier)
        proposal = proposed.get(identifier, {})
        ranks = proposal.get("graduacoes")
        entry = catalog.get(identifier)
        item = {
            "id": identifier,
            "nome": effect["nome"],
            "graduacoes": ranks if type(ranks) is int and ranks > 0 else None,
            "custo_por_graduacao": None,
            "custo_total": None,
            "status": "nao_catalogado",
        }
        if entry is None:
            items.append(item)
            continue
        cost = entry[1].get("custo")
        if type(cost) is not int or cost <= 0:
            item["status"] = "custo_variavel_ou_ausente"
        else:
            item["custo_por_graduacao"] = cost
            if item["graduacoes"] is None:
                item["status"] = "graduacao_indefinida"
            else:
                item["custo_total"] = calculations.custo_componente(
                    cost, item["graduacoes"]
                )
                item["status"] = "calculado_custo_base"
        items.append(item)
    return {
        "disponivel": True,
        "itens": items,
        "total_calculado": sum(item["custo_total"] or 0 for item in items),
        "custos_base_completos": bool(items) and all(
            item["status"] == "calculado_custo_base" for item in items
        ),
        "pendencias": [
            {"id": item["id"], "status": item["status"]}
            for item in items if item["status"] != "calculado_custo_base"
        ],
        "escopo": "Custo base, sem extras, falhas ou validação de limite de NP.",
    }
