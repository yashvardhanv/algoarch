# Lesson 76 — Case Study: Social Graph and "People You May Know"

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — "friends of friends" looks like a one-line join and is really a question about hubs, shards and what you are allowed to reveal.
>
> **Study time:** 55 minutes. **Do this after:** Graphs: BFS, DFS & Modelling; Caching Patterns and Consistent Hashing; Top-K and Trending.
>
> **Level:** extended.

The first idea everyone has is right: suggest the people who share the most friends with you. The interview is about everything after it: what that costs when one account has a million friends, how many machines a single request must visit, what you precompute and what you compute on demand, and which suggestions you must never show. This lesson builds the candidate generator and two scores as a small model, checked in `test/lesson_code/sy76_check.py` against a brute-force definition, with capacity numbers from `capacity_check_j.py`. No social network's engineering material was read; see Sources.

---

## 1. Mental Model

> **People You May Know is a two-hop traversal with a filter on both ends. The traversal is cheap for ordinary users and ruinous for hubs; the filter is where privacy and quality live.**

- **Candidates are friends of friends** who are not already friends, not you, and not blocked. A person's score is the evidence that you and they are close: common neighbours, optionally weighted so that a rare shared friend counts for more than a popular one.
- **Work is the sum of your friends' degrees.** For one user of 200 friends, each with 200, that is 40,000 visits; one friend with a million friends adds a million.
- **Hubs dominate the bill and carry the least signal.** Sharing a friend who has a million friends says almost nothing.
- **The graph is sharded by node,** so your friends are on many machines and a two-hop query touches almost all of them.
- **Most of this is computed offline** into a short list per user; the online path reads a list.

*Visual (planned): a user at the centre, friends on a ring, friends-of-friends beyond, with the count of paths into each candidate shown, and a hub whose spokes swamp the picture until the guard cuts it. Not built yet.*

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "suggest people you may know" | two-hop traversal, count common neighbours, drop friends, self and blocked (section 4) |
| "a celebrity has millions of friends" | skip or sample intermediates above a degree cap; measure what recall you lose (section 5) |
| "rank the suggestions" | common neighbours first; then weight rare shared friends more (Adamic/Adar); then features beyond the graph |
| "latency of the recommendation page" | read a precomputed top-k list per user; refresh in batch |
| "the graph does not fit on one machine" | shard by user id; a two-hop query fans out to most shards (section 5) |
| "what if two users blocked each other, or want privacy" | filters on both sides, and no counts that reveal a hidden relationship (section 8) |
| "how do we know the suggestions are good" | measure against a random baseline and against the simple counter, offline and with acceptance rates |

---

## 3. Requirements and Capacity

**Functional.** Return a short ranked list of non-friends for a user; exclude self, existing friends, blocked users and people who opted out; refresh as the graph changes. **Out of scope:** the friend-request flow, notifications, contact-book import, a learned ranking model.

**Non-functional.** The page must load from a stored list; the batch job must finish inside its window; one very large account must not break the job; no suggestion may expose a relationship its owner hid.

**Capacity estimate.** Every input is an assumption of this lesson (marked *assumed*), and real degree distributions are heavily skewed, which the uniform figures below deliberately ignore except for one hub. Results are reproduced by `capacity_check_j.py`.

| Input | Value |
|---|---|
| users | 100,000,000 *(assumed)* |
| average friends | 200 *(assumed, uniform for the arithmetic)* |
| bytes per stored id | 8 *(assumed)* |
| one very large account | 1,000,000 friends *(assumed)* |
| graph shards | 100 *(assumed)* |
| stored suggestions per user | 100 ids *(assumed)* |
| batch speed | 20,000,000 candidate visits per second per core, 1,000 cores *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| adjacency entries | 100,000,000 x 200 | 20 billion, 160 GB at 8 bytes |
| two-hop visits for one ordinary user | 200 x 200 | 40,000 |
| candidate data moved for one online request | 40,000 x 8 B | 320 KB, against 800 B for a stored list: 400 times more |
| two-hop visits across all users | 100,000,000 x 200 x 200 | 4 x 10^12 |
| one account with a million friends | 1,000,000 x 1,000,000 | 10^12 more: 20% of the new total of 5 x 10^12 |
| shards one 200-friend query touches | 100 x (1 - 0.99^200) | 86.6 of 100 |
| shards for a 1,000-friend query | 100 x (1 - 0.99^1000) | 100.0 of 100 (99.996) |
| stored suggestions | 100,000,000 x 100 x 8 B | 80 GB |
| batch time for the base work | 4 x 10^12 / (20,000,000 x 1,000) | 200 seconds |

