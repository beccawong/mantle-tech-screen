import asyncio, re, sys
sys.path.insert(0, "/Users/rebeccawong/Development/mantle/orn-code-review/python")
from hn import Crawler
from classify import classify

# 5 stories, each with 3 comments -> expect 15 comments. Fake 200ms network latency.
tree = {}
for s in range(1, 6):
    kids = [s * 100 + k for k in range(3)]
    tree[s] = {"id": s, "type": "story", "title": f"s{s}", "kids": kids}
    for k in kids:
        tree[k] = {"id": k, "type": "comment", "text": "x", "time": k}

async def slow_fetch(i):
    await asyncio.sleep(0.2)
    return tree.get(i)

async def main():
    c = Crawler(workers=8, rate=1000, fetch_item=slow_fetch, log=lambda _: None)
    got = await c.run(list(range(1, 6)), 100)
    print("comments collected:", len(got), "(expected 15)")
asyncio.run(main())

print("A.I. sentence:", classify("A.I. is impressive."))
print("A.I. mid-word:", classify("A.I.x is impressive."))
print("negation bleed:", classify("I don't use Copilot. Claude is impressive."))
