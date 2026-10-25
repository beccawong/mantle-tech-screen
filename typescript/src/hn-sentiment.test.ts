import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { classify } from "./classify.ts";
import { cleanText, Crawler, RateLimiter, type Item } from "./hn.ts";
import { render, summarize, type Classified } from "./report.ts";

describe("classify", () => {
  it("ignores comments that are not about AI", () => {
    assert.equal(classify("Rust's borrow checker is impressive."), "unrelated");
  });
  it("detects bullish comments", () => {
    assert.equal(classify("Claude Code saves me hours every day, it's a game changer."), "bullish");
  });
  it("detects bearish comments", () => {
    assert.equal(classify("LLMs hallucinate constantly. Pure hype."), "bearish");
  });
  it("flips a hit that follows a negation", () => {
    assert.equal(classify("GPT-5 is not impressive at all."), "bearish");
  });
  it("labels AI comments with no direction as neutral", () => {
    assert.equal(classify("Which LLM do you use for code review?"), "neutral");
  });
});

describe("cleanText", () => {
  it("strips tags and unescapes entities", () => {
    assert.equal(cleanText('First line<p>Second &amp; <a href="x">link</a> it&#x27;s'), "First line\nSecond & link it's");
  });
});

describe("report", () => {
  const comment = (label: Classified["label"], score: number): Classified => ({
    id: 0, time: 1_700_000_000, storyId: 1, storyTitle: "t", text: "x", label, score,
  });

  it("computes the net score over directional comments only", () => {
    const summary = summarize([comment("bullish", 2), comment("bullish", 1), comment("bearish", -1), comment("unrelated", 0)]);
    assert.equal(summary.total, 4);
    assert.ok(Math.abs(summary.net - 1 / 3) < 1e-9);
  });
  it("renders an empty sample", () => {
    assert.equal(render(summarize([])), "No comments fetched.");
  });
});

describe("Crawler", () => {
  it("collects every comment under a story, newest first", async () => {
    const tree: Record<number, Item> = {
      1: { id: 1, type: "story", title: "s", kids: [2, 3] },
      2: { id: 2, type: "comment", text: "a", time: 2, kids: [4] },
      3: { id: 3, type: "comment", text: "b", time: 3 },
      4: { id: 4, type: "comment", text: "c", time: 4, kids: [5] },
      5: { id: 5, type: "comment", text: "d", time: 5, deleted: true },
    };
    const crawler = new Crawler({ workers: 2, rate: 1000, fetchItem: async (id) => tree[id] ?? null, log: () => {} });
    const comments = await crawler.run([1], 10);
    assert.deepEqual(comments.map((c) => c.id), [4, 3, 2]);
    assert.equal(comments[0].storyTitle, "s");
    assert.equal(crawler.stats.requests, 5);
  });
});

describe("RateLimiter", () => {
  it("spaces acquisitions by the configured interval", async () => {
    const limiter = new RateLimiter(20);
    const started = Date.now();
    for (let i = 0; i < 4; i++) await limiter.acquire();
    assert.ok(Date.now() - started >= 55);
  });
});