Three conclusions. **One hub is a fifth of the job.** An account with a million friends adds as many two-hop visits as 25% of all the ordinary users together (10^12 against 4 x 10^12), for suggestions that mean nothing, since a million people share that friend with you. **Online two-hop is a fan-out to everything:** at 100 shards even a 200-friend user touches 86.6 shards on average, so latency is set by the slowest of dozens of calls. **So the page reads 800 bytes, not 320 KB,** and the traversal moves to a batch job whose cost the hub guard controls. The 200-second batch time rests entirely on assumed per-core speed and is a way to size the cluster, not a claim about any system.

---

## 4. The Model: Candidates and Two Scores

```python
import math
from collections import Counter

def build_graph(edges):
    """Undirected friendship graph: user -> set of friends. Self loops are dropped, duplicates merge."""
    g = {}
    for a, b in edges:
        if a == b:
            continue
        g.setdefault(a, set()).add(b)
        g.setdefault(b, set()).add(a)
    return g

def candidates(g, u, max_fanout=None, blocked=()):
    """Two-hop candidates of u. Returns (common-neighbour counts, Adamic/Adar scores, visits done).
    max_fanout: skip any intermediate friend with more friends than this (the hub guard)."""
    counts, adamic = Counter(), Counter()
    friends, work = g.get(u, set()), 0
    for z in friends:
        degree = len(g[z])
        if max_fanout is not None and degree > max_fanout:
            continue
        weight = 1 / math.log(degree) if degree > 1 else 0.0
        for v in g[z]:
            work += 1
            if v == u or v in friends or v in blocked:
                continue
            counts[v] += 1
            adamic[v] += weight
    return counts, adamic, work

def top_k(g, u, k, metric='common'):
    """The k best candidates as (user, score), ties broken by user id so the output is deterministic."""
    counts, adamic, _ = candidates(g, u)
    scores = counts if metric == 'common' else adamic
    return sorted(scores.items(), key=lambda p: (-p[1], p[0]))[:k]

def expected_shards_touched(shards, friends):
    """Expected number of distinct shards holding at least one of `friends` randomly placed friends."""
    return shards * (1 - (1 - 1 / shards) ** friends)
```

The two scores come from the link-prediction literature: Liben-Nowell and Kleinberg define "common neighbors" as `score(x, y) = |Γ(x) ∩ Γ(y)|` and a measure attributed to Adamic and Adar as the sum over shared neighbours `z` of `1 / log |Γ(z)|`, "weighting rarer features more heavily". Their data was co-authorship in physics preprints (arXiv sections), not a social platform, so what they measured transfers as an idea and not as a number: the paper reports several proximity measures beating a random predictor by factors of 40 to 50 on those networks. The traversal, the exclusion rules, the hub guard and the tie-breaking are this lesson's design.

What the check proves against definitions written separately:

- **Candidates equal the definition.** On 300 random graphs, every non-friend's common-neighbour count and Adamic/Adar score matches a brute-force loop over all users; self, friends and blocked users never appear.
- **The work counter is exactly the sum of the friends' degrees** (the arithmetic of section 3), and with the guard it is the sum over non-hub friends only.
- **The hub guard equals the definition restricted to non-hub intermediates,** for caps of 2, 3, 5 and 8 on 200 random graphs.
- **Ranking is deterministic:** sorted by score then id; two ties in a worked example come out in id order.
- **A rare friend beats a popular one:** with one shared friend of degree 2 and another of degree 22, plain counting ties and Adamic/Adar scores `1/log 2 = 1.44` against `1/log 22 = 0.32`.
- **The shards formula matches a simulation** for four (shards, friends) pairs within 1%, and equals 1 for a single friend or a single shard.

