/** Turns labeled comments into a short report for traders. */
import type { Comment } from "./hn.ts";
import type { Label } from "./classify.ts";

const BUCKET_SECONDS = 6 * 3600; // trend is shown in 6-hour blocks
const TOP_THREADS = 5;
const EXAMPLES = 3;
const LABELS: Label[] = ["bullish", "bearish", "neutral", "unrelated"];

export interface Classified extends Comment {
  label: Label;
  score: number;
}

type Counts = Record<Label, number>;

export interface Summary {
  total: number;
  counts: Counts;
  net: number;
  window: [number, number] | null;
  trend: Array<{ bucket: number; net: number; n: number }>;
  threads: Array<{ title: string; net: number; n: number }>;
  bullishExamples: Classified[];
  bearishExamples: Classified[];
}

const emptyCounts = (): Counts => ({ bullish: 0, bearish: 0, neutral: 0, unrelated: 0 });

/** From -1 (all bearish) to +1 (all bullish). Ignores neutral and unrelated comments. */
export function netScore(counts: Counts): number {
  const directional = counts.bullish + counts.bearish;
  return directional ? (counts.bullish - counts.bearish) / directional : 0;
}

/** Counts labels per group, e.g. per story or per time block. */
function countByGroup<K>(comments: Classified[], groupOf: (c: Classified) => K): Map<K, Counts> {
  const groups = new Map<K, Counts>();
  for (const c of comments) {
    const group = groupOf(c);
    const counts = groups.get(group) ?? emptyCounts();
    counts[c.label] += 1;
    groups.set(group, counts);
  }
  return groups;
}

export function summarize(comments: Classified[]): Summary {
  const counts = emptyCounts();
  for (const c of comments) counts[c.label] += 1;
  const ai = comments.filter((c) => c.label !== "unrelated");
  const titles = new Map(ai.map((c) => [c.storyId, c.storyTitle]));

  const blockStart = (c: Classified) => c.time - (c.time % BUCKET_SECONDS);
  const trend = [...countByGroup(ai, blockStart)]
    .sort(([a], [b]) => a - b)
    .map(([bucket, cnt]) => ({ bucket, net: netScore(cnt), n: cnt.bullish + cnt.bearish }));

  const threads = [...countByGroup(ai, (c) => c.storyId)]
    .map(([storyId, cnt]) => ({
      title: titles.get(storyId) ?? "",
      net: netScore(cnt),
      n: cnt.bullish + cnt.bearish + cnt.neutral,
    }))
    .sort((a, b) => b.n - a.n)
    .slice(0, TOP_THREADS);

  const ranked = [...ai].sort((a, b) => a.score - b.score); // most bearish first
  const times = comments.map((c) => c.time);

  return {
    total: comments.length,
    counts,
    net: netScore(counts),
    window: comments.length ? [Math.min(...times), Math.max(...times)] : null,
    trend,
    threads,
    bullishExamples: ranked.filter((c) => c.score > 0).reverse().slice(0, EXAMPLES),
    bearishExamples: ranked.filter((c) => c.score < 0).slice(0, EXAMPLES),
  };
}

const ts = (epoch: number) => new Date(epoch * 1000).toISOString().slice(0, 16).replace("T", " ");
const pct = (n: number, total: number) => `${((100 * n) / total).toFixed(1).padStart(5)}%`;
const signed = (n: number, digits = 2) => (n < 0 ? "" : "+") + n.toFixed(digits);

function snippet(comment: Classified, width = 110): string {
  const text = comment.text.split(/\s+/).join(" ");
  return text.length <= width ? text : `${text.slice(0, width - 1)}…`;
}

export function render(summary: Summary): string {
  const { total, counts, window } = summary;
  if (!total || !window) return "No comments fetched.";
  const aiTotal = total - counts.unrelated;
  const lines = [`HN AI sentiment: ${total} comments, ${ts(window[0])} to ${ts(window[1])} UTC`, ""];
  for (const label of LABELS) {
    lines.push(`  ${label.padEnd(10)}${String(counts[label]).padStart(6)}  (${pct(counts[label], total)})`);
  }
  lines.push(
    "",
    `net sentiment: ${signed(summary.net)}   (bullish - bearish) / (bullish + bearish), range -1..+1`,
    `AI share of conversation: ${((100 * aiTotal) / total).toFixed(1)}%`,
    "",
    "trend (6h buckets: net score, directional comments):",
    ...summary.trend.map((t) => `  ${ts(t.bucket)}  ${signed(t.net)}  (n=${t.n})`),
    "",
    "most discussed AI threads:",
    ...summary.threads.map((t) => `  ${signed(t.net)}  (n=${t.n})  ${t.title}`),
    "",
    "strongest bullish:",
    ...summary.bullishExamples.map((c) => `  [${signed(c.score, 0)}] ${snippet(c)}`),
    "",
    "strongest bearish:",
    ...summary.bearishExamples.map((c) => `  [${signed(c.score, 0)}] ${snippet(c)}`),
  );
  return lines.join("\n");
}
