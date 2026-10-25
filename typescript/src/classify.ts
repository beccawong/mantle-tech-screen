/** Word-list classifier: is a comment about AI, and is it bullish or bearish on it? */

export type Label = "bullish" | "bearish" | "neutral" | "unrelated";

// Each entry is a regex, matched as a whole word and ignoring case.
const AI_TERMS = [
  "ai", "a\\.i\\.", "agi", "llms?", "gpt-?\\w*", "chatgpt", "openai", "anthropic",
  "claude", "gemini", "copilot", "deepseek", "machine learning", "deep learning",
  "neural net(?:work)?s?", "language models?", "foundation models?",
  "frontier models?", "agentic", "vibe.?cod(?:e|ing|ed)",
];

const BULLISH = [
  "game.?chang\\w+", "breakthrough", "impressive", "incredible", "amazing",
  "remarkable", "excit(?:ed|ing)", "productiv\\w+", "10x", "underrated",
  "revolution\\w*", "transformative", "love (?:it|using|this|how)",
  "works? (?:great|well|surprisingly)", "better than", "faster than",
  "saves? (?:me )?(?:hours|time|days|so much)", "can'?t live without",
  "indispensable", "step change", "accelerat\\w+", "improv(?:ed|ing|ement)",
  "useful", "helpful", "brilliant", "insanely good", "mind.?blowing", "bullish",
];

const BEARISH = [
  "hype\\w*", "overhyped", "bubble", "hallucinat\\w*", "slop", "useless",
  "garbage", "plateau\\w*", "diminishing returns", "scam", "hit(?:ting|s)? a wall",
  "overrated", "disappoint\\w*", "unreliable", "worse than", "regress\\w*",
  "burn(?:ing|s)? (?:cash|money)", "unprofitable", "crash", "waste of",
  "dead end", "stochastic parrot", "grift\\w*", "parlor trick", "snake oil",
  "broken", "buggy", "mediocre", "underwhelm\\w*", "nonsense",
  "not (?:ready|there yet)", "bearish",
];

const NEGATION = /\b(?:not|no|never|hardly|isn'?t|aren'?t|don'?t|doesn'?t|won'?t|can'?t)\b/i;
const NEGATION_WINDOW = 30; // a negation this many characters before a match flips it

const compile = (terms: string[]) => new RegExp(`\\b(?:${terms.join("|")})\\b`, "gi");

const AI_RE = compile(AI_TERMS);
const BULL_RE = compile(BULLISH);
const BEAR_RE = compile(BEARISH);

export function isAboutAi(text: string): boolean {
  AI_RE.lastIndex = 0;
  return AI_RE.test(text);
}

function countMatches(text: string, regex: RegExp): number {
  let total = 0;
  for (const match of text.matchAll(regex)) {
    const before = text.slice(Math.max(0, match.index - NEGATION_WINDOW), match.index);
    total += NEGATION.test(before) ? -1 : 1;
  }
  return total;
}

/** Bullish matches minus bearish matches. Above 0 is bullish, below 0 is bearish. */
export function score(text: string): number {
  return countMatches(text, BULL_RE) - countMatches(text, BEAR_RE);
}

/** "neutral" means about AI but neither bullish nor bearish. */
export function classify(text: string): Label {
  if (!isAboutAi(text)) return "unrelated";
  const s = score(text);
  if (s > 0) return "bullish";
  if (s < 0) return "bearish";
  return "neutral";
}
