"""Geração, cálculo e armazenamento local das fichas exibidas na interface."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from mm_ia.config import PROJECT_ROOT
from mm_ia.pipeline import _ask_json, analyze_request
from mm_ia.rules_engine import MOTOR_DIR, canonical_id, load_engine, rule_options

SHEETS_DIR = PROJECT_ROOT / ".local" / "fichas"
SCHEMA_VERSION = 1
MAX_RANK = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any, field: str, limit: int = 500) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} deve ser texto")
    return value.strip()[:limit]


def _integer(value: Any, field: str, minimum: int = 0, maximum: int = MAX_RANK) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{field} deve ser um inteiro entre {minimum} e {maximum}")
    return value


def _engine_parts():
    loaded = load_engine()
    options = rule_options()
    if loaded is None or options is None:
        raise RuntimeError("Motor de regras local não encontrado em 'Motor de regras/'.")
    return loaded[0], loaded[1], options


def catalog_for_ui() -> dict[str, Any]:
    options = rule_options()
    if options is None:
        return {"disponivel": False, "motivo": "Motor de regras local não encontrado."}
    return {"disponivel": True, **options}


def _unique_rows(rows: Any, names: dict[str, str], field: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{field} deve ser uma lista")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Item inválido em {field}")
        identifier = canonical_id(str(row.get("id", row.get("nome", ""))))
        if identifier not in names or identifier in seen:
            raise ValueError(f"Item desconhecido ou repetido em {field}: {identifier}")
        seen.add(identifier)
        result.append({"id": identifier, "nome": names[identifier], "dados": row})
    return result


def normalize_sheet(raw: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Recalcula todos os pontos no motor local; campos calculados do cliente são ignorados."""
    catalog, calculations, options = _engine_parts()
    if not isinstance(raw, dict):
        raise ValueError("Ficha inválida")
    np = _integer(raw.get("np"), "NP", 1, 30)
    abilities_raw = raw.get("habilidades", {})
    if not isinstance(abilities_raw, dict):
        raise ValueError("Habilidades inválidas")
    abilities = {
        name: _integer(abilities_raw.get(name, 0), name)
        for name in options["habilidades"]
    }
    ability_cost = sum(calculations.custo_habilidade(rank) for rank in abilities.values())

    skill_names = {canonical_id(name): name for name in options["pericias"]}
    skills = []
    warnings = []
    for row in _unique_rows(raw.get("pericias", []), skill_names, "perícias"):
        points = _integer(row["dados"].get("pontos", 0), "pontos da perícia")
        ranks = calculations.graduacoes_pericia(points)
        ability = options["pericias"][row["nome"]]
        if ranks > calculations.limite_graduacoes_pericia(np):
            warnings.append(f"{row['nome']}: graduação de perícia acima do limite usado pelo motor.")
        skills.append({
            "id": row["id"], "nome": row["nome"], "pontos": points,
            "graduacoes": ranks, "habilidade": ability,
            "bonus": ranks + abilities[ability],
            "custo": calculations.custo_pericia(points),
        })

    advantage_names = {canonical_id(name): name for name in options["vantagens"]}
    advantages = []
    for row in _unique_rows(raw.get("vantagens", []), advantage_names, "vantagens"):
        rank = _integer(row["dados"].get("graduacao", 0), "graduação da vantagem")
        advantages.append({
            "id": row["id"], "nome": row["nome"], "graduacao": rank,
            "custo": calculations.custo_vantagem(rank),
        })

    effect_names = {identifier: name for identifier, (name, _) in catalog.items()}
    old_sources = {
        row["id"]: row.get("fontes", [])
        for row in (previous or {}).get("poderes", [])
    }
    powers = []
    for row in _unique_rows(raw.get("poderes", []), effect_names, "poderes"):
        data = row["dados"]
        rank = _integer(data.get("graduacao", 0), "graduação do efeito")
        catalog_cost = catalog[row["id"]][1].get("custo")
        fixed_cost = catalog_cost if type(catalog_cost) is int and catalog_cost > 0 else None
        manual = data.get("custo_manual")
        manual = None if manual in (None, "") else _integer(manual, "custo manual", 1, 100)
        base = fixed_cost if fixed_cost is not None else manual
        cost = calculations.custo_componente(base, rank) if rank and base else None
        if rank and base is None:
            warnings.append(f"{row['nome']}: informe o custo base para calcular os pontos.")
        sources = old_sources.get(row["id"], data.get("fontes", []) if previous is None else [])
        powers.append({
            "id": row["id"], "nome": row["nome"], "graduacao": rank,
            "custo_base": fixed_cost, "custo_manual": manual if fixed_cost is None else None,
            "custo": cost if cost is not None else 0,
            "custo_pendente": bool(rank and base is None),
            "motivo": _text(data.get("motivo", ""), "motivo", 300),
            "fontes": sources if isinstance(sources, list) else [],
        })

    budget = calculations.orcamento(np)
    spent = (
        ability_cost + sum(row["custo"] for row in skills)
        + sum(row["custo"] for row in advantages)
        + sum(row["custo"] for row in powers)
    )
    if spent > budget:
        warnings.append(f"A ficha excede o orçamento em {spent - budget} pontos.")
    identifier = (previous or raw).get("id")
    if identifier is None:
        identifier = str(uuid.uuid4())
    identifier = str(uuid.UUID(identifier))
    return {
        "schema_version": SCHEMA_VERSION,
        "id": identifier,
        "nome": _text(raw.get("nome", ""), "nome", 100) or "Novo personagem",
        "jogador": _text(raw.get("jogador", ""), "jogador", 100),
        "descricao": _text(raw.get("descricao", ""), "descrição", 2000),
        "np": np,
        "habilidades": abilities,
        "pericias": skills,
        "vantagens": advantages,
        "poderes": powers,
        "resumo": {
            "orcamento": budget,
            "gastos": spent,
            "restantes": budget - spent,
            "habilidades": ability_cost,
            "pericias": sum(row["custo"] for row in skills),
            "vantagens": sum(row["custo"] for row in advantages),
            "poderes": sum(row["custo"] for row in powers),
            "avisos": warnings,
        },
        "criado_em": (previous or raw).get("criado_em", _now()),
        "atualizado_em": _now(),
    }


