"""Fetches comments from the Hacker News item API (one request per item)."""
from __future__ import annotations

import asyncio
import html
import http.client
import json
import re
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypedDict

HOST = "hacker-news.firebaseio.com"
TIMEOUT_SECONDS = 10

DEFAULT_WORKERS = 8
DEFAULT_RATE = 50  # max requests per second, shared by all workers
MAX_RETRIES = 3
CACHE_SIZE = 50_000


class Item(TypedDict, total=False):
    """A story or comment as the API returns it."""

    id: int
    type: str
    time: int
    text: str
    title: str
    kids: list[int]  # ids of direct replies
    deleted: bool
    dead: bool


@dataclass
class Comment:
    id: int
    time: int
    story_id: int
    story_title: str
    text: str


Logger = Callable[[str], None]
FetchItem = Callable[[int], Awaitable[Optional[Item]]]


def log_to_stderr(message: str) -> None:
    print(message, file=sys.stderr)


_connections = threading.local()


def get_json(path: str):
    """Keeps one connection open per thread, so each request skips the slow HTTPS setup."""
    conn = getattr(_connections, "conn", None) or http.client.HTTPSConnection(HOST, timeout=TIMEOUT_SECONDS)
    _connections.conn = conn
    try:
        conn.request("GET", f"/v0/{path}.json")
        res = conn.getresponse()
        body = res.read()
    except Exception:
        conn.close()
        _connections.conn = None
        raise
    if res.status != 200:
        raise RuntimeError(f"HN API returned {res.status} for {path}")
    return json.loads(body)


async def top_story_ids(limit: int) -> list[int]:
    ids = await asyncio.to_thread(get_json, "topstories")
    return ids[:limit]


async def fetch_item(item_id: int) -> Item | None:
    """Returns None if the id doesn't exist."""
    return await asyncio.to_thread(get_json, f"item/{item_id}")


def clean_text(raw: str) -> str:
    """Turns HN's HTML comment body into plain text."""
    text = raw.replace("<p>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


class RateLimiter:
    """Keeps requests at least `interval` seconds apart, across all workers."""

    def __init__(self, interval: float):
        self.interval = interval
        self.next_slot = 0.0

    async def acquire(self) -> None:
        now = time.monotonic()
        slot = max(now, self.next_slot)
        self.next_slot = slot + self.interval
        if slot > now:
            await asyncio.sleep(slot - now)


class ItemCache:
    """Remembers fetched items so the same id is never requested twice."""

    def __init__(self, max_size: int):
        self.max_size = max_size
        self.items: dict[int, Item | None] = {}

    def has(self, item_id: int) -> bool:
        return item_id in self.items

    def get(self, item_id: int) -> Item | None:
        return self.items[item_id]

    def set(self, item_id: int, item: Item | None) -> None:
        if len(self.items) >= self.max_size:
            oldest = next(iter(self.items))
            del self.items[oldest]
        self.items[item_id] = item


class FetchStats:
    def __init__(self):
        self.requests = 0
        self.retries = 0
        self.failures = 0
        self.cache_hits = 0
        self.started_at = time.monotonic()

    def __str__(self) -> str:
        seconds = time.monotonic() - self.started_at
        per_second = self.requests / max(seconds, 0.001)
        return (
            f"{self.requests} requests ({per_second:.1f}/s), {self.retries} retries, "
            f"{self.failures} failures, {self.cache_hits} cache hits, {seconds:.1f}s"
        )


@dataclass
class Job:
    id: int
    story_id: int


class Crawler:
    """Walks every comment tree using a pool of workers that share one job queue."""

    def __init__(
        self,
        workers: int = DEFAULT_WORKERS,
        rate: float = DEFAULT_RATE,  # requests per second
        fetch_item: FetchItem = fetch_item,  # swapped out in tests
        log: Logger = log_to_stderr,
    ):
        self.stats = FetchStats()
        self.workers = workers
        self.limiter = RateLimiter(1 / rate)
        self.cache = ItemCache(CACHE_SIZE)
        self.fetch_item = fetch_item
        self.log = log
        self.queue: deque[Job] = deque()
        self.results: list[Comment] = []
        self.titles: dict[int, str] = {}
        self.pending = 0
        self.stopped = False

    async def run(self, story_ids: list[int], max_comments: int) -> list[Comment]:
        """Fetches every comment under the given stories and returns them newest first."""
        for story_id in story_ids:
            self.enqueue(Job(story_id, story_id))
        for _ in range(DEFAULT_WORKERS):
            asyncio.create_task(self.worker())
        await self.wait_until_done()
        self.stopped = True
        for c in self.results:
            c.story_title = self.titles.get(c.story_id, "")
        self.results.sort(key=lambda c: c.time, reverse=True)
        return self.results[:max_comments]

    def enqueue(self, job: Job) -> None:
        self.pending += 1
        self.queue.append(job)

    async def wait_until_done(self) -> None:
        """Checks every 50ms and returns once no jobs are pending."""
        while self.pending != 0:
            await asyncio.sleep(0.05)

    async def worker(self) -> None:
        while not self.stopped:
            if not self.queue:
                await asyncio.sleep(0.01)  # queue is empty, check again soon
                continue
            job = self.queue.popleft()
            self.pending -= 1  # picked up by a worker, so no longer pending
            item = await self.fetch_with_retry(job.id)
            if not item or item.get("deleted") or item.get("dead"):
                continue

            if item.get("type") == "story":
                self.titles[item["id"]] = item.get("title", "")
            if item.get("type") == "comment" and "text" in item:
                self.results.append(
                    Comment(
                        id=item["id"],
                        time=item.get("time", 0),
                        story_id=job.story_id,
                        story_title="",
                        text=clean_text(item["text"]),
                    )
                )
                if len(self.results) % 100 == 0:
                    self.log(f"{len(self.results)} comments; {self.stats}")
            for kid in item.get("kids", []):
                self.enqueue(Job(kid, job.story_id))

    async def fetch_with_retry(self, item_id: int) -> Item | None:
        """Fetches one item. Failures are retried with growing waits (0.5s, 1s, 2s)."""
        if self.cache.has(item_id):
            self.stats.cache_hits += 1
            return self.cache.get(item_id)
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            await self.limiter.acquire()
            self.stats.requests += 1
            if attempt > 0:
                self.stats.retries += 1
            try:
                item = await self.fetch_item(item_id)
                self.cache.set(item_id, item)
                return item
            except Exception as err:
                last_error = err
                await asyncio.sleep(0.5 * 2**attempt)
        self.stats.failures += 1
        self.log(f"giving up on item {item_id}: {last_error}")
        return None
