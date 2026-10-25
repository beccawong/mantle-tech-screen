"""Turns labeled comments into a short report for traders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Hashable

from hn import Comment

BUCKET_SECONDS = 6 * 3600  # trend is shown in 6-hour blocks
TOP_THREADS = 5
EXAMPLES = 3
LABELS = ["bullish", "bearish", "neutral", "unrelated"]


@dataclass
class Classified(Comment):
    label: str
    score: int


@dataclass
class Summary:
    total: int
    counts: dict[str, int]
    net: float
    window: tuple[int, int] | None
    trend: list[dict]  # {"bucket", "net", "n"}
    threads: list[dict]  # {"title", "net", "n"}
    bullish_examples: list[Classified]
    bearish_examples: list[Classified]


def empty_counts() -> dict[str, int]:
    return {label: 0 for label in LABELS}


def net_score(counts: dict[str, int]) -> float:
    """From -1 (all bearish) to +1 (all bullish). Ignores neutral and unrelated comments."""
    directional = counts["bullish"] + counts["bearish"]
    return (counts["bullish"] - counts["bearish"]) / directional if directional else 0.0


def count_by_group(comments: list[Classified], group_of: Callable[[Classified], Hashable]) -> dict:
    """Counts labels per group, e.g. per story or per time block."""
    groups: dict = {}
    for c in comments:
        counts = groups.setdefault(group_of(c), empty_counts())
        counts[c.label] += 1
    return groups


def summarize(comments: list[Classified]) -> Summary:
    counts = empty_counts()
    for c in comments:
        counts[c.label] += 1
    ai = [c for c in comments if c.label != "unrelated"]
    titles = {c.story_id: c.story_title for c in ai}

    def block_start(c: Classified) -> int:
        return c.time - (c.time % BUCKET_SECONDS)

    trend = [
        {"bucket": bucket, "net": net_score(cnt), "n": cnt["bullish"] + cnt["bearish"]}
        for bucket, cnt in sorted(count_by_group(ai, block_start).items())
    ]

    threads = [
        {
            "title": titles.get(story_id, ""),
            "net": net_score(cnt),
            "n": cnt["bullish"] + cnt["bearish"] + cnt["neutral"],
        }
        for story_id, cnt in count_by_group(ai, lambda c: c.story_id).items()
    ]
    threads.sort(key=lambda t: t["n"], reverse=True)

    ranked = sorted(ai, key=lambda c: c.score)  # most bearish first
    times = [c.time for c in comments]

    return Summary(
        total=len(comments),
        counts=counts,
        net=net_score(counts),
        window=(min(times), max(times)) if comments else None,
        trend=trend,
        threads=threads[:TOP_THREADS],
        bullish_examples=[c for c in reversed(ranked) if c.score > 0][:EXAMPLES],
        bearish_examples=[c for c in ranked if c.score < 0][:EXAMPLES],
    )


def ts(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def pct(n: int, total: int) -> str:
    return f"{100 * n / total:5.1f}%"


def snippet(comment: Classified, width: int = 110) -> str:
    text = " ".join(comment.text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def render(summary: Summary) -> str:
    total, counts, window = summary.total, summary.counts, summary.window
    if not total or not window:
        return "No comments fetched."
    ai_total = total - counts["unrelated"]
    lines = [f"HN AI sentiment: {total} comments, {ts(window[0])} to {ts(window[1])} UTC", ""]
    for label in LABELS:
        lines.append(f"  {label:<10}{counts[label]:>6}  ({pct(counts[label], total)})")
    lines += [
        "",
        f"net sentiment: {summary.net:+.2f}   (bullish - bearish) / (bullish + bearish), range -1..+1",
        f"AI share of conversation: {100 * ai_total / total:.1f}%",
        "",
        "trend (6h buckets: net score, directional comments):",
        *(f"  {ts(t['bucket'])}  {t['net']:+.2f}  (n={t['n']})" for t in summary.trend),
        "",
        "most discussed AI threads:",
        *(f"  {t['net']:+.2f}  (n={t['n']})  {t['title']}" for t in summary.threads),
        "",
        "strongest bullish:",
        *(f"  [{c.score:+d}] {snippet(c)}" for c in summary.bullish_examples),
        "",
        "strongest bearish:",
        *(f"  [{c.score:+d}] {snippet(c)}" for c in summary.bearish_examples),
    ]
    return "\n".join(lines)
