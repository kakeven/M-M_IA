"""Indexa os dados JSON no ChromaDB e, opcionalmente, gera resumos."""

import argparse
import json
from typing import Any

from ollama import chat
from unidecode import unidecode

from mm_ia.config import DATA_DIR, OLLAMA_MODEL
from mm_ia.database import get_collections
from mm_ia.prompts.prompt_efeitos_resumidos import PROMPT_RESUMO
from mm_ia.rules_engine import canonical_id

DATA_FILES = {
    "efeito": "efeitos.json",
    "extra": "extras.json",
    "falha": "falhas.json",
    "poder_pronto": "poderes_prontos.json",
}


def normalize_name(name: str) -> str:
    return unidecode(name).strip().lower()


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_as_text(item)}" for key, item in value.items())
    return str(value)


def build_document(kind: str, item: dict[str, Any]) -> str:
    """Converte um registro JSON em texto legível para indexação."""
    lines = [f"Tipo: {kind}", f"Nome: {item.get('nome', '')}"]
    for field in ("categoria", "custo", "acao", "alcance", "duracao", "resistencia"):
        if item.get(field) not in (None, ""):
            lines.append(f"{field.capitalize()}: {_as_text(item[field])}")
    for field in ("descricao", "efeitos", "extras", "falhas", "opcoes", "observacoes"):
        if item.get(field):
            lines.extend([f"\n{field.capitalize()}:", _as_text(item[field])])
    return "\n".join(lines)


def _delete_all(collection: Any) -> None:
    ids = collection.get()["ids"]
    for start in range(0, len(ids), 500):
        collection.delete(ids=ids[start : start + 500])


def index_documents(reset: bool = False) -> int:
    documents_collection, summaries_collection = get_collections()
    if reset:
        _delete_all(documents_collection)
        _delete_all(summaries_collection)

    total = 0
    for kind, filename in DATA_FILES.items():
        path = DATA_DIR / filename
        with path.open(encoding="utf-8") as source:
            records = json.load(source)
        for key, item in records.items():
            record_id = f"{kind}_{key}"
            documents_collection.upsert(
                ids=[record_id],
                documents=[build_document(kind, item)],
                metadatas=[
                    {
                        "tipo": kind,
                        "nome": normalize_name(item["nome"]),
                        "id_canonico": canonical_id(key),
                        # Chroma aceita metadados escalares; a lista completa
                        # de referências fica no JSON privado e é serializada.
                        "fontes_json": json.dumps(
                            item.get("fontes", []), ensure_ascii=False
                        ),
                    }
                ],
            )
            total += 1
    return total


def create_summaries(force: bool = False) -> tuple[int, int]:
    documents_collection, summaries_collection = get_collections()
    source = documents_collection.get(include=["documents", "metadatas"])
    existing = set(summaries_collection.get()["ids"])
    created = skipped = 0

    for record_id, document, metadata in zip(
        source["ids"], source["documents"], source["metadatas"]
    ):
        summary_id = f"resumo_{record_id}"
        if summary_id in existing and not force:
            # Atualiza referências mesmo quando o texto do resumo já existe.
            summaries_collection.update(ids=[summary_id], metadatas=[metadata])
            skipped += 1
            continue
        response = chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": PROMPT_RESUMO},
                {"role": "user", "content": f"Documento:\n{document}"},
            ],
            think=False,
        )
        summaries_collection.upsert(
            ids=[summary_id],
            documents=[response.message.content],
            metadatas=[metadata],
        )
        created += 1
    return created, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="apaga e recria as coleções locais antes de indexar",
    )
    parser.add_argument(
        "--skip-summaries", action="store_true", help="não chama o Ollama para resumir"
    )
    args = parser.parse_args()

    total = index_documents(reset=args.reset)
    print(f"{total} registros indexados.")
    if not args.skip_summaries:
        created, skipped = create_summaries(force=args.reset)
        print(f"{created} resumos gerados; {skipped} já existiam.")


if __name__ == "__main__":
    main()
