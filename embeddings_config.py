"""Local sentence-transformers embeddings for Chroma (replaces OpenAI embeddings)."""

from __future__ import annotations

import sensia_bootstrap  # noqa: F401

from typing import Optional

from langchain_huggingface import HuggingFaceEmbeddings

EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"

_embedding_instance: Optional[HuggingFaceEmbeddings] = None


def get_embedding_model() -> HuggingFaceEmbeddings:
    """Singleton — avoids reloading the HF model on every Streamlit rerun."""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL_NAME,
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embedding_instance