---

## 5. Deep Dive 1: The Hub Guard and What It Costs

Hubs are skipped as intermediates: a friend with more than `max_fanout` friends contributes no candidates. The model measures the trade on a random graph of 4,000 users and 24,000 random edges plus one account that is friends with everyone. For 400 sampled users, the guard (cap 100) cuts the total visits from about 1.67 million to about 67 thousand, 25 times fewer, and the check asserts a reduction of more than 20 times. **The top-10 lists do not change, and that is an artefact of how the graph was built:** an account that is friends with everyone adds exactly one common neighbour to every candidate, a constant that cannot reorder anyone, so skipping it loses nothing here. On a real graph, where a large account is friends with some people and not others, the lists would change; the method (run both, compare the lists, choose the cap from the loss you accept) transfers and the zero loss does not. Real graphs also have community structure that this random one lacks.

Three things the model does not do: sampling a hub's friends instead of skipping it; weighting by recency or interaction; and capping the number of candidates stored per user. The honest claim is only that the guard removes the quadratic blow-up and that its cost in suggestion quality must be measured on your own graph.

---

## 6. Deep Dive 2: Sharding and the Fan-Out

A graph sharded by user id stores each person's friend list on one shard, so expanding your friends' friend lists means one request per friend, routed to wherever that friend lives. With friends placed independently and uniformly, the number of distinct shards is `S x (1 - (1 - 1/S)^d)`. The check confirms the formula by simulation. For S = 100: a user with 10 friends touches 9.6 shards, one with 200 touches 86.6, one with 1,000 touches all 100. **The fan-out saturates:** past a few hundred friends, adding friends adds work but not new shards, so latency is the slowest shard and a retry storm is a real risk (see Overload, Load Shedding and Cascading Failures). Two remedies, both partial: batch the per-shard requests so each shard gets one call with many ids (the shard count, not the friend count, bounds the calls), and precompute, which turns the whole path into a read.

Placement that keeps friends together (by community or by locality) cuts the fan-out, and it is not modelled here and not sourced.

---

## 7. Deep Dive 3: Batch, Online and the Stale List

| Choice | Behaviour | Cost |
|---|---|---|
| online two-hop per request | always fresh | 320 KB moved and 86.6 shards touched per request (section 3); unusable for page loads |
| nightly batch into a stored top-100 | page reads 800 B | the list is up to a day old; a new friendship appears tomorrow; 80 GB stored |
| batch plus a small online patch | batch list, then drop anyone who has since become a friend or been blocked | cheap, and removes the worst stale artefacts |

The stale list has one dangerous failure and several cosmetic ones. **Cosmetic:** someone you met yesterday is missing; a person who joined today is absent. **Dangerous:** a user you blocked, or who blocked you, still appears. So the online path must apply the block and friend filters at read time even when the list is precomputed. The model's `blocked` argument is the batch-time version of that filter and does not by itself solve the read-time one.

---

## 8. Failure Modes and What You Must Not Reveal

| Failure | What goes wrong | Mitigation |
|---|---|---|
| a hub in the graph | the batch job's quadratic term explodes | hub guard; measure the quality it costs |
| list shows a blocked user | harm, not a quality issue | read-time filter against blocks and friends |
| mutual-friend counts or names shown | can reveal a relationship the other person hid | show counts only from relationships the viewer may see; no claim here on what any product does |
| a new user with no friends | no two-hop candidates | needs signals outside the graph (not modelled) |
| a shard is slow or down | the online fan-out stalls or returns partial candidates | prefer the stored list; treat partial results as partial |
| an unknown user id | no friends, no candidates | the model returns an empty list, no crash |
| suggestions that never get accepted | the ranking is not helping | compare against random and against plain common-neighbour ranking, offline and by acceptance rate |

