"""Input guardrails for Sensia therapy chat (off-topic, crisis, harmful)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

GuardrailAction = Literal["allow", "block"]
GuardrailCategory = Literal["in_scope", "off_topic", "crisis", "harmful"]

_POLICY_PATH = Path(__file__).resolve().parent / "guardrails_policy.json"
_policy_cache: dict | None = None

DEFAULT_OFF_TOPIC = (
    "I'm not able to help with that. I'm here only for emotional support and conversation in this session."
)
DEFAULT_HARMFUL = (
    "I can't assist with that request. This space is for emotional support and safe conversation only."
)
DEFAULT_CRISIS_IN = (
    "I'm really glad you reached out. If you are in crisis or thinking about harming yourself, "
    "please contact emergency services or a crisis line right away: Tele-MANAS 14416 (24/7), "
    "iCall +91-9152987821, Vandrevala Foundation 1860-2662-345 / 1800-233-3330. "
    "You deserve support from a trained human right now."
)


@dataclass(frozen=True)
class GuardrailResult:
    action: GuardrailAction
    category: GuardrailCategory
    reply: str = ""

    @property
    def triggered(self) -> bool:
        return self.action == "block"


def guardrails_enabled() -> bool:
    return os.getenv("SENSIA_GUARDRAILS_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _load_policy() -> dict:
    global _policy_cache
    if _policy_cache is not None:
        return _policy_cache
    if _POLICY_PATH.is_file():
        with open(_POLICY_PATH, encoding="utf-8") as f:
            _policy_cache = json.load(f)
    else:
        _policy_cache = {
            "replies": {"off_topic": DEFAULT_OFF_TOPIC, "harmful": DEFAULT_HARMFUL},
            "crisis_regions": {"IN": DEFAULT_CRISIS_IN},
            "emotional_override_patterns": [],
            "crisis_patterns": [],
            "harmful_patterns": [],
            "off_topic_patterns": [],
            "off_topic_phrases": [],
        }
    return _policy_cache


def _normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.IGNORECASE))
        except re.error:
            continue
    return out


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _has_emotional_override(normalized: str, policy: dict) -> bool:
    patterns = _compile_patterns(policy.get("emotional_override_patterns", []))
    return _matches_any(normalized, patterns)


def _crisis_reply(policy: dict) -> str:
    region = (os.getenv("SENSIA_CRISIS_REGION") or "IN").strip().upper()
    regions = policy.get("crisis_regions", {})
    return regions.get(region) or regions.get("IN") or DEFAULT_CRISIS_IN


def _reply_for(category: GuardrailCategory, policy: dict) -> str:
    replies = policy.get("replies", {})
    if category == "crisis":
        return _crisis_reply(policy)
    if category == "harmful":
        return replies.get("harmful", DEFAULT_HARMFUL)
    return replies.get("off_topic", DEFAULT_OFF_TOPIC)


def evaluate_user_message(text: str) -> GuardrailResult:
    """Classify user input; block with canned reply when out of scope."""
    if not guardrails_enabled():
        return GuardrailResult(action="allow", category="in_scope")

    normalized = _normalize(text)
    if not normalized:
        return GuardrailResult(action="allow", category="in_scope")

    policy = _load_policy()
    emotional = _has_emotional_override(normalized, policy)

    crisis_p = _compile_patterns(policy.get("crisis_patterns", []))
    if _matches_any(normalized, crisis_p):
        return GuardrailResult(
            action="block",
            category="crisis",
            reply=_reply_for("crisis", policy),
        )

    harmful_p = _compile_patterns(policy.get("harmful_patterns", []))
    if _matches_any(normalized, harmful_p):
        return GuardrailResult(
            action="block",
            category="harmful",
            reply=_reply_for("harmful", policy),
        )

    if not emotional:
        for phrase in policy.get("off_topic_phrases", []):
            if phrase.lower() in normalized:
                return GuardrailResult(
                    action="block",
                    category="off_topic",
                    reply=_reply_for("off_topic", policy),
                )

        off_p = _compile_patterns(policy.get("off_topic_patterns", []))
        if _matches_any(normalized, off_p):
            return GuardrailResult(
                action="block",
                category="off_topic",
                reply=_reply_for("off_topic", policy),
            )

    return GuardrailResult(action="allow", category="in_scope")
