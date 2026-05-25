"""Groq chat LLM (LangChain). Uses GROQ_API_KEY from environment."""

from __future__ import annotations

import os

from langchain_groq import ChatGroq

# Default: strong general model on Groq; override with env GROQ_MODEL
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def get_chat_llm(temperature: float = 0.3) -> ChatGroq:
    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    return ChatGroq(model=model, temperature=temperature)
