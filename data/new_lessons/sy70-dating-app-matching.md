# Lesson 70 — Case Study: Dating App Matching and Swipe Feed (Tinder)

> **Priority:** ★★☆☆☆ (proposed; the curriculum data holds the final rating) — a lower-frequency prompt, but it packs three reusable ideas: a reciprocal write that must not lose a match, a "have I shown this already" set too big for exact storage, and a feed that must not show everyone the same people.
>
> **Study time:** 60 minutes. **Do this after:** Proximity Service & Location-Based Systems; Scaling Patterns I: Reads, Writes and Contention; Flash Sale & Ticket Reservation (Ticketmaster).
>
> **Level:** extended.

You swipe right on someone; if they already swiped right on you, both of you must learn about the match, once, and never be shown each other again. That is a small write path with a nasty race, a membership set that grows forever, and a ranking problem that concentrates attention. The code is checked in `test/lesson_code/sy70_check.py`; capacity figures come from `capacity_check_i.py`. Finding nearby people is not re-taught (see Proximity Service & Location-Based Systems), nor is the counter-contention pattern (see Scaling Patterns I).

---

## 1. Mental Model

> **A swipe feed is three separate problems wearing one app: a candidate query (who is eligible), a seen filter (who have I already judged), and a ranking (who first). The only part where a bug loses a user-visible promise is the write that detects a mutual like.**

- **The match is the promise.** If both people swiped right, a match must exist. A lost match is silent: nobody sees an error, two people just never meet.
- **Write first, then read.** Each swipe records itself, then looks for the reverse swipe. Reading first and writing second loses matches when two swipes cross (section 5, all six orders enumerated).
- **The seen set only needs one-sided errors.** Wrongly hiding an unseen profile costs a little supply; wrongly showing a judged one is a visible bug. A Bloom filter errs in exactly the cheap direction.
- **Supply is finite.** A user's eligible pool is bounded by who lives within their filters, so at some point the feed runs out, and "recycle after a window" is a requirement, not a nicety.
- **Rank for the pair, and cap exposure.** What helps is the chance that both like each other, and no profile should take an unbounded share of impressions.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "when both swipe right, notify both" | write the swipe first, then read the reverse; match keyed by the unordered pair (section 5) |
| "never show a profile twice" | per-user seen set; exact set while small, Bloom filter when large (section 6) |
| "profiles near me", "within 25 km" | geo index with a cell cover; see Proximity Service & Location-Based Systems |
| "the same few people appear for everyone" | per-round exposure cap on the ranked list (section 7) |
| "undo", "rewind" | the seen filter must support removal, so keep an exact short-term list beside the Bloom filter |
| "unmatch", "block" | an explicit deny list checked in the candidate query; never rely on the seen filter |

---

## 3. Requirements and Capacity

**Functional.** Show a stack of candidate profiles filtered by distance, age and preference; record like or pass; on mutual like create a match and notify both; never repeat a judged profile; allow unmatch and block.

**Non-functional.** Swipe acknowledgement is fast (the client moves to the next card at once); a mutual like is never lost; a duplicate delivery of one swipe creates at most one match; the feed keeps working when one component is down (serve a slightly stale stack rather than an error).

**Capacity.** Every figure below is an assumption chosen to size the design; none is a statement about any real product. They are computed in `capacity_check_i.py`.

| Quantity | Assumption or derivation | Result |
|---|---|---|
| Daily active users | assumed | 10 million |
| Swipes per active user per day | assumed | 100 |
| Swipes per day | 10 million x 100 | 1 billion, about 11,574 per second average, about 34,722 per second at three times the average |
| Right swipes | assumed 30 percent of swipes | 300 million per day, about 3,472 per second |
| Reverse lookups | one per right swipe | about 3,472 per second average, about 10,417 at the peak |
| Matches | assumed 5 percent of right swipes find a prior like | 15 million per day, about 174 per second |
| Right-swipe index | 24 bytes per entry (two 8-byte ids, 8-byte timestamp) | 7.2 GB per day, about 2.6 TB per year |
| Seen set for one heavy user who never forgets | 100 swipes per day for 3 years = 109,500 ids | exact ids 855 KiB; Bloom filter at 1 percent 128 KiB |
| The same user with a 45-day window | 4,500 ids in 3 generations of 1,500, each sized for 0.33 percent | about 6.5 KiB |
| Fleet seen-set store, upper bound | 10 million users, every one as heavy as above and never forgetting | about 1.3 TB as Bloom filters, 8.8 TB as exact ids |
| Seen-set updates | every swipe, left or right | the full swipe rate: about 11,574 per second average |
| Pool exhaustion | 100 swipes per day against a pool of 5,000 or 50,000 eligible profiles | 50 days or 500 days |

