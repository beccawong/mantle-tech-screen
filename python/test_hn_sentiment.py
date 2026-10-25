import time
import unittest

from classify import classify
from hn import Crawler, Item, RateLimiter, clean_text
from report import Classified, render, summarize


class ClassifyTest(unittest.TestCase):
    def test_ignores_comments_not_about_ai(self):
        self.assertEqual(classify("Rust's borrow checker is impressive."), "unrelated")

    def test_detects_bullish_comments(self):
        self.assertEqual(classify("Claude Code saves me hours every day, it's a game changer."), "bullish")

    def test_detects_bearish_comments(self):
        self.assertEqual(classify("LLMs hallucinate constantly. Pure hype."), "bearish")

    def test_flips_a_hit_that_follows_a_negation(self):
        self.assertEqual(classify("GPT-5 is not impressive at all."), "bearish")

    def test_labels_ai_comments_with_no_direction_as_neutral(self):
        self.assertEqual(classify("Which LLM do you use for code review?"), "neutral")


class CleanTextTest(unittest.TestCase):
    def test_strips_tags_and_unescapes_entities(self):
        raw = 'First line<p>Second &amp; <a href="x">link</a> it&#x27;s'
        self.assertEqual(clean_text(raw), "First line\nSecond & link it's")


def comment(label: str, score: int) -> Classified:
    return Classified(id=0, time=1_700_000_000, story_id=1, story_title="t", text="x", label=label, score=score)


class ReportTest(unittest.TestCase):
    def test_computes_net_score_over_directional_comments_only(self):
        summary = summarize([comment("bullish", 2), comment("bullish", 1), comment("bearish", -1), comment("unrelated", 0)])
        self.assertEqual(summary.total, 4)
        self.assertAlmostEqual(summary.net, 1 / 3)

    def test_renders_an_empty_sample(self):
        self.assertEqual(render(summarize([])), "No comments fetched.")


class CrawlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_collects_every_comment_under_a_story_newest_first(self):
        tree: dict[int, Item] = {
            1: {"id": 1, "type": "story", "title": "s", "kids": [2, 3]},
            2: {"id": 2, "type": "comment", "text": "a", "time": 2, "kids": [4]},
            3: {"id": 3, "type": "comment", "text": "b", "time": 3},
            4: {"id": 4, "type": "comment", "text": "c", "time": 4, "kids": [5]},
            5: {"id": 5, "type": "comment", "text": "d", "time": 5, "deleted": True},
        }

        async def fake_fetch(item_id):
            return tree.get(item_id)

        crawler = Crawler(workers=2, rate=1000, fetch_item=fake_fetch, log=lambda _: None)
        comments = await crawler.run([1], 10)
        self.assertEqual([c.id for c in comments], [4, 3, 2])
        self.assertEqual(comments[0].story_title, "s")
        self.assertEqual(crawler.stats.requests, 5)


class RateLimiterTest(unittest.IsolatedAsyncioTestCase):
    async def test_spaces_acquisitions_by_the_configured_interval(self):
        limiter = RateLimiter(0.02)
        started = time.monotonic()
        for _ in range(4):
            await limiter.acquire()
        self.assertGreaterEqual(time.monotonic() - started, 0.055)


if __name__ == "__main__":
    unittest.main()
