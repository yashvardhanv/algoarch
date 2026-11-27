# Lesson 74 — Case Study: News Aggregator

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — a news aggregator is a crawler, a de-duplicator and a ranker in a trench coat, and the hard part is deciding that two articles are the same story without comparing every pair.
>
> **Study time:** 55 minutes. **Do this after:** Web Crawler; Top-K and Trending; Pretraining Data and Scaling Laws (for MinHash).
>
> **Level:** extended.

An aggregator pulls thousands of feeds, finds that forty of them are reporting the same event, shows it once, and orders the result so that what is new and widely reported rises. This lesson builds the three parts as small models checked in `test/lesson_code/sy74_check.py`: identity and revision handling for feed entries, near-duplicate clustering with shingles and MinHash banding (with the banding probability verified by simulation), and a ranking with freshness decay. Capacity numbers come from `capacity_check_j.py`. No news product's engineering material was read (see Sources), and fetching itself is the Web Crawler lesson's topic.

---

## 1. Mental Model

> **Ingest is cheap and incremental; de-duplication is the expensive idea; ranking is a formula you tune. Two articles are "the same story" when their sets of word-triples overlap enough, and you find those pairs by letting similar documents collide in a hash table instead of comparing everything with everything.**

- **A feed entry has an identity and a revision time.** Atom says the entry id must be permanent and unique and must not change when the entry is republished or syndicated; revisions keep the id. Duplicates and updates are different things.
- **Similarity is set overlap.** Break each article into word shingles and compare by Jaccard similarity: the size of the intersection over the size of the union.
- **MinHash turns that into a small signature,** and banding makes similar signatures collide in a table, so a new article looks only at a handful of candidates.
- **Banding is a probability curve, not a switch.** Pairs above the threshold are found with high probability and pairs near it with moderate probability; a cheap exact check removes the false candidates.
- **Ranking is freshness times evidence:** the more independent sources report a story, the higher it goes; every hour it ages, it decays.

*Visual (planned): two articles as sets of shingles with the overlap highlighted, the signature below them as columns of minimum values, and the banding S-curve with a slider for bands and rows. Not built yet.*

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "don't show the same story twice" | shingles, MinHash, banding, exact check; cluster by union-find (section 5) |
| "pull 100,000 feeds without hammering them" | conditional requests and an adaptive per-feed interval (section 6; the crawler lesson for politeness) |
| "the same article arrives from several feeds" | entry identity by the feed's own id plus content similarity across feeds |
| "an article was edited" | same id, newer updated time: a revision, not a new item |
| "rank by freshness and importance" | exponential decay with a half-life, times a log of the number of sources |
| "trending right now" | a count over a sliding window (the Top-K and Trending lesson), here with stories as the keys |
| "why not compare every new article with every old one" | 35 million kept items is 35 million Jaccard computations per new item; banding replaces that with about 20 lookups (section 3) |

---

## 3. Requirements and Capacity

**Functional.** Poll a large set of feeds; keep the entries; group near-duplicate entries into stories; rank stories for a front page; update as entries are revised. **Out of scope:** the crawler's politeness and robots rules (see Web Crawler), personalisation, search, extracting the text of articles that feeds only summarise.

**Non-functional.** New stories appear within minutes; the de-duplicator's cost per new item does not grow with the archive; a revised entry never appears twice.

**Capacity estimate.** Every input is an assumption of this lesson (marked *assumed*); results are reproduced by `capacity_check_j.py`.

| Input | Value |
|---|---|
| feeds polled | 100,000 *(assumed)*, each every 900 seconds on average *(assumed)* |
| new items per day | 5,000,000 *(assumed)* |
| full feed response | 50 KB *(assumed)*; unchanged response 300 B *(assumed)*; 15% of polls find something new *(assumed)* |
| items kept for de-duplication | 7 days *(assumed)* |
| signature | 100 minima of 8 bytes *(as the model below stores them)* |
| band table entry | one key and one 8-byte item id per band *(assumed: nearly every band key of a non-duplicate item is unique, so nearly every entry carries its own key)* |
| banding | 20 bands of 5 rows |