Two consequences. First, only right swipes need an index for reverse lookup, so that durable like index grows at about a third of the swipe rate (3,472 per second). Left swipes do not go there, but they do update the seen set, so the seen set is written at the full swipe rate; if those updates are batched per session and lost in a crash, the last few judged profiles reappear, which is a visible bug, so keep a short exact log of recent swipes durable. Second, the pool-exhaustion row says the seen set must forget: after about 50 days a user in a sparse area has seen everyone, and the feed is empty unless old entries expire (section 6, which also says how long to remember).

---

## 4. API and Data Model

```
POST /swipes        {swiper, target, direction: like|pass, client_swipe_id}  -> {matched: bool}
GET  /feed?limit=20                                                           -> [profile cards]
POST /matches/{id}/unmatch
```

| Store | Key | Notes |
|---|---|---|
| likes | (swiper, target) | right swipes only; a unique key makes a retried swipe harmless |
| matches | (low id, high id) | the unordered pair is the key, so two racing writers cannot create two matches |
| seen | per user | exact short-term list plus rotating Bloom filters (section 6) |
| profiles + geo index | cell id, then id | the candidate query; see Proximity Service & Location-Based Systems |
| deny list | per user | blocks and unmatches, checked in the candidate query |

The client sends a `client_swipe_id` so that a lost reply can be retried; the like row's unique key already makes the retry idempotent, so the id matters mostly for logging and for pass swipes, which are not stored in the likes table.

---

## 5. Deep Dive 1: The Swipe That Must Not Lose a Match

A swipe does two things to the store: it records "A liked B", and it asks "did B like A?". Two people can swipe on each other at nearly the same time, on different servers. The order of those two steps decides whether the match survives.

```python
class SwipeStore:
    """Right swipes only are indexed; matches are keyed by the unordered pair."""
    def __init__(self):
        self.likes = set()        # (swiper, target)
        self.matches = {}         # (low, high) -> match id

    def write(self, a, b):
        self.likes.add((a, b))

    def sees(self, a, b):
        return (b, a) in self.likes

    def create_match(self, a, b):
        key = (min(a, b), max(a, b))          # numeric order, never string order
        if key in self.matches:
            return False                      # idempotent: a second writer finds it done
        self.matches[key] = len(self.matches) + 1
        return True


def swipe_steps(store, a, b, safe=True):
    """One right swipe as a generator with a yield between the two store calls, so a test can
    interleave two swipes at every possible point. safe=True is write-then-read."""
    if safe:
        store.write(a, b)
        yield
        if store.sees(a, b):
            store.create_match(a, b)
    else:
        seen = store.sees(a, b)               # read first ...
        yield
        store.write(a, b)                     # ... write second: the bug
        if seen:
            store.create_match(a, b)
```

Two clients, two steps each, gives 6 distinct schedules (the orders of `0,0,1,1`). The check runs all six against both versions:

| Version | Schedules that end with exactly one match | Schedules that lose the match |
|---|---|---|
| write, then read | 6 of 6 | none |
| read, then write | 2 of 6 (`0,0,1,1` and `1,1,0,0`, where one swipe finishes first) | 4 of 6 |

The four losing orders are exactly those where both clients read before either writes (the first two steps are one from each client): each sees nothing, each then writes, and nobody creates the match. Visual (planned): a two-lane timeline of the six schedules with the four losing ones marked. In the safe version, whichever client reads second has necessarily read after both writes, so at least one of the two sees the other. Sometimes both do, which is why `create_match` must be idempotent on the unordered pair. That is the whole fix: **an ordering rule plus an idempotent key**, with no lock.

The check goes beyond the pair. A single one-sided swipe never matches; a retried swipe (three double-taps then the reply) still makes exactly one match; ids 9 and 10 give the key `(9, 10)` both ways (compare numerically, not as strings, or `"10" < "9"` flips the key); and 300 random runs with up to 12 users and shuffled schedules end with exactly the set of mutually liked pairs. A second 300-run batch with the unsafe order, built around one crossing pair, loses the match in more than 20 runs, which shows the test can see the bug.

