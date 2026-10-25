"""CLI: fetch Hacker News comments, classify AI sentiment, print a report."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict

import hn
from classify import classify, score
from report import Classified, render, summarize

log = hn.log_to_stderr


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stories", type=int, default=30)
    parser.add_argument("--max-comments", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=hn.DEFAULT_WORKERS)
    parser.add_argument("--rate", type=int, default=hn.DEFAULT_RATE)
    args = parser.parse_args()

    log(f"fetching {args.stories} stories with {args.workers} workers at {args.rate} req/s")
    crawler = hn.Crawler(workers=args.workers, rate=args.rate, log=log)
    comments = await crawler.run(await hn.top_story_ids(args.stories), args.max_comments)
    classified = []
    for c in comments:
        label = classify(c.text)
        classified.append(Classified(**asdict(c), label=label, score=0 if label == "unrelated" else score(c.text)))
    print(render(summarize(classified)))
    print(f"\nfetch stats: {crawler.stats}")


if __name__ == "__main__":
    asyncio.run(main())
