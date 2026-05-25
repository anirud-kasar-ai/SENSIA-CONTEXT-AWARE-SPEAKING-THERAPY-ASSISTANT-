"""Tests for sensia_guardrails (no Groq / Redis required)."""

from __future__ import annotations

import pytest

from sensia_guardrails import (
    DEFAULT_OFF_TOPIC,
    evaluate_user_message,
    guardrails_enabled,
)


@pytest.fixture(autouse=True)
def enable_guardrails(monkeypatch):
    monkeypatch.setenv("SENSIA_GUARDRAILS_ENABLED", "1")


def test_prime_minister_blocked():
    r = evaluate_user_message("Who is the prime minister?")
    assert r.action == "block"
    assert r.category == "off_topic"
    assert r.reply == DEFAULT_OFF_TOPIC
    assert "prime minister" not in r.reply.lower()
    assert "modi" not in r.reply.lower()


def test_in_scope_anxiety_allowed():
    r = evaluate_user_message("I feel anxious about work")
    assert r.action == "allow"
    assert r.category == "in_scope"


def test_emotional_about_election_allowed():
    r = evaluate_user_message("I feel stressed about the election and my family")
    assert r.action == "allow"
    assert r.category == "in_scope"


def test_crisis_india_default(monkeypatch):
    monkeypatch.setenv("SENSIA_CRISIS_REGION", "IN")
    r = evaluate_user_message("I want to kill myself")
    assert r.action == "block"
    assert r.category == "crisis"
    assert "14416" in r.reply or "Tele-MANAS" in r.reply


def test_crisis_us_region(monkeypatch):
    monkeypatch.setenv("SENSIA_CRISIS_REGION", "US")
    r = evaluate_user_message("I want to kill myself")
    assert r.action == "block"
    assert r.category == "crisis"
    assert "988" in r.reply


def test_guardrails_disabled(monkeypatch):
    monkeypatch.setenv("SENSIA_GUARDRAILS_ENABLED", "0")
    r = evaluate_user_message("Who is the prime minister?")
    assert r.action == "allow"


def test_guardrails_enabled_default():
    assert guardrails_enabled() is True