**In a real store.** The two steps are two statements, and across shards they are two requests. The ordering rule still holds if "write" is durable before "read" starts and the read sees all durable writes (read from the primary, or a read-your-writes path). A read from a lagging replica brings the race back, because the other writer's row may not have arrived. If the like rows are sharded by swiper, the reverse lookup `(b, a)` goes to a different shard than the write; that is a network hop on every right swipe, which is why the sizing table counts reverse lookups at the right-swipe rate. Sharding by the unordered pair puts both rows on one shard, at the cost of fan-out when listing "who liked me".

**Notify after the match is durable.** Create the match row, then enqueue the notification (see Notification System). If the process dies between the two, a reconciler that scans recent matches without a sent flag repairs it; a notification without a match row would be a lie.

---

## 6. Deep Dive 2: The Seen Set

"Never show a judged profile again" is a set-membership test run for every candidate of every feed request. Exact storage is a list of ids per user: 855 KiB for the 109,500-swipe heavy user above, which is acceptable for one user and heavy across tens of millions. A Bloom filter stores the same set in about a seventh of the space with a tunable error. For `n` keys, `m` bits and `k` hashes, the false-positive rate is `(1 - e^(-kn/m))^k`; sizing for rate `p` gives `m = -n ln p / (ln 2)^2` and `k = (m/n) ln 2`.

```python
import hashlib, math
from collections import deque


def bloom_size(n, p):
    m = math.ceil(-n * math.log(p) / math.log(2) ** 2)
    return m, round(m / n * math.log(2))


def bloom_fp(m, k, n):
    return (1 - math.exp(-k * n / m)) ** k


class Bloom:
    def __init__(self, m_bits, k):
        self.m, self.k = m_bits, k
        self.bits = bytearray((m_bits + 7) // 8)

    def _idx(self, key):                      # two 64-bit halves of one digest give k positions
        h = hashlib.blake2b(str(key).encode(), digest_size=16).digest()
        a = int.from_bytes(h[:8], 'little')
        b = int.from_bytes(h[8:], 'little') | 1
        return [(a + i * b) % self.m for i in range(self.k)]

    def add(self, key):
        for i in self._idx(key):
            self.bits[i >> 3] |= 1 << (i & 7)

    def __contains__(self, key):
        return all(self.bits[i >> 3] >> (i & 7) & 1 for i in self._idx(key))


class RotatingSeen:
    """A Bloom filter cannot delete, so keep several generations and drop the oldest whole. A lookup asks every
    generation, so the false-positive rates add up: each generation is sized for p / gens, which makes the union about p."""
    def __init__(self, gens=3, n=1000, p=0.01):
        self.size = bloom_size(n, p / gens)
        self.gens = deque([Bloom(*self.size)], maxlen=gens)

    def add(self, key):
        self.gens[0].add(key)

    def rotate(self):
        self.gens.appendleft(Bloom(*self.size))   # maxlen drops the oldest generation

    def __contains__(self, key):
        return any(key in g for g in self.gens)
```

What the check pins down:

- `bloom_size(1000, 0.01)` is `(9586, 7)` and `bloom_size(100000, 0.01)` is `(958506, 7)`; at that size the formula returns 1 percent within 0.15 points.
- No false negatives: all 2,000 members are found. This is the property the product depends on, and it holds by construction.
- Measured false positives on 20,000 never-added ids are 1.16 percent (asserted between 0.5 and 1.6 percent), and a one-hash filter of the same size is 9.7 percent, more than three times worse. Every hash position is set on `add` (a filter that set only the first position would pass the no-false-negative test and fail the rate test).
- **What a false positive costs here.** A false positive hides a profile the user never saw. At 1 percent, a user with a 5,000-profile pool loses about 50 candidates, and they were never judged, so nobody can tell. The opposite error, showing a judged profile, cannot happen. This asymmetry is why a Bloom filter fits; for a "has this payment been processed" check it would not.
- `RotatingSeen` keeps three generations and answers yes if any of them does, so the rates add: three filters each sized for 1 percent give about 3 percent (2.75 percent measured on 50,000 never-added ids, a case the first draft of this lesson used as if it were 1 percent). The class sizes each generation for `p / gens`, and the check fills all three with 1,000 keys and requires the union rate to land between 0.5 and 1.6 percent. After four rotations, keys from the oldest two generations are gone (at most 4 of 200 sampled ones still answer yes, from false positives) and keys from the latest three generations are always found.
- **How long to remember.** Rotation is how the pool recycles, and the window decides which failure you get. A window **longer** than the time to exhaust the pool guarantees an empty feed from the day the pool runs out until the first entries expire; a window shorter than it guarantees unseen profiles exist, at the cost of showing old ones again. So choose the window at most the exhaustion time (50 days for a 5,000-profile pool at 100 swipes a day, 500 for a dense one), per pool density. The window is the number of generations times the length of one, and the live window varies between one generation less and the full count, so three generations of 15 days remember between 30 and 45 days: safe for the 50-day pool. The sizing table prices it: 4,500 ids in three generations of 1,500 each sized for 0.33 percent cost about 6.5 KiB, against 128 KiB for a never-forgotten heavy user.

