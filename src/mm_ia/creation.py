"""Criação em etapas com propostas separadas das decisões aprovadas."""

from __future__ import annotations

import json
import os
import re
import uuid
from copy import deepcopy
from threading import RLock
from typing import Any
from unidecode import unidecode

from mm_ia.config import PROJECT_ROOT
from mm_ia.pipeline import _ask_json, retrieve_summaries
from mm_ia.prompts.prompt_criacao import AREAS, ETAPAS, PROMPTS
from mm_ia.sheets import (
    _engine_parts, _integer, _now, _save, _text, ai_options, normalize_sheet,
)
from mm_ia.rules_engine import canonical_id

CREATIONS_DIR = PROJECT_ROOT / ".local" / "criacoes"
_LOCK = RLock()
LIMITS = [
    "Poderes: somente custos base; extras e falhas não são aplicados nesta integração.",
    "O motor não verifica todos os limites de NP nem requisitos de vantagens.",
]
NEXT_QUESTION = {
    "habilidades": "Agora vamos às habilidades. Quais características devem se destacar?",
    "pericias": "Vamos escolher as perícias. Em que atividades o personagem é treinado?",
    "vantagens": "Quais vantagens combinam com o jeito de agir desse herói?",
    "poderes": "Chegamos aos poderes. Como eles funcionam na história?",
    "revisao": "Vamos revisar a ficha. O que você quer conferir antes de finalizar?",
}


class CreationConflict(ValueError):
    """Uma operação tentou usar uma revisão que já foi substituída."""


def _path(identifier: str):
    try:
        identifier = str(uuid.UUID(identifier))
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError("Identificador de criação inválido") from error
    return CREATIONS_DIR / f"{identifier}.json"


