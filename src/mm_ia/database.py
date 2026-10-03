"""Acesso às coleções ChromaDB, criado sob demanda."""

from functools import lru_cache

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from mm_ia.config import CHROMA_PATH, EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_collections():
    """Retorna as coleções de documentos e resumos, sem efeitos no import."""
    embedding_function = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    documents = client.get_or_create_collection(
        name="mutantes_malfeitores",
        embedding_function=embedding_function,
    )
    summaries = client.get_or_create_collection(
        name="efeitos_resumidos",
        embedding_function=embedding_function,
    )
    return documents, summaries
