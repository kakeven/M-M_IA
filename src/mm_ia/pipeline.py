"""Orquestra as chamadas ao Ollama e o acesso à base local."""

import json
import re
from time import perf_counter
from typing import Any

from ollama import chat
from unidecode import unidecode

from mm_ia.config import OLLAMA_KEEP_ALIVE, OLLAMA_MODEL, OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT
from mm_ia.database import get_collections
from mm_ia.prompts.prompt_RAG import PROMPT_RAG
from mm_ia.prompts.prompt_calcular_efeitos import PROMPT_CALCULAR_EFEITOS
from mm_ia.prompts.prompt_ficha import PROMPT_FICHA
from mm_ia.rules_engine import calculate_proposal, canonical_id, rule_options


def _normalize(value: str) -> str:
    return unidecode(value).strip().lower()


def _verified_sources(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Lê apenas citações cadastradas localmente; nunca pede citações ao modelo."""
    raw_sources = metadata.get("fontes_json", "[]")
    try:
        sources = json.loads(raw_sources) if isinstance(raw_sources, str) else []
    except (TypeError, json.JSONDecodeError):
        return []

    verified = []
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        book = source.get("livro")
        section = source.get("secao")
        printed_page = source.get("pagina_impressa")
        pdf_page = source.get("pagina_pdf")
        if (
            isinstance(book, str)
            and book.strip()
            and isinstance(section, str)
            and section.strip()
            and type(printed_page) is int
            and printed_page > 0
            and type(pdf_page) is int
            and pdf_page > 0
        ):
            verified.append(
                {
                    "livro": book.strip(),
                    "secao": section.strip(),
                    "pagina_impressa": printed_page,
                    "pagina_pdf": pdf_page,
                }
            )
    return verified


def _record_from_result(
    record_id: str,
    document: str | None,
    metadata: dict[str, Any] | None,
    match: str,
    distance: float | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    sources = _verified_sources(metadata)
    record = {
        "id": record_id,
        "id_canonico": metadata.get(
            "id_canonico", canonical_id(str(metadata.get("nome", record_id)))
        ),
        "nome": metadata.get("nome", record_id),
        "tipo": metadata.get("tipo", "desconhecido"),
        "documento": document or "",
        "correspondencia": match,
        "distancia": distance,
        "fontes": sources,
    }
    if not sources:
        record["referencia"] = "Fonte não cadastrada"
    return record


def _ask_json(
    prompt: str, request: str, context: Any = None,
    provider: str = "ollama", model: str | None = None,
    effort: str | None = None,
) -> dict[str, Any]:
    system_prompt = prompt
    if context is not None:
        system_prompt += "\n\nDados de referência:\n" + json.dumps(
            context, ensure_ascii=False
        )
    if provider == "chatgpt":
        from mm_ia.chatgpt_plan import ask_json
        return ask_json(system_prompt, request, model or "", effort)
    if provider != "ollama":
        raise ValueError("Provedor de IA desconhecido.")
    response = chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request},
        ],
        options={
            "temperature": 0,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        },
        format="json",
        think=False,
        keep_alive=OLLAMA_KEEP_ALIVE,
    )
    return json.loads(response.message.content)


def retrieve_summaries(
    request: str,
    suggestions: list[dict[str, Any]],
    semantic_results_per_suggestion: int = 2,
) -> list[dict[str, Any]]:
    """Combina nomes exatos com vizinhos semânticos, priorizando os exatos."""
    _, summaries_collection = get_collections()
    exact_matches: list[dict[str, Any]] = []
    semantic_matches: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    valid = [suggestion for suggestion in suggestions
             if isinstance(suggestion, dict)
             and isinstance(suggestion.get("efeito"), str)
             and float(suggestion.get("relevancia", 1)) >= 0.5]
    exact_names = [_normalize(item["efeito"]) for item in valid]
    if not valid:
        # Na interface rápida, o texto do usuário alimenta diretamente o vetor.
        # Os nomes explícitos ainda recebem prioridade de correspondência exata.
        options = rule_options() or {}
        normalized_request = _normalize(request)
        exact_names = [
            _normalize(item["nome"]) for item in options.get("efeitos", [])
            if re.search(r"(?<!\w)" + re.escape(_normalize(item["nome"]))
                         + r"(?!\w)", normalized_request)
        ]
    for name in dict.fromkeys(exact_names):
        result = summaries_collection.get(
            where={"nome": name}, include=["documents", "metadatas"]
        )
        for record_id, document, metadata in zip(
            result["ids"], result["documents"], result["metadatas"]
        ):
            if record_id not in seen_ids:
                seen_ids.add(record_id)
                exact_matches.append(
                    _record_from_result(record_id, document, metadata, "exata")
                )

    queries = ([f"{request}\nEfeito relacionado: {item['efeito']}" for item in valid]
               if valid else [request])
    result = summaries_collection.query(
        query_texts=queries,
        n_results=semantic_results_per_suggestion if valid else 6,
        include=["documents", "metadatas", "distances"],
    )
    for ids, documents, metadatas, distances in zip(
        result.get("ids", []), result.get("documents", []),
        result.get("metadatas", []), result.get("distances", []),
    ):
        for record_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            if record_id not in seen_ids:
                seen_ids.add(record_id)
                semantic_matches.append(
                    _record_from_result(
                        record_id,
                        document,
                        metadata,
                        "semantica",
                        float(distance) if distance is not None else None,
                    )
                )

    semantic_matches.sort(
        key=lambda item: (
            item["distancia"] if item["distancia"] is not None else float("inf")
        )
    )
    return exact_matches + semantic_matches


def analyze_request(
    request: str, fast: bool = False,
    provider: str = "ollama", model: str | None = None,
    effort: str | None = None,
) -> dict[str, Any]:
    """Executa seleção, recuperação, validação e estimativa de graduações."""
    started = perf_counter()
    selection = ({"consulta_rag": [], "modo": "busca_direta"} if fast
                 else _ask_json(PROMPT_RAG, request, provider=provider, model=model, effort=effort))
    after_selection = perf_counter()
    retrieved = retrieve_summaries(request, selection.get("consulta_rag", []))
    after_retrieval = perf_counter()
    documents = [
        {"nome": item["nome"], "resumo": item["documento"][:1000]}
        for item in retrieved[:6]
    ]
    validation = _ask_json(
        PROMPT_FICHA,
        f"Pedido: {request}\nDocumentos recuperados: {json.dumps(documents, ensure_ascii=False)}",
        provider=provider, model=model, effort=effort,
    )
    after_validation = perf_counter()
    retrieved_ids = {canonical_id(item["nome"]) for item in retrieved[:6]}
    confirmed = [
        item for item in validation.get("efeitos_confirmados", [])
        if isinstance(item, dict)
        and isinstance(item.get("nome"), str)
        and canonical_id(item["nome"]) in retrieved_ids
    ]
    validation["efeitos_confirmados"] = confirmed
    confirmed_ids = {canonical_id(item["nome"]) for item in confirmed}
    concise_rules = [
        {"nome": item["nome"], "resumo": item["documento"][:1000]}
        for item in retrieved if item["id_canonico"] in confirmed_ids
    ][:6]
    gradations = (
        _ask_json(
            PROMPT_CALCULAR_EFEITOS,
            request,
            context={
                "efeitos_confirmados": confirmed,
                "resumos_locais": concise_rules,
            },
            provider=provider, model=model, effort=effort,
        )
        if confirmed else {}
    )
    after_gradations = perf_counter()
    costs = calculate_proposal(validation, gradations)
    return {
        "selecao": selection,
        "documentos_recuperados": retrieved,
        "validacao": validation,
        "graduações": gradations,
        "custos_motor": costs,
        "tempos_segundos": {
            "selecao": round(after_selection - started, 2),
            "busca": round(after_retrieval - after_selection, 2),
            "validacao": round(after_validation - after_retrieval, 2),
            "graduacoes": round(after_gradations - after_validation, 2),
        },
    }