| Result | Arithmetic | Value |
|---|---|---|
| polls | 100,000 / 900 | 111 per second |
| new items | 5,000,000 / 86,400 | 58 per second |
| bandwidth if every poll fetched the feed | 111 x 50 KB | 5.6 MB/s |
| bandwidth with conditional requests | 111 x (0.15 x 50 KB + 0.85 x 300 B) | 0.86 MB/s: 6.4 times less |
| items kept | 5,000,000 x 7 | 35 million |
| signature storage | 35 million x 800 B | 28 GB (14 GB if each minimum is cut to 4 bytes) |
| band table, if each band key is hashed to 8 bytes | 35 million x 20 bands x (8 B key + 8 B item id) | 11.2 GB |
| band table, if the 5-minimum key is stored as the model stores it | 35 million x 20 bands x (40 B key + 8 B item id) | 33.6 GB |
| band entries | 35 million x 20 | 700 million |
| table lookups for new items | 58 x 20 | 1,157 per second |

| Similarity of a pair | Chance the pair becomes a candidate: `1 - (1 - s^5)^20` |
|---|---|
| 0.5 | 47.0% |
| 0.6 | 80.2% |
| 0.7 | 97.5% |
| 0.8 | 99.96% |
| 0.9 | 100.0% (99.999998%) |

Three conclusions. **Conditional polling is a six-fold saving on bandwidth,** not a hundred-fold, because 15% of polls do bring data. **The archive is large and the lookups are few:** 1,157 lookups a second (about ten times the 111 polls a second) against 35 million kept items and 700 million band entries, which is the whole point of banding: the work per new item does not grow with the archive. The band table is the biggest single structure, at least 11.2 GB once keys are counted, and 33.6 GB if the model's keys are stored whole. **The S-curve is the design:** with 20 bands of 5 rows, near-duplicates at 0.8 are found 99.96% of the time while pairs at 0.5 are candidates 47% of the time, so the exact check after the lookup earns its keep. Move the curve with the number of bands and rows, not with a bigger signature alone.

---

## 4. API and Data Model

This is the lesson's own design, not any product's. One `FeedStore` per feed, so an entry id is scoped to its feed.

```
poll(feed)      -> conditional GET (ETag, If-None-Match); 304 means nothing changed; interval = next_interval(gaps)
ingest(feed, entries[(id, updated, text)]) -> fresh entries (new, or newer than seen)     FeedStore.ingest
add(text)       -> story id (the union-find root)                                         Dedup.add
GET /stories?limit=50 -> [{story, score, n_sources, newest_age_hours}]                     story_score, section 7

feed       {feed_id, url, etag, recent_gaps, next_poll}
entry      {feed_id, entry_id, updated, text, item}        key (feed_id, entry_id); a newer `updated` replaces the row
signature  {item, 100 minima}
band table {(band, tuple of 5 minima) -> [item]}          key as the model builds it; hashing it to 8 bytes is the sizing choice in section 3
story      {root, members, distinct sources, newest entry time}
```

