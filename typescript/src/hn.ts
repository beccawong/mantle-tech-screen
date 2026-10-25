/** Fetches comments from the Hacker News item API (one request per item). */

const BASE_URL = "https://hacker-news.firebaseio.com/v0";
const TIMEOUT_MS = 10_000;

export const DEFAULT_WORKERS = 8;
export const DEFAULT_RATE = 50; // max requests per second, shared by all workers
const MAX_RETRIES = 3;
const CACHE_SIZE = 50_000;

/** A story or comment as the API returns it. */
export interface Item {
  id: number;
  type?: string;
  time?: number;
  text?: string;
  title?: string;
  kids?: number[]; // ids of direct replies
  deleted?: boolean;
  dead?: boolean;
}

export interface Comment {
  id: number;
  time: number;
  storyId: number;
  storyTitle: string;
  text: string;
}

export type Logger = (message: string) => void;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}/${path}.json`, { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new Error(`HN API returned ${res.status} for ${path}`);
  return (await res.json()) as T;
}

export async function topStoryIds(limit: number): Promise<number[]> {
  return (await getJson<number[]>("topstories")).slice(0, limit);
}

/** Returns null if the id doesn't exist. */
export function fetchItem(id: number): Promise<Item | null> {
  return getJson<Item | null>(`item/${id}`);
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function decodeEntity(match: string, code: string): string {
  if (code[0] !== "#") return ENTITIES[code.toLowerCase()] ?? match;
  const isHex = code[1].toLowerCase() === "x";
  return String.fromCodePoint(isHex ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10));
}

/** Turns HN's HTML comment body into plain text. */
export function cleanText(html: string): string {
  return html
    .replace(/<p>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, decodeEntity)
    .trim();
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Keeps requests at least `intervalMs` apart, across all workers. */
export class RateLimiter {
  private nextSlot = 0;
  private readonly intervalMs: number;

  constructor(intervalMs: number) {
    this.intervalMs = intervalMs;
  }

  async acquire(): Promise<void> {
    const now = Date.now();
    const slot = Math.max(now, this.nextSlot);
    this.nextSlot = slot + this.intervalMs;
    if (slot > now) await sleep(slot - now);
  }
}

/** Remembers fetched items so the same id is never requested twice. */
export class ItemCache {
  private readonly items = new Map<number, Item | null>();
  private readonly maxSize: number;

  constructor(maxSize: number) {
    this.maxSize = maxSize;
  }

  get(id: number): Item | null | undefined {
    return this.items.get(id);
  }

  set(id: number, item: Item | null): void {
    if (this.items.size >= this.maxSize) {
      const oldest = this.items.keys().next().value as number;
      this.items.delete(oldest);
    }
    this.items.set(id, item);
  }
}

export class FetchStats {
  requests = 0;
  retries = 0;
  failures = 0;
  cacheHits = 0;
  private readonly startedAt = Date.now();

  toString(): string {
    const seconds = (Date.now() - this.startedAt) / 1000;
    const perSecond = this.requests / Math.max(seconds, 0.001);
    return `${this.requests} requests (${perSecond.toFixed(1)}/s), ${this.retries} retries, ${this.failures} failures, ${this.cacheHits} cache hits, ${seconds.toFixed(1)}s`;
  }
}

export interface CrawlerOptions {
  workers?: number;
  rate?: number; // requests per second
  fetchItem?: (id: number) => Promise<Item | null>; // swapped out in tests
  log?: Logger;
}

interface Job {
  id: number;
  storyId: number;
}

/** Walks every comment tree using a pool of workers that share one job queue. */
export class Crawler {
  readonly stats = new FetchStats();
  private readonly workers: number;
  private readonly limiter: RateLimiter;
  private readonly cache = new ItemCache(CACHE_SIZE);
  private readonly fetchItem: (id: number) => Promise<Item | null>;
  private readonly log: Logger;
  private readonly queue: Job[] = [];
  private readonly results: Comment[] = [];
  private readonly titles = new Map<number, string>();
  private pending = 0;
  private stopped = false;

  constructor(options: CrawlerOptions = {}) {
    this.workers = options.workers ?? DEFAULT_WORKERS;
    this.limiter = new RateLimiter(1000 / (options.rate ?? DEFAULT_RATE));
    this.fetchItem = options.fetchItem ?? fetchItem;
    this.log = options.log ?? console.error;
  }

  /** Fetches every comment under the given stories and returns them newest first. */
  async run(storyIds: number[], maxComments: number): Promise<Comment[]> {
    for (const id of storyIds) this.enqueue({ id, storyId: id });
    for (let i = 0; i < DEFAULT_WORKERS; i++) void this.worker();
    await this.waitUntilDone();
    this.stopped = true;
    for (const c of this.results) c.storyTitle = this.titles.get(c.storyId) ?? "";
    return this.results.sort((a, b) => b.time - a.time).slice(0, maxComments);
  }

  private enqueue(job: Job): void {
    this.pending += 1;
    this.queue.push(job);
  }

  /** Checks every 50ms and resolves once no jobs are pending. */
  private waitUntilDone(): Promise<void> {
    return new Promise((resolve) => {
      const timer = setInterval(() => {
        if (this.pending === 0) {
          clearInterval(timer);
          resolve();
        }
      }, 50);
    });
  }

  private async worker(): Promise<void> {
    while (!this.stopped) {
      const job = this.queue.shift();
      if (!job) {
        await sleep(10); // queue is empty, check again soon
        continue;
      }
      this.pending -= 1; // picked up by a worker, so no longer pending
      const item = await this.fetchWithRetry(job.id);
      if (!item || item.deleted || item.dead) continue;

      if (item.type === "story") this.titles.set(item.id, item.title ?? "");
      if (item.type === "comment" && item.text !== undefined) {
        this.results.push({
          id: item.id,
          time: item.time ?? 0,
          storyId: job.storyId,
          storyTitle: "",
          text: cleanText(item.text),
        });
        if (this.results.length % 100 === 0) this.log(`${this.results.length} comments; ${this.stats}`);
      }
      for (const kid of item.kids ?? []) this.enqueue({ id: kid, storyId: job.storyId });
    }
  }

  /** Fetches one item. Failures are retried with growing waits (0.5s, 1s, 2s). */
  private async fetchWithRetry(id: number): Promise<Item | null> {
    const cached = this.cache.get(id);
    if (cached !== undefined) {
      this.stats.cacheHits += 1;
      return cached;
    }
    let lastError: unknown;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      await this.limiter.acquire();
      this.stats.requests += 1;
      if (attempt > 0) this.stats.retries += 1;
      try {
        const item = await this.fetchItem(id);
        this.cache.set(id, item);
        return item;
      } catch (err) {
        lastError = err;
        await sleep(500 * 2 ** attempt);
      }
    }
    this.stats.failures += 1;
    this.log(`giving up on item ${id}: ${String(lastError)}`);
    return null;
  }
}