Keep two things outside the filter: an exact short list of the last few dozen swipes (for "undo", which a Bloom filter cannot do), and the deny list for blocks, which must be exact. A blocked profile hidden by a 1-percent chance is a safety bug.

---

## 7. Deep Dive 3: Candidates, Ranking and the Same-People Problem

**Candidate query.** Filter by geo cover, age range and stated preferences, subtract the deny list, then subtract the seen filter. Do the cheap structural filters in the index and the seen filter last, on the short list. Fetch more than the page needs (the filter will remove some), and stop when the page is full.

**Ranking.** A one-sided score ("how popular is this profile") ranks the same people first for every viewer. A pair-aware score is the product of two estimates: the chance that I like them and the chance that they like me. A match needs both, so ranking by only the first fills your stack with people who would not like you back, and ranking by only the second fills it with people you would pass on. How the probabilities are estimated (a rating, a learned model) is a modelling decision this lesson does not prescribe. Rating systems that carry a measure of uncertainty are covered in Multiplayer Game Backend and Matchmaking.

**The exposure problem.** If every viewer sees the top of one global ranking, a few profiles receive huge attention and most receive almost none, and the lowest-ranked profiles never get the impressions needed to be ranked fairly. A per-round cap on how many viewers a profile can be shown to is a blunt but checkable fix.

```python
import random


def simulate_exposure(n=600, rounds=10, show=10, cap=None, seed=1):
    """Every round each viewer is shown `show` profiles they have not seen, taken from one ranked list.
    Returns total impressions, the share going to the most-shown 10 percent of profiles,
    and the most impressions any profile got in a single round."""
    rng = random.Random(seed)
    appeal = [rng.random() ** 2 for _ in range(n)]         # chance a viewer likes the profile
    likes, shown = [0] * n, [0] * n
    seen = [set() for _ in range(n)]
    total, worst = 0, 0
    for _ in range(rounds):
        jitter = [rng.random() for _ in range(n)]
        order = sorted(range(n), key=lambda i: (-(likes[i] + 1) / (shown[i] + 2), jitter[i]))
        quota = [cap if cap is not None else n] * n
        got = [0] * n
        for v in range(n):
            picked = 0
            for c in order:
                if c == v or c in seen[v] or quota[c] == 0:
                    continue
                quota[c] -= 1
                seen[v].add(c)
                got[c] += 1
                if rng.random() < appeal[c]:
                    likes[c] += 1
                picked += 1
                if picked == show:
                    break
        for i in range(n):
            shown[i] += got[i]
        total += sum(got)
        worst = max(worst, max(got))
    top = sorted(shown, reverse=True)[: n // 10]
    return {'impressions': total, 'top10_share': sum(top) / total, 'max_per_round': worst}
```

Illustrative result (seed 7, 600 profiles, 10 rounds, 10 cards per viewer per round; invented population, not data from any app): without a cap the most-shown 10 percent of profiles take 60 percent of impressions and one profile is shown to all 599 other viewers in a single round; with a cap of 30 per round the share is 29 percent and the maximum is 30. Both runs deliver the same 60,000 impressions, so the cap does not starve the feed. The check asserts the cap as a hard invariant, the share gap of more than 15 points, and that the run is deterministic.

This simulation shows only one effect: a single ranked list shared by all viewers concentrates impressions, and a cap spreads them. It does not show that any particular product ranks this way, and it says nothing about what a cap does to match rates. Measure that in an experiment, not in a lesson.

---

## 8. Failure Modes