def get_creation(identifier: str) -> dict[str, Any]:
    state = json.loads(_path(identifier).read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise ValueError("Formato de criação inválido")
    return state


def _persist(state: dict[str, Any]) -> dict[str, Any]:
    CREATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(state["id"])
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp")
    state["atualizado_em"] = _now()
    try:
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return state


def list_creations() -> list[dict[str, Any]]:
    result = []
    for path in CREATIONS_DIR.glob("*.json"):
        state = get_creation(path.stem)
        result.append({
            "id": state["id"], "nome": state["ficha"]["nome"],
            "etapa_atual": state["etapa_atual"], "status": state["status"],
            "revisao": state["revisao"], "atualizado_em": state["atualizado_em"],
        })
    return sorted(result, key=lambda row: row["atualizado_em"], reverse=True)


def start_creation(request: dict[str, Any]) -> dict[str, Any]:
    description = _text(request.get("descricao", ""), "descrição", 2000)
    if not description:
        raise ValueError("Descreva o personagem antes de iniciar a criação")
    sheet = normalize_sheet({
        "nome": _text(request.get("nome", ""), "nome", 100),
        "jogador": _text(request.get("jogador", ""), "jogador", 100),
        "descricao": description, "np": _integer(request.get("np", 10), "NP", 1, 30),
    })
    state = {
        "schema_version": 1, "id": str(uuid.uuid4()), "revisao": 0,
        "status": "em_criacao", "etapa_atual": "conceito",
        "pedido_original": description, "nome_informado": bool(request.get("nome", "").strip()),
        "ia": ai_options(request), "conceito": None,
        "reservas": dict.fromkeys(AREAS, 0), "ficha": sheet,
        "etapas": {stage: {"status": "pendente"} for stage in ETAPAS},
        "proposta": None, "historico": [], "pendencias": [], "limites_validacao": LIMITS,
        "mensagens": [
            {"papel": "usuario", "texto": description, "etapa": "conceito"},
            {"papel": "assistente", "texto": "Vamos começar pelo conceito. Conte o que é essencial neste herói ou peça uma primeira proposta.", "etapa": "conceito"},
        ],
        "criado_em": _now(),
    }
    return _persist(state)


def _check_revision(state: dict[str, Any], revision: int) -> None:
    if type(revision) is not int or revision != state["revisao"]:
        raise CreationConflict("A criação foi atualizada. Recarregue o estado antes de continuar.")
    if state["status"] != "em_criacao":
        raise ValueError("Esta criação já foi finalizada.")


def _check_stage(state: dict[str, Any], stage: str) -> None:
    if stage not in ETAPAS:
        raise ValueError("Etapa de criação desconhecida")
    if any(state["etapas"][previous]["status"] != "aprovada"
           for previous in ETAPAS[:ETAPAS.index(stage)]):
        raise ValueError("Aprove as etapas anteriores antes de propor esta etapa.")


def _stage_limit(state: dict[str, Any], stage: str) -> int:
    if stage not in AREAS:
        return 0
    index = AREAS.index(stage)
    spent_before = sum(state["ficha"]["resumo"][area] for area in AREAS[:index])
    reserved_after = sum(state["reservas"][area] for area in AREAS[index + 1:])
    return max(0, state["ficha"]["resumo"]["orcamento"] - spent_before - reserved_after)


def _context(state: dict[str, Any], stage: str, instruction: str) -> dict[str, Any]:
    _, calculations, options = _engine_parts()
    context = {
        "etapa": stage, "pedido_original": state["pedido_original"],
        "instrucao_atual": instruction, "conceito_aprovado": state["conceito"],
        "ficha_aprovada": state["ficha"],
        "decisoes_anteriores": {
            name: {"instrucao": data["instrucao"],
                   "justificativa": data["dados"]["justificativa"],
                   "pendencias": data["dados"]["pendencias"]}
            for name, data in state["etapas"].items() if data["status"] == "aprovada"
        },
        "orcamento": {"total": state["ficha"]["resumo"]["orcamento"],
                      "gastos_conhecidos": state["ficha"]["resumo"]["gastos"],
                      "custos_completos": not any(row["custo_pendente"]
                                                 for row in state["ficha"]["poderes"]),
                      "reservas": state["reservas"]},
        "limite_pontos_etapa": _stage_limit(state, stage),
        "custos": options["custos"], "limites_validacao": LIMITS,
        "reformular_invalida_etapas_seguintes": True,
        "pendencias_aprovadas": state["pendencias"],
        "conversa_recente": state.get("mensagens", [])[-12:],
    }
    if state["proposta"] is not None and state["proposta"]["etapa"] == stage:
        context["proposta_anterior"] = state["proposta"]["dados"]
    if stage == "habilidades":
        context["habilidades_validas"] = options["habilidades"]
    elif stage == "pericias":
        context["pericias_validas"] = options["pericias"]
        context["limite_pontos_por_pericia"] = (
            calculations.limite_graduacoes_pericia(state["ficha"]["np"])
            // calculations.GRADUACOES_PERICIA_POR_PONTO
        )
    elif stage == "vantagens":
        context["vantagens_validas"] = options["vantagens"]
    elif stage == "poderes":
        context["efeitos_validos"] = options["efeitos"]
    return context


def _power_context(state: dict[str, Any], stage: str, instruction: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Recupera somente efeitos pertinentes à decisão atual, desde o conceito."""
    catalog, _, _ = _engine_parts()
    concept = state.get("conceito") or {}
    capabilities = concept.get("capacidades_essenciais", [])
    parts = [instruction, *capabilities] if capabilities else [instruction or state["pedido_original"]]
    query = unidecode(" ".join(part for part in parts if isinstance(part, str))).lower()
    query = re.sub(r"\b(voa|voando|voador|voar)\b", "voar", query)
    query = re.sub(r"\b(heroi|heroina|personagem|quero|capaz|poder|poderes|que|de|da|do|um|uma|com)\b", " ", query)
    query = re.sub(r"\s+", " ", query).strip()[:400]
    if not query:
        query = state["pedido_original"][:400]
    limit = 6 if stage == "poderes" else 4
    rules = []
    seen = set()
    for row in retrieve_summaries(query, []):
        identifier = canonical_id(row.get("nome", ""))
        if identifier in catalog and identifier not in seen and row.get("documento", "").strip():
            rules.append(row)
            seen.add(identifier)
            if len(rules) == limit:
                break
    excerpt = 1500 if stage == "poderes" else 850
    concise = [{"nome": row["nome"], "resumo": row["documento"][:excerpt]}
               for row in rules]
    return rules, concise


def _texts(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 30:
        raise ValueError(f"{field} deve ser uma lista com até 30 textos")
    return [_text(item, field, 500) for item in value]


def _distribution(value: Any, names: list[str]) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("A IA deve retornar uma distribuição por nome")
    allowed = {canonical_id(name): name for name in names}
    result = {}
    for name, rank in value.items():
        identifier = canonical_id(name)
        if identifier not in allowed or allowed[identifier] in result:
            raise ValueError(f"Nome desconhecido ou repetido na proposta: {name}")
        result[allowed[identifier]] = _integer(rank, name)
    return result


def _validated_data(stage: str, response: Any, state: dict[str, Any], rules: list) -> dict:
    if not isinstance(response, dict):
        raise ValueError("A IA deve retornar um objeto JSON")
    data = {"justificativa": _text(response.get("justificativa"), "justificativa", 2000),
            "pendencias": _texts(response.get("pendencias"), "pendências")}
    catalog, _, options = _engine_parts()
    if stage == "conceito":
        concept = response.get("conceito")
        if not isinstance(concept, dict):
            raise ValueError("A IA deve retornar o conceito estruturado")
        data["conceito"] = {
            key: _text(concept.get(key), key, 1000)
            for key in ("nome_sugerido", "resumo", "estilo")
        }
        data["conceito"].update({
            key: _texts(concept.get(key), key)
            for key in ("prioridades", "capacidades_essenciais", "suposicoes")
        })
        reserves = response.get("reservas")
        if not isinstance(reserves, dict):
            raise ValueError("Informe reservas para as quatro áreas")
        total = state["ficha"]["resumo"]["orcamento"]
        data["reservas"] = {area: _integer(reserves.get(area), area, 0, total) for area in AREAS}
        if sum(data["reservas"].values()) > total:
            raise ValueError("As reservas propostas ultrapassam o orçamento total")
    elif stage in AREAS[:3]:
        data[stage] = _distribution(response.get(stage), list(options[stage]))
    elif stage == "poderes":
        powers = response.get("poderes")
        if not isinstance(powers, list):
            raise ValueError("Poderes devem ser uma lista")
        references = {}
        for row in rules:
            identifier = canonical_id(row["nome"])
            if identifier not in references or row.get("fontes"):
                references[identifier] = row.get("fontes", [])
        seen = set()
        data[stage] = []
        for row in powers:
            if not isinstance(row, dict) or not isinstance(row.get("nome"), str):
                raise ValueError("Poder inválido na proposta")
            identifier = canonical_id(row["nome"])
            if identifier not in catalog or identifier not in references or identifier in seen:
                raise ValueError("Poder desconhecido, repetido ou sem resumo local recuperado")
            seen.add(identifier)
            data[stage].append({
                "id": identifier, "graduacao": _integer(row.get("graduacao"), "graduação", 1),
                "motivo": _text(row.get("motivo"), "motivo", 300),
                # Fontes vêm exclusivamente do RAG local, jamais da resposta da IA.
                "fontes": references[identifier],
            })
    else:
        data["coerencia"] = _text(response.get("coerencia"), "coerência", 2000)
        adjustments = response.get("ajustes_sugeridos")
        if not isinstance(adjustments, list) or len(adjustments) > 30:
            raise ValueError("Ajustes sugeridos devem ser uma lista com até 30 itens")
        data["ajustes_sugeridos"] = []
        for row in adjustments:
            if not isinstance(row, dict) or row.get("etapa") not in ETAPAS[:-1]:
                raise ValueError("Etapa inválida nos ajustes sugeridos")
            data["ajustes_sugeridos"].append({
                "etapa": row["etapa"], "motivo": _text(row.get("motivo"), "motivo", 500),
            })
    return data


def _candidate(state: dict[str, Any], stage: str, data: dict[str, Any]) -> dict[str, Any]:
    sheet = deepcopy(state["ficha"])
    # A aprovação de uma etapa anterior exige reconstruir suas dependências.
    for later in ETAPAS[ETAPAS.index(stage) + 1:]:
        if later in AREAS:
            sheet[later] = {} if later == "habilidades" else []
    if stage == "conceito":
        if not state["nome_informado"]:
            sheet["nome"] = data["conceito"]["nome_sugerido"]
    elif stage == "habilidades":
        sheet[stage] = data[stage]
    elif stage in ("pericias", "vantagens"):
        field = "pontos" if stage == "pericias" else "graduacao"
        sheet[stage] = [{"id": canonical_id(name), field: value}
                        for name, value in data[stage].items() if value]
    elif stage == "poderes":
        sheet[stage] = data[stage]
    candidate = normalize_sheet(sheet)
    if stage in AREAS and candidate["resumo"][stage] > _stage_limit(state, stage):
        raise ValueError("A proposta ultrapassa os pontos disponíveis para a etapa. Peça uma redistribuição.")
    if stage == "pericias":
        _, calculations, _ = _engine_parts()
        if any(row["graduacoes"] > calculations.limite_graduacoes_pericia(sheet["np"])
               for row in candidate[stage]):
            raise ValueError("A proposta ultrapassa o limite de perícia usado pelo motor")
    return candidate


def propose_stage(identifier: str, request: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state = get_creation(identifier)
        _check_revision(state, request.get("revisao"))
        stage = request.get("etapa", state["etapa_atual"])
        _check_stage(state, stage)
    instruction = _text(request.get("instrucao", ""), "instrução", 2000)
    context = _context(state, stage, instruction)
    rules = []
    try:
        if stage != "revisao":
            try:
                rules, context["regras_recuperadas"] = _power_context(state, stage, instruction)
            except Exception:
                if stage == "poderes":
                    raise
                context["regras_recuperadas"] = []
                context["regras_indisponiveis"] = True
        response = _ask_json(PROMPTS[stage], instruction or state["pedido_original"],
                             context=context, **state["ia"])
    except (ValueError, RuntimeError):
        raise
    except Exception as error:
        raise RuntimeError(
            f"Não foi possível gerar a etapa {stage}. Confira o provedor e, para poderes, o RAG local."
        ) from error
    data = _validated_data(stage, response, state, rules)
    candidate = _candidate(state, stage, data)
    with _LOCK:
        current = get_creation(identifier)
        _check_revision(current, state["revisao"])
        current["proposta"] = {
            "etapa": stage, "instrucao": instruction, "dados": data,
            "ficha_previa": candidate, "limite_pontos": _stage_limit(state, stage),
            "etapas_a_refazer": list(ETAPAS[ETAPAS.index(stage) + 1:]),
        }
        current.setdefault("mensagens", []).extend([
            {"papel": "usuario", "texto": instruction or "Faça uma proposta para esta etapa.", "etapa": stage},
            {"papel": "assistente", "texto": data["justificativa"], "etapa": stage},
        ])
        current["revisao"] += 1
        return _persist(current)


def approve_stage(identifier: str, request: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state = get_creation(identifier)
        _check_revision(state, request.get("revisao"))
        proposal = state["proposta"]
        if proposal is None:
            raise ValueError("Não há proposta para aprovar")
        stage, data = proposal["etapa"], proposal["dados"]
        _check_stage(state, stage)
        state["ficha"] = _candidate(state, stage, data)
        if stage == "conceito":
            state["conceito"], state["reservas"] = data["conceito"], data["reservas"]
        state["etapas"][stage] = {
            "status": "aprovada", "instrucao": proposal["instrucao"], "dados": data,
        }
        for later in ETAPAS[ETAPAS.index(stage) + 1:]:
            state["etapas"][later] = {"status": "pendente"}
        state["pendencias"] = list(dict.fromkeys(
            warning for decision in state["etapas"].values() if decision["status"] == "aprovada"
            for warning in decision["dados"]["pendencias"]
        ))
        state["etapa_atual"] = next(
            (name for name in ETAPAS if state["etapas"][name]["status"] != "aprovada"),
            "concluida",
        )
        state["historico"].append({
            "etapa": stage, "instrucao": proposal["instrucao"], "dados": deepcopy(data),
            "revisao": state["revisao"] + 1, "aprovado_em": _now(),
        })
        state["proposta"] = None
        state.setdefault("mensagens", []).append({
            "papel": "assistente", "texto": NEXT_QUESTION.get(
                state["etapa_atual"],
                "Todas as etapas foram aprovadas. Revise a ficha antes de finalizar.",
            ), "etapa": stage,
        })
        state["revisao"] += 1
        return _persist(state)


def edit_creation_sheet(identifier: str, request: dict[str, Any]) -> dict[str, Any]:
    """Salva edições manuais e refaz etapas que dependem da área alterada."""
    with _LOCK:
        state = get_creation(identifier)
        _check_revision(state, request.get("revisao"))
        raw = request.get("ficha")
        if not isinstance(raw, dict):
            raise ValueError("Envie a ficha editada")
        old = state["ficha"]
        sheet = normalize_sheet(raw, old)
        changed = [area for area in AREAS if sheet[area] != old[area]]
        identity_changed = any(sheet[key] != old[key] for key in ("nome", "jogador", "descricao", "np"))
        if not changed and not identity_changed:
            return state
        if sheet["np"] != old["np"]:
            state["reservas"] = dict.fromkeys(AREAS, 0)
            state["conceito"] = None
            state["etapas"] = {stage: {"status": "pendente"} for stage in ETAPAS}
            state["etapa_atual"] = "conceito"
            for area in AREAS:
                sheet[area] = {} if area == "habilidades" else []
            sheet = normalize_sheet(sheet, old)
        elif changed:
            first = min(changed, key=AREAS.index)
            index = ETAPAS.index(first)
            if any(state["etapas"][earlier]["status"] != "aprovada" for earlier in ETAPAS[:index]):
                raise ValueError("Conclua as etapas anteriores antes de editar esta área")
            for later in ETAPAS[index + 1:]:
                state["etapas"][later] = {"status": "pendente"}
                if later in AREAS:
                    sheet[later] = {} if later == "habilidades" else []
            sheet = normalize_sheet(sheet, old)
            state["etapa_atual"] = first if state["etapas"][first]["status"] != "aprovada" else ETAPAS[index + 1]
            if state["etapas"][first]["status"] == "aprovada":
                record = state["etapas"][first]
                record["instrucao"] = "Ajustado manualmente na ficha"
                record["dados"]["justificativa"] = record["instrucao"]
                record["dados"]["pendencias"] = []
                if first == "habilidades":
                    record["dados"][first] = sheet[first]
                elif first in ("pericias", "vantagens"):
                    key = "pontos" if first == "pericias" else "graduacao"
                    record["dados"][first] = {row["nome"]: row[key] for row in sheet[first]}
                else:
                    record["dados"][first] = sheet[first]
            state["pendencias"] = list(dict.fromkeys(
                warning for decision in state["etapas"].values()
                if decision["status"] == "aprovada"
                for warning in decision["dados"]["pendencias"]
            ))
        if sheet["nome"] != old["nome"]:
            state["nome_informado"] = True
        if sheet["descricao"] != old["descricao"]:
            state["pedido_original"] = sheet["descricao"]
        state["ficha"] = sheet
        state["proposta"] = None
        state.setdefault("mensagens", []).append({
            "papel": "sistema", "texto": (
                "Ficha ajustada e recalculada. As etapas seguintes foram reabertas."
                if changed or sheet["np"] != old["np"] else
                "Identidade atualizada na ficha."
            ),
            "etapa": state["etapa_atual"],
        })
        state["revisao"] += 1
        return _persist(state)


def finish_creation(identifier: str, request: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state = get_creation(identifier)
        _check_revision(state, request.get("revisao"))
        if state["etapa_atual"] != "concluida" or state["proposta"] is not None:
            raise ValueError("Aprove todas as etapas e resolva a proposta aberta antes de finalizar")
        sheet = normalize_sheet(state["ficha"])
        if sheet["resumo"]["restantes"] < 0:
            raise ValueError("A ficha ultrapassa o orçamento total")
        # A revisão narrativa não comprova todas as regras ausentes no motor.
        state["validacao_completa"] = False
        state["ficha"] = sheet
        _save(sheet)
        state["status"] = "finalizada"
        state["revisao"] += 1
        return _persist(state)
