/** CLI: fetch Hacker News comments, classify AI sentiment, print a report. */
import { parseArgs } from "node:util";

import { classify, score } from "./classify.ts";
import * as hn from "./hn.ts";
import { render, summarize, type Classified } from "./report.ts";

const log: hn.Logger = (message) => console.error(message);

async function main(): Promise<void> {
  const { values } = parseArgs({
    options: {
      stories: { type: "string", default: "30" },
      "max-comments": { type: "string", default: "2000" },
      workers: { type: "string", default: String(hn.DEFAULT_WORKERS) },
      rate: { type: "string", default: String(hn.DEFAULT_RATE) },
    },
  });
  const stories = Number(values.stories);
  const maxComments = Number(values["max-comments"]);
  const workers = Number(values.workers);
  const rate = Number(values.rate);

  log(`fetching ${stories} stories with ${workers} workers at ${rate} req/s`);
  const crawler = new hn.Crawler({ workers, rate, log });
  const comments = await crawler.run(await hn.topStoryIds(stories), maxComments);
  const classified: Classified[] = comments.map((c) => {
    const label = classify(c.text);
    return { ...c, label, score: label === "unrelated" ? 0 : score(c.text) };
  });
  console.log(render(summarize(classified)));
  console.log(`\nfetch stats: ${crawler.stats}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