Entries are keyed by identity, signatures by item, stories by union-find root: a merge changes only roots, so a story id is not stable across merges (the model says so in `Dedup`'s docstring). The model does not re-cluster a revised entry; that is left to the reader. Sizes of these rows are those in section 3 and nothing more.

---

## 5. The Model: Shingles, MinHash, Banding and Clusters

```python
import hashlib, math, random, re
from collections import defaultdict

P = (1 << 61) - 1
_rng = random.Random(1234)
COEFFS = [(_rng.randrange(1, P), _rng.randrange(P)) for _ in range(256)]     # 256 hash functions, fixed for repeatability

def shingles(text, k=3):
    """Set of word k-grams, lower-cased, punctuation ignored. Fewer than k words: the words form one shingle."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    if not words:
        return set()
    if len(words) < k:
        return {' '.join(words)}
    return {' '.join(words[i:i + k]) for i in range(len(words) - k + 1)}

def jaccard(a, b):
    """|A and B| / |A or B|. Two empty sets score 0: two empty documents are not the same story."""
    union = len(a | b)
    return len(a & b) / union if union else 0.0

def _base(s):
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], 'big')

def minhash(shingle_set, n=100):
    """n minima, one per hash function. The chance two sets agree on one minimum equals their Jaccard similarity."""
    if not shingle_set:
        return None
    xs = [_base(s) for s in shingle_set]
    return [min((a * x + b) % P for x in xs) for a, b in COEFFS[:n]]

def estimate(sig_a, sig_b):
    return sum(x == y for x, y in zip(sig_a, sig_b)) / len(sig_a)

def band_keys(sig, bands, rows):
    """One key per band; two documents are candidates if any key is equal."""
    return [(i, tuple(sig[i * rows:(i + 1) * rows])) for i in range(bands)]

def lsh_probability(s, bands, rows):
    """Chance a pair of similarity s shares at least one band, if rows of one band agree with probability s^rows."""
    return 1 - (1 - s ** rows) ** bands


class Dedup:
    """Adds documents one at a time; returns the story id (the current root of the story). Ids can change when
    two stories merge."""
    def __init__(self, threshold=0.8, bands=20, rows=5, n=100):
        self.threshold, self.bands, self.rows, self.n = threshold, bands, rows, n
        self.sets, self.parent, self.table = [], [], defaultdict(list)

    def _find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def add(self, text):
        i, s = len(self.sets), shingles(text)
        self.sets.append(s)
        self.parent.append(i)
        sig = minhash(s, self.n)
        if sig is not None:
            keys = band_keys(sig, self.bands, self.rows)
            candidates = {j for key in keys for j in self.table[key]}
            for j in candidates:
                if jaccard(s, self.sets[j]) >= self.threshold:        # the exact check: no false merges
                    self.parent[self._find(i)] = self._find(j)
            for key in keys:
                self.table[key].append(i)
        return self._find(i)
```

The Pretraining Data and Scaling Laws lesson already teaches shingles, MinHash, the identity `P(minima agree) = Jaccard`, the banding formula `1 - (1 - s^r)^b` with its S-curve, and the verify step, there for removing near-duplicate documents from a training corpus. It is the same technique for the same purpose (finding near-duplicate documents without comparing all pairs), so read it first; it is not re-derived here. What is new in this lesson: the model's hash family is multiply-and-add, which is pairwise independent but not min-wise independent, so the identity is only approximate and the check measures the bias instead of assuming it; the band independence assumption is tested by simulation; documents are grouped into stories with union-find instead of one survivor per cluster; and the threshold and recall trade-off is measured on rewrites. No paper on these techniques was consulted for this lesson.

What the check proves:

- **Shingles and Jaccard match their definitions,** including case, punctuation, short documents and the rule that two empty documents score 0.
- **No bias is detectable at this sample size.** For pairs built to have Jaccard similarity 0.2, 0.5, 0.8 and 0.95, the mean of 200 estimates from 100-minimum signatures is within four standard errors of the truth (about 0.014 at 0.5; the same 100 coefficients are reused across trials, and a smaller bias than that would not show).
- **The S-curve is real.** For five similarities (0.5 to 0.9) and 1,500 pairs each, the fraction of pairs sharing a band matches `1 - (1 - s^5)^20` within four binomial standard errors, so the independence assumption holds for this family.
- **Clusters are connected by verified pairs, and recall follows the curve.** On six random corpora of rewritten stories plus unrelated one-offs, every story is a set whose members are linked by chains of true pairs at or above the threshold, so no two unrelated articles are merged. For light rewrites (at most one edited word in sixty) at the default threshold of 0.8, all 156 true pairs end up in one story (the check asserts equality). For heavy rewrites (up to six edited words) at a threshold of 0.5, only 101 of 125 true pairs (81%) do, which is the S-curve's shoulder showing: pairs near the threshold are found only some of the time (the corpora are seeded, so the check pins 101 of 125). A bridging case pins the union-find: A and C share nothing, B overlaps both, and added in any order the three form one story. A decoy case pins candidate handling: when the first candidate is not a true match, the second one is still checked. Empty documents never merge, and the same text added twice joins one story.

---

## 6. Ingest: Identity, Revisions and Polling

```python
import statistics

class FeedStore:
    """Entries are (id, updated, text). The id is the identity; a later 'updated' is a revision."""
    def __init__(self):
        self.seen = {}                                        # id -> latest updated seen

    def ingest(self, entries):
        """Returns the entries that are new or newer than what we have, in the order received."""
        fresh = []
        for entry_id, updated, text in entries:
            if entry_id not in self.seen or updated > self.seen[entry_id]:
                self.seen[entry_id] = updated
                fresh.append((entry_id, updated, text))
        return fresh

def next_interval(gaps, lo=60, hi=3600):
    """Seconds until the next poll of a feed: about twice per typical gap between new entries, within [lo, hi]."""
    if not gaps:
        return hi
    return min(hi, max(lo, statistics.median(gaps) / 2))
```

The Atom standard (RFC 4287) defines the entry id as a permanent, universally unique identifier that does not change when an entry is relocated, republished or syndicated, and defines `updated` as the most recent time the entry was modified in a way the publisher considers significant, adding that not every modification changes it. That is why identity is the id and a revision is a newer `updated`: a feed that edits a typo without touching `updated` is invisible here by the publisher's own definition. Many feeds are not Atom and are less careful; this model does not read RSS and makes no claim about it.

The check pins the semantics: the same entry twice yields nothing; a newer `updated` yields a revision under the same id; an older copy arriving late is ignored; duplicates inside one batch collapse. `next_interval` is this lesson's design: poll about twice per typical gap (an interval of half the median gap), so a new entry waits half an interval, a quarter of a typical gap, on average and at worst half a gap (the check simulates arrivals against the poll grid), and clamp between a minute and an hour to protect the feed and bound the staleness. Polling uses a conditional request (`If-None-Match`; the Feature Flags and Config Service lesson cites the HTTP standard for it, and this lesson did not read it); the crawler lesson covers politeness.

---

## 7. Ranking

```python
def story_score(n_sources, newest_age_hours, source_weight=1.0, half_life_hours=6):
    """Evidence (1 + log2 of the number of distinct sources) times freshness (halves every half-life)."""
    return source_weight * (1 + math.log2(n_sources)) * 0.5 ** (newest_age_hours / half_life_hours)
```

Every constant here (the log, the six-hour half-life, the source weight) is a tuning choice with no source behind it. The check pins the shape, including that 1.5 ratio: a story's score halves after one half-life and quarters after two; four sources score 3 against 2 for two sources (1.5 times, not double: the log grows slowly); a day-old story reported by eight sources scores below a fresh single report at a six-hour half-life (`4.0 x 0.0625 = 0.25` against 1). The point to make in an interview is that this is a dial, set by looking at what readers click, not a theorem.

**Counting sources honestly.** `n_sources` should count distinct publishers, not copies: forty syndicated reprints of one agency story are one source, not forty. The model leaves that to the caller.

---

## 8. Failure Modes

| Failure | What goes wrong | What the design does |
|---|---|---|
| a feed repeats old entries | duplicates appear | identity by id; an unchanged `updated` is ignored |
| an entry is edited | a second copy, or none | same id, newer `updated`: reported as a revision |
| a feed reuses ids | distinct stories collapse | a standard-violating feed; add content similarity as a second check (not modelled) |
| two stories share boilerplate | a false merge | the exact check at the threshold; boilerplate removal is not modelled |
| a rewrite at similarity near the threshold | missed by banding with 47% probability at 0.5 | accept, or add bands; the curve shows the cost |
| a very popular story | thousands of near-duplicates, one growing cluster | union-find keeps merging; cap candidate checks per item in production (not modelled) |
| a slow or dead feed | its entries stall | the interval clamp and a failure backoff (the crawler lesson) |
| ranking drift | old stories linger or new ones vanish | tune the half-life against reader behaviour |

---

## 9. What Real Systems Did

No engineering article or paper from a news aggregator or search engine was read for this lesson. The one standard it uses is the Atom format (entry identity and the meaning of `updated`). Shingling, MinHash banding and clustering are described here as general techniques and derived from first principles, and every number is this lesson's assumption.

---

## 10. Pitfalls Checklist

1. **Treating an edited entry as a new article.** The id is the identity; use `updated` for order.
2. **Comparing every new article with every stored one.** 35 million comparisons per item; use banding.
3. **Skipping the exact check.** Banding returns candidates at 47% for pairs at 0.5; verify before merging.
4. **Counting copies as sources.** Forty reprints are one report.
5. **A fixed polling interval for all feeds.** A feed that updates once a day does not need minute polling; a news wire does.
6. **Using only a bigger signature to improve recall.** The S-curve moves with bands and rows.
7. **Ranking with no decay.** Old big stories sit on top forever.
8. **Trusting every feed's ids and dates.** Not every feed follows the standard.

---

## Drills

1. Two articles have shingle sets of sizes 80 and 60 sharing 48 shingles. What is their Jaccard similarity?
2. Compute `1 - (1 - s^r)^b` for s = 0.7, r = 4, b = 25 and compare with the 20 x 5 curve at the same similarity. Which is more permissive, and what does it cost?
3. 100,000 feeds with a 1,800-second average poll, 20 KB full responses, 300-byte unchanged responses and 10% of polls bringing data. Bandwidth with and without conditional requests.
4. A feed edits a typo without changing `updated`. What does the model do, and is that a bug?
5. Choose bands and rows so that a pair at similarity 0.7 is found at least 90% of the time. Show the arithmetic for your choice.
6. Change `>=` to `>` in the verification step. Which pairs stop merging, and which check fails?
7. A story is reported by 16 sources and is 12 hours old with a six-hour half-life. Its score, and the age at which it falls below a fresh single report.
8. Why is "forty syndicated copies" one source for ranking but forty items for storage? Where in the pipeline does the distinction have to be made?

---

## Homework

1. Write a boilerplate remover that drops shingles occurring in more than a given share of documents, and measure how many false merges the exact check was stopping before and after.
2. Add a cap on candidate checks per new document and measure, on a corpus with one 500-article story, how the cap changes the work and the number of stories.
3. Replace the multiply-and-add family with SHA-256-based hashing for each of the 100 functions, and measure the estimator's bias against the check's tolerance.
4. Read RFC 4287 section 4.1.2 (entries) and list which fields you would need to store to rebuild an entry for display, beyond the id and the `updated` time.

---

## Sources

All read on 27 November 2026.

- IETF, *RFC 4287, The Atom Syndication Format*, rfc-editor.org/rfc/rfc4287.txt (read in part: the definitions of `atom:id` in section 4.2.6 and `atom:updated` in section 4.2.15).
- Not read: any paper on shingling, MinHash or locality-sensitive hashing (the identity between the agreement probability and Jaccard similarity, and the banding formula, are derived in the lesson and tested by simulation), RFC 5005 or the RSS specification, any news aggregator's engineering material, and any study of ranking for news.

## Further reading (not consulted)

- Broder's work on resemblance and containment of documents, and the locality-sensitive hashing literature.
- Engineering write-ups of news and feed-reader backends.
- Research on freshness and popularity in news ranking.

*Last reviewed: 27 November 2026.*