---

## 9. What Real Systems Did

No engineering article or paper from a social network was read for this lesson. The single source consulted is the link-prediction paper above, which studied co-authorship networks and says nothing about how a platform builds or serves its suggestions. Everything about sharding, batching, hub handling and privacy here is the lesson's own general design, labelled as such.

---

## 10. Pitfalls Checklist

1. **Counting all friends' friends without a degree guard.** One account can be a fifth of the job.
2. **Running the traversal online.** 320 KB and most of the shards for one page view.
3. **Recommending friends of friends who are already friends.** The exclusion is part of the definition.
4. **Forgetting both directions of a block.** Filter on either side.
5. **Plain counts only.** A rare shared friend is stronger evidence than a popular one.
6. **Non-deterministic ties.** Two runs give different lists; break ties by id.
7. **Showing mutual-friend details without a privacy rule.** It can reveal what someone hid.
8. **Trusting a recall number from a different network.** The paper's factors of 40 to 50 are for co-authorship graphs.

---

## Drills

1. A user has 150 friends, each with 300 friends. How many two-hop visits, and how many bytes of candidate ids at 8 bytes each?
2. A graph has 50 million users with 100 friends each. Total two-hop visits, and the extra visits from one account with 2 million friends.
3. Compute `S x (1 - (1 - 1/S)^d)` for S = 50 and d = 20, 100 and 500. At what d does the fan-out reach 99% of the shards?
4. A user shares friend A (degree 4) with candidate X and friend B (degree 400) with candidate Y. Which has the higher Adamic/Adar score, and why does plain counting tie?
5. Choose `max_fanout` for a graph where 0.1% of users have more than 10,000 friends and the rest have under 1,000. What would you measure before fixing it?
6. In `candidates`, remove the `v in friends` test. What changes in the output, and which check fails?
7. Design the read path for a page that must load in 100 ms, given the stored top-100 list, a block list and a friends list. Which filters run at read time?
8. Explain why a two-hop query on a graph sharded by user id touches nearly all shards for a 300-friend user, and name one way to reduce it and one cost.

---

## Homework

1. Add a `sample_fanout` option that samples at most N friends of each hub instead of skipping the hub, and compare work and top-10 overlap with the skip guard on a synthetic graph where the large account is friends with only half the users (on the check's graph, where it is friends with everyone, any guard changes nothing).
2. Extend `candidates` to weight each shared friend by a recency or interaction score passed in, and write a check that fails first on an unweighted implementation.
3. Add a stored-list refresher: given yesterday's list and today's new edges, update only the affected users. State how many users that touches for a given edge, in terms of the endpoints' degrees.
4. Read the link-prediction paper's description of its baselines (random, graph distance, common neighbours) and design an offline evaluation for your own graph using a held-out set of new friendships.

---

## Sources

All read on 27 November 2026.

- David Liben-Nowell and Jon Kleinberg, *The Link Prediction Problem for Social Networks* (cs.cornell.edu/home/kleinber/link-pred.pdf, the January 2004 version, read in part as extracted text: the definitions of common neighbours and of the Adamic/Adar measure, the random-predictor baseline, and the abstract's statement that several proximity measures outperform chance by factors of 40 to 50 on the arXiv co-authorship networks studied; the result tables were extracted in scrambled form and no table figures are quoted).
- Not read: Adamic and Adar's original paper, any social network's engineering writing on suggestion systems, any paper on graph partitioning or community-aware placement, and any privacy guidance.

## Further reading (not consulted)

- Adamic and Adar, *Friends and neighbors on the web*.
- Engineering write-ups of large social graph stores and recommendation pipelines.
- Graph-partitioning literature for placing friends together.

*Last reviewed: 27 November 2026.*
