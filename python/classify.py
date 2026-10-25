"""Word-list classifier: is a comment about AI, and is it bullish or bearish on it?"""
from __future__ import annotations

import re

# Each entry is a regex, matched as a whole word and ignoring case.
AI_TERMS = [
    r"ai", r"a\.i\.", r"agi", r"llms?", r"gpt-?\w*", r"chatgpt", r"openai", r"anthropic",
    r"claude", r"gemini", r"copilot", r"deepseek", r"machine learning", r"deep learning",
    r"neural net(?:work)?s?", r"language models?", r"foundation models?",
    r"frontier models?", r"agentic", r"vibe.?cod(?:e|ing|ed)",
]

BULLISH = [
    r"game.?chang\w+", r"breakthrough", r"impressive", r"incredible", r"amazing",
    r"remarkable", r"excit(?:ed|ing)", r"productiv\w+", r"10x", r"underrated",
    r"revolution\w*", r"transformative", r"love (?:it|using|this|how)",
    r"works? (?:great|well|surprisingly)", r"better than", r"faster than",
    r"saves? (?:me )?(?:hours|time|days|so much)", r"can'?t live without",
    r"indispensable", r"step change", r"accelerat\w+", r"improv(?:ed|ing|ement)",
    r"useful", r"helpful", r"brilliant", r"insanely good", r"mind.?blowing", r"bullish",
]

BEARISH = [
    r"hype\w*", r"overhyped", r"bubble", r"hallucinat\w*", r"slop", r"useless",
    r"garbage", r"plateau\w*", r"diminishing returns", r"scam", r"hit(?:ting|s)? a wall",
    r"overrated", r"disappoint\w*", r"unreliable", r"worse than", r"regress\w*",
    r"burn(?:ing|s)? (?:cash|money)", r"unprofitable", r"crash", r"waste of",
    r"dead end", r"stochastic parrot", r"grift\w*", r"parlor trick", r"snake oil",
    r"broken", r"buggy", r"mediocre", r"underwhelm\w*", r"nonsense",
    r"not (?:ready|there yet)", r"bearish",
]

NEGATION = re.compile(r"\b(?:not|no|never|hardly|isn'?t|aren'?t|don'?t|doesn'?t|won'?t|can'?t)\b", re.I)
NEGATION_WINDOW = 30  # a negation this many characters before a match flips it


def compile_terms(terms: list[str]) -> re.Pattern[str]:
    return re.compile(rf"\b(?:{'|'.join(terms)})\b", re.I)


AI_RE = compile_terms(AI_TERMS)
BULL_RE = compile_terms(BULLISH)
BEAR_RE = compile_terms(BEARISH)


def is_about_ai(text: str) -> bool:
    return AI_RE.search(text) is not None


def count_matches(text: str, regex: re.Pattern[str]) -> int:
    total = 0
    for match in regex.finditer(text):
        before = text[max(0, match.start() - NEGATION_WINDOW) : match.start()]
        total += -1 if NEGATION.search(before) else 1
    return total


def score(text: str) -> int:
    """Bullish matches minus bearish matches. Above 0 is bullish, below 0 is bearish."""
    return count_matches(text, BULL_RE) - count_matches(text, BEAR_RE)


def classify(text: str) -> str:
    """Returns "bullish", "bearish", "neutral" (about AI but neither) or "unrelated"."""
    if not is_about_ai(text):
        return "unrelated"
    s = score(text)
    if s > 0:
        return "bullish"
    if s < 0:
        return "bearish"
    return "neutral"
