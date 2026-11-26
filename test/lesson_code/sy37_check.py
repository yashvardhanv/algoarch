"""Runs the python code blocks from data/new_lessons/sy37-distributed-search.md against a brute-force BM25 scorer
that re-reads every document's text, and asserts the worked example's numbers."""
import re, sys, math, random
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
Index, bm25_top_k, distributed_top_k = ns['Index'], ns['bm25_top_k'], ns['distributed_top_k']
page_after, paginate, merge_stats = ns['page_after'], ns['paginate'], ns['merge_stats']
random.seed(37)

# guard: paginate calls page_after through the module namespace; cap the calls so a cursor bug that
# returns the same page forever fails the check instead of hanging it
_page_after, _calls = page_after, [0]
def guarded_page_after(*a, **kw):
    _calls[0] += 1
    assert _calls[0] <= 200, 'paginate did not terminate (cursor does not advance)'
    return _page_after(*a, **kw)
ns['page_after'] = guarded_page_after

def brute_scores(docs, query, k1=1.2, b=0.75):
    """docs: {doc_id: text}. Scores every document straight from the formula, no index."""
    toks = {d: t.lower().split() for d, t in docs.items()}
    N = len(toks)
    avgdl = sum(len(t) for t in toks.values()) / N
    out = {}
    for d, t in toks.items():
        s, matched = 0.0, False
        for q in set(query.lower().split()):
            n = sum(1 for u in toks.values() if q in u)
            f = t.count(q)
            if f:
                matched = True
                w = math.log((N - n + 0.5) / (n + 0.5) + 1)
                s += w * (f * (k1 + 1)) / (f + k1 * (1 - b + b * len(t) / avgdl))
        if matched:
            out[d] = s
    return out

def brute_ranking(docs, query):
    sc = brute_scores(docs, query)
    return sorted(sc, key=lambda d: (-sc[d], d)), sc

def same_ranking(hits, ranking, sc):
    assert [d for _, d in hits] == ranking[:len(hits)], (hits, ranking[:len(hits)])
    for s, d in hits:
        assert abs(-s - sc[d]) < 1e-9

VOCAB = ['redis', 'kafka', 'shard', 'cluster', 'index', 'search', 'query', 'node', 'replica', 'segment', 'merge', 'score']
def random_docs(n):
    docs = {}
    for i in range(n):
        L = random.randint(1, 12)
        # skewed vocabulary so that some terms are common and some rare
        docs[random.randint(0, 10**6) * 1000 + i] = ' '.join(random.choice(VOCAB[:random.randint(2, len(VOCAB))]) for _ in range(L))
    return docs

checked = 0
for trial in range(250):
    docs = random_docs(random.randint(1, 40))
    query = ' '.join(random.sample(VOCAB, random.randint(1, 3)))
    ranking, sc = brute_ranking(docs, query)
    single = Index()
    for d, t in docs.items():
        single.add(d, t)
    k = random.randint(1, 12)
    same_ranking(bm25_top_k(single, query, k), ranking, sc)
    # shard by doc id, score with global statistics: must equal the single index exactly
    n = random.randint(1, 6)
    shards = [Index() for _ in range(n)]
    for d, t in docs.items():
        shards[d % n].add(d, t)
    same_ranking(distributed_top_k(shards, query, k, dfs=True), ranking, sc)
    # paging with search_after over global stats reproduces the full ranking with no gaps or repeats
    stats = merge_stats([s.stats() for s in shards])
    size = random.randint(1, 5)
    _calls[0] = 0
    pages = paginate(shards, query, size, stats)
    flat = [h for p in pages for h in p]
    assert all(len(p) <= size for p in pages)
    same_ranking(flat, ranking, sc)
    assert len(flat) == len(ranking), (len(flat), len(ranking))
    assert len(set(d for _, d in flat)) == len(flat)
    checked += 1

# --- the worked example
A, B = Index(), Index()
A.add(1, "redis sorted sets"); A.add(2, "redis persistence modes"); A.add(3, "redis eviction policies")
B.add(4, "tuning redis for a large kafka deployment"); B.add(5, "kafka consumer groups"); B.add(6, "kafka log compaction")
g = distributed_top_k([A, B], "redis", 4, dfs=True)
l = distributed_top_k([A, B], "redis", 2, dfs=False)
assert [d for _, d in g] == [1, 2, 3, 4], g
assert round(-g[0][0], 3) == 0.477 and round(-g[1][0], 3) == 0.477 and round(-g[2][0], 3) == 0.477 and -g[3][0] < -g[2][0]
assert [d for _, d in l] == [4, 1] and round(-l[0][0], 3) == 0.784 and round(-l[1][0], 3) == 0.134, l
assert 'document 4 scores 0.784' in src and 'document 1 scores 0.134' in src and 'tie at 0.477' in src
print('sy37 code checks passed (%d random collections)' % checked)