def _save(sheet: dict[str, Any]) -> None:
    SHEETS_DIR.mkdir(parents=True, exist_ok=True)
    destination = SHEETS_DIR / f"{sheet['id']}.json"
    temporary = SHEETS_DIR / f".{sheet['id']}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _path_for_new(identifier: str) -> Path:
    try:
        identifier = str(uuid.UUID(identifier))
    except (ValueError, AttributeError) as error:
        raise ValueError("Identificador de ficha inválido") from error
    return SHEETS_DIR / f"{identifier}.json"


def save_changes(identifier: str, raw: dict[str, Any]) -> dict[str, Any]:
    path = _path_for_new(identifier)
    if not path.is_file():
        raise FileNotFoundError("Ficha não encontrada")
    previous = json.loads(path.read_text(encoding="utf-8"))
    if previous.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Esta ficha antiga está disponível somente para leitura")
    sheet = normalize_sheet(raw, previous)
    _save(sheet)
    return sheet


def _positive_model_rank(value: Any) -> int:
    return min(value, MAX_RANK) if type(value) is int and value > 0 else 0


def _model_values(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {canonical_id(str(name)): _positive_model_rank(rank)
            for name, rank in value.items()}


def ai_options(request: dict[str, Any]) -> dict[str, Any]:
    """Valida a escolha do provedor sem persistir credenciais na criação."""
    provider = request.get("provedor", "ollama")
    if provider not in ("ollama", "chatgpt"):
        raise ValueError("Escolha Ollama ou ChatGPT Plus como provedor.")
    model = request.get("modelo")
    effort = request.get("esforco") or None
    if provider == "chatgpt":
        from mm_ia.chatgpt_plan import models
        available = {item["id"] for item in models()}
        if not isinstance(model, str) or model not in available:
            raise ValueError("Escolha um modelo disponível na sua conta ChatGPT.")
        if effort not in (None, "none", "low", "medium", "high", "xhigh", "max"):
            raise ValueError("Esforço de raciocínio inválido.")
    return {"provider": provider, "model": model, "effort": effort}


def generate_sheet(request: dict[str, Any]) -> dict[str, Any]:
    """A IA sugere; o motor limita ao orçamento e recalcula cada custo."""
    started = perf_counter()
    catalog, calculations, options = _engine_parts()
    description = _text(request.get("descricao", ""), "descrição", 2000)
    if not description:
        raise ValueError("Descreva o personagem antes de gerar a ficha")
    np = _integer(request.get("np", 10), "NP", 1, 30)
    ai = ai_options(request)
    provider, model, effort = ai["provider"], ai["model"], ai["effort"]
    try:
        analysis = analyze_request(
            description, fast=True, provider=provider, model=model, effort=effort
        )
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            "Não foi possível consultar a IA e o RAG local. Verifique a conexão escolhida "
            "e a indexação do ChromaDB."
        ) from error
    after_analysis = perf_counter()
    budget = calculations.orcamento(np)
    remaining = budget
    powers = []
    retrieved = {}
    for row in analysis.get("documentos_recuperados", []):
        identifier = row.get("id_canonico")
        if identifier and (identifier not in retrieved or row.get("fontes")):
            retrieved[identifier] = row.get("fontes", [])
    for proposal in analysis.get("custos_motor", {}).get("itens", []):
        identifier = proposal["id"]
        if identifier not in catalog:
            continue
        rank = _positive_model_rank(proposal.get("graduacoes"))
        base = proposal.get("custo_por_graduacao")
        if type(base) is int and base > 0:
            rank = min(rank, remaining // base)
            remaining -= calculations.custo_componente(base, rank) if rank else 0
        motive = analysis.get("graduações", {}).get(proposal["nome"], {})
        powers.append({
            "id": identifier, "nome": catalog[identifier][0], "graduacao": rank,
            "motivo": motive.get("motivo", "") if isinstance(motive, dict) else "",
            "fontes": retrieved.get(identifier, []),
        })

    system_prompt = (
        "Você propõe apenas a distribuição inicial de pontos de uma ficha de personagem. "
        "Use somente os nomes fornecidos. Não invente regras, custos nem fontes. "
        "Responda apenas JSON com: nome_sugerido (texto), habilidades (objeto nome:graduacao), "
        "pericias (objeto nome:pontos_investidos) e vantagens (objeto nome:graduacao). "
        "Todos os números devem ser inteiros não negativos. O orçamento restante para essas "
        "três áreas é informado nos dados; deixe pontos livres quando não houver justificativa."
    )
    context = {
        "pedido": description, "np": np, "pontos_restantes": remaining,
        "habilidades_validas": options["habilidades"],
        "pericias_validas": list(options["pericias"]),
        "vantagens_validas": options["vantagens"],
        "poderes_reservados": [{"nome": p["nome"], "graduacao": p["graduacao"]} for p in powers],
        "custos": options["custos"],
    }
    try:
        allocation = _ask_json(
            system_prompt, json.dumps(context, ensure_ascii=False),
            provider=provider, model=model, effort=effort,
        )
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(
            "A IA não retornou uma distribuição válida. Verifique o modelo e tente novamente."
        ) from error
    if not isinstance(allocation, dict):
        raise RuntimeError("A IA não retornou um objeto de distribuição válido.")
    after_allocation = perf_counter()
    abilities_proposed = _model_values(allocation.get("habilidades"))
    skills_proposed = _model_values(allocation.get("pericias"))
    advantages_proposed = _model_values(allocation.get("vantagens"))
    abilities = {}
    for name in options["habilidades"]:
        wanted = abilities_proposed.get(canonical_id(name), 0)
        rank = min(wanted, remaining // calculations.PONTOS_POR_GRADUACAO_HABILIDADE)
        abilities[name] = rank
        remaining -= calculations.custo_habilidade(rank)
    skills = []
    for name in options["pericias"]:
        wanted = skills_proposed.get(canonical_id(name), 0)
        points = min(wanted, remaining, calculations.limite_graduacoes_pericia(np) // calculations.GRADUACOES_PERICIA_POR_PONTO)
        if points:
            skills.append({"id": canonical_id(name), "pontos": points})
            remaining -= calculations.custo_pericia(points)
    advantages = []
    for name in options["vantagens"]:
        wanted = advantages_proposed.get(canonical_id(name), 0)
        rank = min(wanted, remaining // calculations.PONTOS_POR_GRADUACAO_VANTAGEM)
        if rank:
            advantages.append({"id": canonical_id(name), "graduacao": rank})
            remaining -= calculations.custo_vantagem(rank)

    name = _text(request.get("nome", ""), "nome", 100)
    if not name:
        name = _text(allocation.get("nome_sugerido", ""), "nome sugerido", 100)
    sheet = normalize_sheet({
        "nome": name or "Novo personagem",
        "jogador": _text(request.get("jogador", ""), "jogador", 100),
        "descricao": description,
        "np": np, "habilidades": abilities,
        "pericias": skills, "vantagens": advantages, "poderes": powers,
    })
    _save(sheet)
    print(
        f"Geração da ficha ({provider}): análise RAG/IA "
        f"{after_analysis - started:.1f}s, distribuição "
        f"{after_allocation - after_analysis:.1f}s, total "
        f"{perf_counter() - started:.1f}s. Etapas: {analysis.get('tempos_segundos', {})}",
        flush=True,
    )
    return sheet


def _sheet_item(path: Path, source: str) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        current = source == "local" and data.get("schema_version") == SCHEMA_VERSION
        return {
            "id": f"nova:{data['id']}" if current else f"antiga:{source}:{path.name}",
            "nome": data.get("nome") if current else data.get("nomePersonagem", path.stem),
            "np": data.get("np"), "tipo": "nova" if current else "antiga",
            "atualizado_em": data.get("atualizado_em", ""),
            "ordem": path.stat().st_mtime,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_sheets() -> list[dict[str, Any]]:
    result = []
    for source, directory in (("local", SHEETS_DIR), ("motor", MOTOR_DIR)):
        if directory.is_dir():
            for path in directory.glob("*.json"):
                item = _sheet_item(path, source)
                if item is not None:
                    result.append(item)
    result.sort(key=lambda item: item.pop("ordem"), reverse=True)
    return result


def get_sheet(identifier: str) -> dict[str, Any]:
    if identifier.startswith("nova:"):
        path = _path_for_new(identifier.removeprefix("nova:"))
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Formato de ficha inválido")
        return {"tipo": "nova", "ficha": data}
    parts = identifier.split(":", 2)
    if len(parts) != 3 or parts[0] != "antiga" or parts[1] not in ("local", "motor"):
        raise ValueError("Identificador de ficha inválido")
    filename = parts[2]
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("Nome de ficha inválido")
    directory = SHEETS_DIR if parts[1] == "local" else MOTOR_DIR
    data = json.loads((directory / filename).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Formato de ficha inválido")
    return {"tipo": "antiga", "ficha": data}