| What breaks | What happens | Mitigation |
|---|---|---|
| Both swipes read before either writes | match lost, nobody notified | write first, then read; idempotent pair key (section 5) |
| Reverse lookup reads a lagging replica | the same lost-match race | read the reverse like from the primary, or a read-your-writes path |
| Match row written, process dies before notification | match exists, nobody told | reconciler scans recent matches without a sent flag |
| Bloom filter saturates (more keys than it was sized for) | false-positive rate climbs; feed shrinks | size per generation for the expected swipes in a window; rotate on schedule |
| Seen filter used for blocks | a blocked profile reappears with 1 percent chance | exact deny list, checked first |
| Pool exhausted | empty feed | rotation, widen filters, tell the user |
| Hot profile | one like row shard gets a flood of reverse lookups | cache a short list of "likes me" for very popular profiles; cap exposure |
| Client retries after lost reply | duplicate swipe | unique like key; idempotent match |

---

## 9. What Real Companies Did

No engineering post from Tinder or any other dating app could be read for this lesson: the Medium-hosted Tinder engineering pages returned HTTP 403 to a plain fetch on 27 November 2026, so their content is unknown here. So this lesson states nothing about how any dating app is built. Sections 5 to 7 are the general design, built from first principles and tested here. The pieces they use are public techniques: Bloom filters, geographic cell indexes (taught in Proximity Service & Location-Based Systems, whose sources are cited there) and rating systems (read in the Glicko papers cited in Multiplayer Game Backend and Matchmaking).

---

## 10. Pitfalls Checklist

1. Reading the reverse swipe before writing your own. Two crossing swipes lose the match; enumerate the interleavings to see it.
2. Creating the match without an idempotent key on the unordered pair. Both writers see each other and create two.
3. Keying the pair as `(a, b)` instead of `(min, max)`, or comparing ids as strings.
4. Using a lagging replica for the reverse lookup.
5. Storing left swipes in the same index as right swipes: three times the write volume for rows nothing reads.
6. A Bloom filter for blocks or payments, where a false positive is a real failure.
7. A Bloom filter you cannot rotate or resize, so the pool never recycles and the false-positive rate climbs.
8. Forgetting "undo": the filter cannot remove an id.
9. Ranking by one-sided popularity and then wondering why most profiles get nothing.
10. Quoting a company's matching algorithm you have not read.

---

## Drills

1. Why does write-then-read need an idempotent match key, and what does the key look like?
2. Describe the four schedules (of six) in which read-then-write loses a match by what both clients do first, and say what each client sees.
3. A user has swiped right 40,000 times over two years and the app wants a seen filter at 1 percent error. How many bits and hashes? (Use `bloom_size`.)
4. Your feed pool is 8,000 profiles and the user swipes 100 a day. When does it run out, and which design choice fixes it?
5. A false positive in the seen filter: what does the user lose, and why is that acceptable here but not for the deny list?
6. The reverse lookup reads a replica that is 200 ms behind. Describe a sequence of events that loses a match.
7. In the exposure simulation, what number would you look at to decide whether a cap of 30 is too tight, and what does the simulation not tell you?
8. Where does the geo index sit in the candidate query relative to the seen filter, and why?

---

## Homework

1. Run `swipe_steps` for three clients where A likes B, B likes C and C likes A. How many matches should exist? Check with all interleavings of the six steps that your code agrees. (Answer first on paper.)
2. Extend `SwipeStore` with an unmatch that deletes the match and both like rows, and decide what a second right swipe after unmatching should do. Write the tests that fix your decision.
3. Measure `Bloom` false positives for load factors n/m from 0.05 to 0.3 and compare each with `bloom_fp`. Where does the gap start to grow?
4. In `simulate_exposure`, replace the global ranked list with a list personalised by a random viewer-specific shuffle. Does the cap still matter? Explain what you measured.
5. Read the Proximity Service & Location-Based Systems lesson's cover code and write the candidate query that combines the cover, the deny list and `RotatingSeen`.

---

## Sources

All read on 27 November 2026.

- None for dating-app internals. The Tinder engineering pages on Medium returned HTTP 403 and were not read, so nothing is said about their content.
- The Bloom filter formulas in section 6 are stated in the lesson and checked numerically (sizes, measured false-positive rates of one filter and of three generations); no paper was consulted for them.
- Capacity figures are assumptions labelled as such in section 3.

## Further reading (not consulted)

- Tinder's engineering blog (Medium), not readable in this session.
- Bloom (1970), *Space/time trade-offs in hash coding with allowable errors*.
- Literature on reciprocal recommendation and two-sided marketplaces.

*Last reviewed: 27 November 2026.*
