# Lesson 54 — Case Study: Web Crawler

> **Priority:** ★★★★☆ — asked directly at search, data and AI-training teams, and a clean test of queues, hashing and being a good citizen at scale.
>
> **Study time:** 75 minutes. **Do this after:** Caching and Consistent Hashing (sy45) and the Distributed Message Queue case study (sy36).
>
> **Level:** core.

A crawler repeatedly takes a URL, downloads the page, pulls out the links and adds the new ones to its to-do list. That is
ten lines of code. The interview is about everything that breaks when the web is the input: you must not hammer one
server, you cannot hold every URL you have ever seen in memory, and some sites are infinite on purpose or by accident.
This lesson builds the pieces that carry the design (URL canonicalisation, a `robots.txt` matcher, a polite
prioritising frontier, a duplicate-URL eliminator and a per-host budget), runs them together on a fake web, and checks
them against independent references in `test/lesson_code/sy54_check.py`. Every capacity figure is reproduced by
`test/lesson_code/capacity_check_c.py`.

---

## 1. Mental Model

> **A crawler is a scheduler wearing a downloader's clothes. Fetching is easy and parallel; the design is deciding
> which URL goes next (priority and politeness), remembering what you have already seen (billions of keys), and
> limiting the damage any one host can do to you or you to it.**

What follows from it:

- **The frontier is the heart.** Clients choose what to add; the frontier alone decides what comes out and when, so it
  controls speed, fairness to hosts, and freshness.
- **Politeness is per host, not per worker.** A worker pool pulling from one FIFO queue hammers one site, because links
  on a page mostly point to the same site.
- **"Seen before?" is asked once per extracted link,** about forty times per page in this lesson's model, so it is the
  hottest data structure and the first one to outgrow memory.
- **The web is adversarial and sloppy.** Duplicates, mirrors, infinite calendars and slow servers are normal inputs, so
  every loop needs a budget.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "do not overload a site" | per-host queues, a next-allowed-time per host, a heap of hosts ordered by that time |
| "billions of URLs, avoid duplicates" | fingerprint the URL (8 bytes), keep fingerprints in a sorted, partitioned store, batch the lookups |
| "same page at many URLs" | content fingerprint, checked after download ("content seen") |
| "crawl important pages first / keep pages fresh" | priority levels in front of the politeness queues, priority from download history |
| "infinite site" or "calendar trap" | per-host page budget, depth limits, give budget in proportion to who links to the host |
| "respect site owners" | `robots.txt`, cached up to 24 hours, with explicit rules for 4xx and 5xx |
| "scale to many machines" | partition by host name, so each machine owns whole hosts and their politeness state |
| "DNS is slow" | your own resolver pool and cache; do not rely on the operating system's serial resolver |

---

## 3. Requirements and Capacity

**Functional.** Start from seed URLs, fetch pages over HTTP(S), extract links, and hand each page's content to a
downstream consumer (an indexer or a dataset writer). Re-crawl pages on a schedule. **Out of scope here:** parsing
JavaScript-rendered pages, near-duplicate detection, ranking.

**Non-functional.** Polite (never two requests in flight to one host, and a pause between requests). Scalable beyond
memory. Fault tolerant: a restart must not re-crawl the world. Extensible: new content types and URL filters.

**Capacity estimate.** Inputs are **assumptions**; every result is reproduced by `test/lesson_code/capacity_check_c.py`.

| Input (assumed) | Value |
|---|---|
| pages to keep fresh | 10 billion |
| full refresh cycle | 30 days |
| average fetched page | 300 KB (measure yours) |
| links extracted per page | 40 |
| average fetch latency per request | 1 second |
| politeness wait | 10 times the last fetch time (Mercator's rule) |
| distinct URLs known | 50 billion |
| fingerprint size | 8 bytes |
| crawler partitions | 64 |
| share of links that are relative (same host) | 80% (Mercator measured this) |
| distinct hosts | 100 million |

| Result | Arithmetic | Value |
|---|---|---|
| fetch rate | 10 billion / (30 x 86,400 s) | 3,858 pages per second |
| download bandwidth | 3,858 x 300 KB | 9.3 Gbit/s |
| raw page storage per refresh cycle | 10 billion x 300 KB | 3 PB |
| duplicate-URL checks | 3,858 x 40 | 154,321 URLs per second |
| concurrency (Little's law) | 3,858 per second x 1 s | 3,858 fetches in flight |
| hosts that must be ready at once | 3,858 x (1 s fetch + 10 s wait) | 42,438 hosts |
| one host's fastest rate | 1 per (1 s + 10 s) | one request every 11 seconds |
| a 10-million-page site at that rate | 10 million x 11 s / 86,400 | 1,273 days |
| fingerprints for all known URLs | 50 billion x 8 B | 400 GB |
| partition share | 50 billion / 64 | 781,250,000 URLs |
| accidental fingerprint collisions | 50 billion² / 2 / 2⁶⁴ | about 68 colliding pairs |
| links that cross partitions | 20% non-relative x 63/64 | about 19.7% |
| `robots.txt` refreshes at a 24-hour cache | 100 million / 86,400 | 1,157 robots.txt fetches per second |

Five conclusions. **Politeness, not bandwidth, limits you:** at one request per 11 seconds per host you need tens of
thousands of different hosts ready at once to reach this rate. **A huge host is a problem, not a prize:** a
10-million-page site takes 1,273 days at the polite rate, so you need a budget and a priority for such sites, or they
sit in your queues forever. **The URL-seen set is 400 GB and must be partitioned or disk based,** and its lookups run
at 154,321 URLs per second. **Eight bytes per URL is enough** because about 68 colliding pairs among 50 billion URLs
means about 68 pages wrongly skipped, which is noise. **Partition by host:** then the cross-partition traffic is only
the 19.7% of links that leave the host, and each partition's politeness state is local.

Mercator's authors give the opening figure for a billion pages in a month: about 386 per second (this lesson's cycle
is three times larger). Their 2000 crawl on four machines averaged about 50 million documents a day for 17 days.

Visual (planned): the crawl loop as a ring: frontier, fetcher, content-seen, link extractor, URL filter, duplicate-URL eliminator, back to the frontier, with the partition router on the extractor-to-eliminator edge.

---

## 4. API and Data Model

```
frontier.add(url, priority)      frontier.pop(now) -> url | none      frontier.done(url, now, seconds_taken)
due.submit(url)                  due.flush() -> [urls never seen before]
robots_cache[host] -> rules, fetched_at (valid at most 24 hours; shorter on errors)
page record: {url, fetched_at, status, content_fingerprint, outlinks[], body_ref}
host record: {host, next_allowed_at, pages_fetched, linking_hosts}
```

The fetch loop, in the order Mercator's authors describe it: take a URL from the frontier, resolve the host, fetch
(first `robots.txt` for the host, from a cache), run the **content-seen** test on the body, extract links with a
processing module for the content type, apply the **URL filter**, submit survivors to the **duplicate-URL eliminator**,
which hands only new ones to the frontier. A single background thread logs statistics and writes **checkpoints** so a
failed crawl resumes from the last one, losing only the work since then.

Each partition owns a set of hosts (hash of host name). A link extracted on partition A to a host owned by B is
buffered and sent to B in a batch, where it goes through B's eliminator and frontier. No state is replicated.

---

## 5. Deep Dive 1: URLs and robots.txt

Two URLs that differ in case, a default port or a fragment are the same page, and the eliminator can only see that if
URLs are first reduced to one form. RFC 3986 section 6.2 lists the safe rules: lower-case the scheme and host, uppercase
the hex in percent escapes and decode escapes of unreserved characters, remove dot segments (`/a/../b`), turn an empty
path into `/`, and drop a port that is empty or the scheme's default. The fragment never reaches the server, so drop
it. Sorting query parameters or dropping tracking parameters is **not** in the RFC; it is a policy you choose, and a
wrong choice merges pages that differ, so this lesson leaves queries alone.

```python
import re, random, heapq, hashlib, collections
from urllib.parse import urlsplit, urlunsplit, urljoin

def remove_dot_segments(path):                    # path starts with "/"
    out, segs = [], path.split('/')[1:]
    for i, s in enumerate(segs):
        last = i == len(segs) - 1
        if s == '.':
            if last: out.append('')
        elif s == '..':
            if out: out.pop()                     # ".." above the root is ignored
            if last: out.append('')
        else:
            out.append(s)
    return '/' + '/'.join(out)

def _unescape(m):
    ch = chr(int(m.group(1), 16))
    return ch if ch.isascii() and (ch.isalnum() or ch in '-._~') else '%' + m.group(1).upper()

def canonicalize(url):
    p = urlsplit(url)
    scheme, host = p.scheme.lower(), p.netloc.lower()
    host, _, port = host.partition(':')
    if port == '' or (scheme, port) in (('http', '80'), ('https', '443')):
        netloc = host
    else:
        netloc = host + ':' + port
    path = remove_dot_segments(p.path or '/')
    path = re.sub(r'%([0-9a-fA-F]{2})', _unescape, path)
    query = re.sub(r'%([0-9a-fA-F]{2})', _unescape, p.query)
    return urlunsplit((scheme, netloc, path, query, ''))
```

The check compares `remove_dot_segments` with a literal transcription of the RFC's two-buffer algorithm on 3,000
random paths, asserts idempotence (`canonicalize(canonicalize(u)) == canonicalize(u)`), and runs the table of cases.
The sketch ignores user-info, IPv6 literals and internationalised hosts; a production normaliser must handle them.

**robots.txt.** The Robots Exclusion Protocol became RFC 9309 in September 2022. The rules that matter for an
implementation: crawlers pick the group whose product token matches theirs (case-insensitively), else the `*` group,
else no rules apply; matching groups for the same token are merged; for a path, **the matching rule with the most
octets wins, and if an allow and a disallow tie the allow wins**; `*` matches any run of characters and a trailing `$`
anchors the end; `/robots.txt` itself is always allowed. Fetch results matter: a `4xx` answer means "unavailable",
so the crawler may fetch anything; a `5xx` or network failure means "unreachable", and the crawler must assume complete
disallow, though after a long outage (the RFC's example is 30 days) it may treat the file as absent. Cache for at most
24 hours unless the file is unreachable, and impose a parse limit of at least 500 KiB.

```python
def parse_robots(text):
    groups, cur, after_agent = [], None, False    # a group is (set of agent tokens, list of (allow, pattern))
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key, val = key.strip().lower(), val.strip()
        if key == 'user-agent':
            if not after_agent:
                cur = (set(), []); groups.append(cur)
            cur[0].add(val.lower()); after_agent = True
        elif key in ('allow', 'disallow'):
            after_agent = False
            if cur is not None and val:           # an empty "disallow:" adds no rule: everything stays allowed
                cur[1].append((key == 'allow', val))
    return groups

def pattern_matches(pat, path):
    anchored = pat.endswith('$')
    parts = (pat[:-1] if anchored else pat).split('*')
    if not path.startswith(parts[0]):
        return False
    pos = len(parts[0])
    if len(parts) == 1:
        return path == parts[0] if anchored else True
    for mid in parts[1:-1]:
        i = path.find(mid, pos)
        if i < 0:
            return False
        pos = i + len(mid)
    last = parts[-1]
    if anchored:
        return path.endswith(last) and len(path) - len(last) >= pos
    return path.find(last, pos) >= 0

class Robots:
    def __init__(self, groups=(), deny_all=False):
        self.groups, self.deny_all = list(groups), deny_all

    def can_fetch(self, token, path):
        if path == '/robots.txt':
            return True
        if self.deny_all:
            return False
        token = token.lower()
        mine = [g for g in self.groups if token in g[0]] or [g for g in self.groups if '*' in g[0]]
        best = None
        for _, rules in mine:
            for allow, pat in rules:
                if pattern_matches(pat, path):
                    key = (len(pat), allow)       # longest pattern wins; on a tie True (allow) beats False
                    if best is None or key > best:
                        best = key
        return True if best is None else best[1]

def robots_policy(status, text):
    if status is not None and 200 <= status < 300:
        return Robots(parse_robots(text))
    if status is not None and 400 <= status < 500:
        return Robots()                           # unavailable: no rules
    return Robots(deny_all=True)                  # 5xx or unreachable: assume complete disallow
```

The check runs the RFC's own longest-match example, ties, `*` and `$`, group selection, merging, comments, orphan rules
and the status policy, then compares 24,000 random (rule set, path) pairs with a regular-expression matcher written
separately. Two honest limits: pattern length is counted as written (including `*`), and percent-encoding of the
robots path is not normalised. Real parsers differ on such corners, which is why large crawlers test against Google's
published behaviour rather than a lesson's sketch.

---

## 6. Deep Dive 2: The Polite, Prioritising Frontier

A single FIFO queue gives breadth-first order, but pages link mostly to their own site, so the queue fills with runs of
one host and parallel workers hit one server together. Mercator's authors call "only one connection to a host at a
time" the **weak politeness guarantee**, and report that crawls under it still drew a handful of complaints from
administrators, because requests to a host could arrive back to back. Their strong form rate-limits each host.

The design (their Figure 3) has two layers:

- **Front end:** `k` FIFO queues, one per priority. A *prioritizer* assigns the priority from the URL and its download
  history (their example: did the page change since the last fetch?).
- **Back end:** `n` FIFO queues, each non-empty and each holding URLs of **one host only**, a table from host to queue,
  and a **heap of queues ordered by the time the host may be contacted again**. To fetch, a worker takes the heap's
  root (waiting until its time has come) and the head URL of that queue. When the download ends, the worker sets the
  host's next time to *now plus a multiple of the download time*, puts the queue back in the heap, and, if the queue
  emptied, refills it from the front end by picking a priority queue at random **biased towards high priority**.

The wait multiplier and the number of back queues go together: more waiting needs more queues to keep workers busy.
In production crawls Mercator used three times as many back queues as threads and waited ten times the last download
time. In this lesson's capacity model that wait makes one host serve one request every 11 seconds, which is where the
42,438-ready-hosts figure comes from. The back queues live mostly on disk in a real crawl, with a few URLs buffered at
each end.

```python
def host_of(url):
    return urlsplit(url).netloc

class Frontier:
    def __init__(self, k, n_back, wait_factor, rng):
        self.k, self.n_back, self.wait_factor, self.rng = k, n_back, wait_factor, rng
        self.front = [collections.deque() for _ in range(k)]
        self.back = {}                    # host -> deque of urls; every host here is in the heap or in flight
        self.heap = []                    # (ready_at, host) for hosts that are not in flight
        self.ready_at = {}                # host -> next allowed time; survives the queue being emptied
        self.inflight = set()

    def add(self, url, prio):
        self.front[min(max(prio, 0), self.k - 1)].append(url)
        self._fill()

    def _fill(self):
        while len(self.back) < self.n_back:
            live = [i for i, q in enumerate(self.front) if q]
            if not live:
                return
            i = self.rng.choices(live, weights=[self.k - j for j in live])[0]   # bias to priority 0
            url = self.front[i].popleft()
            h = host_of(url)
            if h in self.back:
                self.back[h].append(url)
            else:
                self.back[h] = collections.deque([url])
                heapq.heappush(self.heap, (self.ready_at.get(h, 0), h))

    def pop(self, now):
        if not self.heap or self.heap[0][0] > now:
            return None
        _, h = heapq.heappop(self.heap)
        self.inflight.add(h)
        return self.back[h].popleft()

    def done(self, url, now, took):
        h = host_of(url)
        self.inflight.discard(h)
        self.ready_at[h] = now + self.wait_factor * took
        if self.back[h]:
            heapq.heappush(self.heap, (self.ready_at[h], h))
        else:
            del self.back[h]
            self._fill()

    def next_ready(self):
        return self.heap[0][0] if self.heap else None

    def pending(self):
        return sum(map(len, self.front)) + sum(map(len, self.back.values()))
```

`ready_at` is the detail to keep: when a host's queue empties it leaves `back`, and if the timestamp left with it, a
URL for the same host arriving a second later would be fetched at once and break the rate limit. A dedicated test
covers that case. The main check simulates 400 random crawls with several workers, children discovered while crawling,
and random fetch times, then **audits the fetch log after the fact**: every discovered URL fetched exactly once, no two
fetches of a host overlap, and each host's next fetch starts no sooner than ten times the previous download time after
it ended. A separate run confirms the bias: with 90 URLs of three priorities and one worker, the mean output position
rises with the priority number.

Freshness uses the same machinery. Mercator's continuous-crawl configuration re-adds each downloaded URL to the
frontier with a priority computed from its history, and in one configuration the priority of a page that did not change
between downloads decreases over time, so stable pages are fetched less often. The design question is how to split
fetches between new URLs and refreshes; the priority levels are the dial.

---

## 7. Deep Dive 3: Seen Sets, Budgets and the Whole Loop

**URL-seen.** Mercator's in-memory duplicate-URL eliminator keeps 8-byte fingerprints of URLs, made with Rabin's
fingerprinting; they report that a billion URLs take slightly over 5 GB that way. Their first disk-based version kept the
fingerprint table on disk with a memory cache: one in six submissions still went to disk, and because fingerprints have
almost no locality each of those cost a seek. At 8 ms per seek that is 125 seeks, or 750 DUE submissions, per second;
with about ten links per page it caps the crawl at 75 downloads per second. Their fix, which the lesson reproduces,
is to **batch**: new fingerprints collect in an in-memory table; when it fills, it is sorted and merged in one
sequential pass into the sorted file of all fingerprints, and only URLs that were new join the frontier. Disk becomes a
sequential merge instead of a random seek per link. They note the merge time eventually exceeds the fill time, so
throughput still decays as the file grows; the IRLbot authors (see Sources) report a bucket-sort based disk repository
that avoids this (only their summary of it was read).

```python
def fingerprint(url, bits=64):
    return int.from_bytes(hashlib.sha256(url.encode()).digest()[:bits // 8], 'big')

class BatchDue:
    """Sorted 'file' F of fingerprints plus a buffer T; flush() merges T into F and returns the new URLs."""
    def __init__(self, bits=64):
        self.bits, self.F, self.T = bits, [], {}

    def submit(self, url):
        fp = fingerprint(url, self.bits)
        if fp in self.T or self._in_file(fp):
            return
        self.T[fp] = url                              # remember first-seen order

    def _in_file(self, fp):
        from bisect import bisect_left
        i = bisect_left(self.F, fp)
        return i < len(self.F) and self.F[i] == fp

    def flush(self):
        new = list(self.T.values())
        self.F = list(heapq.merge(self.F, sorted(self.T)))   # sequential merge of two sorted runs
        self.T = {}
        return new
```

SHA-256 is a stand-in for Rabin fingerprinting; any well-mixed hash does the job. The check models it against a set
with the same fingerprint function, for 8-, 16- and 64-bit fingerprints (small sizes collide on purpose, and the
reference collides identically), asserts that `F` stays sorted and unique, and measures the **birthday collision rate**
on 16-bit fingerprints: the average number of colliding pairs in 2,000 URLs lands within 20% of `n(n-1)/2 / 2^bits`,
the formula behind "about 68 colliding pairs" in the capacity table. A collision here means a new URL is judged
already seen and never crawled: a silent loss, harmless at that rate, which is the reasoning for 8 bytes.

**Content-seen.** After download, fingerprint the body; if it was seen, do not extract links again. This catches
mirrors and the same page at several URLs. It catches only exact duplicates; near-duplicate detection is a separate
topic not covered here.

**Budgets and traps.** In IRLbot's paper, breadth-first order eventually fills the queue with links from spam sites
with high branching, and infinite pages generated by server-side scripts keep a crawler busy for ever. Their remedy for
sites is a budget of allowed pages per domain that grows with the number of links from *other* domains (they call the
algorithm STAR), because a spammer can create unlimited pages and hostnames but cannot easily make other domains link
to them. Over-budget URLs go to queues that are examined less often (BEAST) rather than being re-scanned constantly.
The lesson keeps the idea and drops the queues: pages over budget are simply dropped.

```python
class Budget:
    def __init__(self, per_link=10, floor=5):
        self.per_link, self.floor = per_link, floor

    def cap(self, linking_hosts):
        return max(self.floor, self.per_link * len(linking_hosts))

def owner(host, n_partitions):
    return int.from_bytes(hashlib.sha256(host.encode()).digest()[:8], 'big') % n_partitions
```

`owner` is the partition function: every URL of a host lands on one machine, so that machine alone holds the host's
politeness clock, its robots cache and its budget. When partitions come and go, replace the modulus with the ring from
sy45 so only a fraction of hosts move. The check verifies that 16,000 hosts spread over 16 partitions within 20% of an
even split.

```python
def crawl(fetch, seeds, agent, budget, stats=None, max_pages=10 ** 6):
    """fetch(url) -> (status, body, hrefs). Single machine, virtual clock, 1 second per fetch."""
    stats = {} if stats is None else stats
    stats.update(processed=0, duplicates=0, robots=0, blocked=0, over_budget=0)
    fr, due = Frontier(3, 50, 10, random.Random(0)), BatchDue()
    robots, bodies, used = {}, set(), collections.Counter()
    linkers, depth, fetched = collections.defaultdict(set), {}, []

    def discover(url, d, from_host=None):
        if urlsplit(url).scheme.lower() not in ('http', 'https'):
            return
        c = canonicalize(url)
        h = host_of(c)
        if from_host and from_host != h:
            linkers[h].add(from_host)                 # budget grows with distinct linking hosts
        due.submit(c)
        for new in due.flush():
            depth[new] = d
            fr.add(new, min(d, 2))

    for s in seeds:
        discover(s, 0)
    now = 0
    while len(fetched) < max_pages:
        u = fr.pop(now)
        if u is None:
            now = fr.next_ready()
            if now is None:
                break
            continue
        p, h = urlsplit(u), host_of(u)
        if h not in robots:
            status, text, _ = fetch('%s://%s/robots.txt' % (p.scheme, h))
            stats['robots'] += 1
            robots[h] = robots_policy(status, text)
        if not robots[h].can_fetch(agent, p.path + ('?' + p.query if p.query else '')):
            stats['blocked'] += 1
            fr.done(u, now, 0)
            continue
        if used[h] >= budget.cap(linkers[h]):
            stats['over_budget'] += 1
            fr.done(u, now, 0)
            continue
        used[h] += 1
        status, body, hrefs = fetch(u)
        now += 1
        fr.done(u, now, 1)
        if status != 200:
            continue
        fetched.append(u)
        key = hashlib.sha256(body.encode()).digest()
        if key in bodies:
            stats['duplicates'] += 1
            continue
        bodies.add(key)
        stats['processed'] += 1
        for href in hrefs:
            discover(urljoin(u, href), depth[u] + 1, h)
    return fetched
```

The end-to-end check builds 250 random fake webs (several hosts, mixed-case hosts and schemes, fragments, relative links
with dot segments, `mailto:` links, mirrors with identical bodies, hosts with different robots rules or a failing
`robots.txt`), crawls them, and compares the set of fetched URLs with a separate breadth-first reference. It also checks
that the number of processed pages equals the number of distinct bodies. A trap test gives one host an endless chain of
fresh URLs: with a budget of 10 for a host linked from one domain, the trap stops after exactly 10 pages while the
ordinary pages finish.

---

## 8. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| DNS lookups serialise | workers idle waiting for names | a parallel resolver pool in front of a local name server; Mercator measured lookups at 70% of each thread's elapsed time with the system resolver and 14% with theirs |
| infinite or spam site | queue and storage fill with one domain | per-host budget, depth cap, priority by in-links |
| huge legitimate site | its URLs sit in RAM waiting out politeness | budget and a separate slow queue; do not let one host consume the back queues |
| slow or hostile server | fetch threads tied up (IRLbot describes a "delay attack" with deliberate HTTP and DNS delays) | timeouts, a cap on time per host, count slow hosts against their budget |
| `robots.txt` returns 5xx | you must assume disallow | back off and retry; do not guess "allowed" |
| crawler node dies | its hosts stop | checkpoint the frontier and seen set (Mercator: 1 to 4 times a day); on restart reload; work since the checkpoint is repeated |
| complaints | site owners block you | a clear user-agent with a contact page (RFC 9309 asks the product token to be part of it), obey the rate limit, and staff the inbox (Brin and Page describe near-daily emails) |

---

## 9. What Real Companies Did

- **Mercator** (Najork and Heydon, SRC Research Report 173, 26 September 2001, read in full 2026-11-26): Compaq's
  crawler, used in AltaVista's search product. Host-partitioned distribution, the polite frontier, three duplicate-URL
  eliminators, and the DNS finding. A December 2000 crawl processed 891 million URLs in 17 days on four machines; of
  847 million HTTP requests, 725 million returned 200. About 80% of links were relative.
- **The original Google crawler** (Brin and Page, 1998, section 4.3 read): a URL server feeding about three crawlers,
  each keeping roughly 300 connections open with asynchronous I/O; peak above 100 pages per second with four crawlers;
  a DNS cache per crawler. Their summary: crawling is "the most fragile application" because it depends on servers
  beyond your control.
- **IRLbot** (Lee, Leonard, Wang, Loguinov, WWW 2008; abstract and introduction read): one server, 41 days, 6.3 billion
  pages, 1,789 pages per second on average, from 117 million hosts. Contributions: DRUM for URL checks, STAR for
  reputation budgets, BEAST for over-budget URLs.
- **RFC 9309** (September 2022, read in full): the formal robots protocol described above; two of the authors work at
  Google.
- No public description of the current crawlers of Google, Bing or Common Crawl was read for this revision, so no claim
  about them is made.

---

## 10. Pitfalls Checklist

1. **One shared FIFO queue** with many workers: every worker lands on the same host.
2. **Politeness by worker count** instead of by host and time.
3. **Forgetting the host's next-allowed time when its queue empties** (the late-arrival test).
4. **Storing full URLs in the seen set** and discovering the memory bill at a billion URLs.
5. **A disk lookup per link:** at 8 ms a seek, 125 lookups per second per disk.
6. **Skipping `robots.txt` handling for errors:** treating a 5xx as "no restrictions".
7. **Normalising too much:** merging URLs whose queries differ changes which pages exist.
8. **No budget:** one calendar or spam farm can take the whole crawl.
9. **Dedup only by URL,** so mirrors multiply storage and work.
10. **Quoting a 2001 or 2008 crawl's numbers as today's capacity:** use them as shapes, not targets.

---

## Drills

1. Why does a single FIFO frontier with 200 worker threads violate politeness even though each fetch is individually
   fine?
2. In the Mercator frontier, which structure enforces "wait ten times the last download time", and what happens to
   that timestamp when a host's back queue empties?
3. From the capacity table: how many hosts must be ready at once to sustain the fetch rate, and what changes if you
   wait 5 times the download time instead of 10?
4. Why 8-byte fingerprints rather than 4, and what does one collision cost?
5. Explain why partitioning by host name beats partitioning by URL hash for politeness, and what fraction of links
   cross partitions when 80% are relative.
6. Under RFC 9309, what must a crawler do if `/robots.txt` returns 404, and what if it returns 503? A site's file says
   `allow: /a` and `disallow: /a` for your agent: may you fetch `/a`?
7. A crawler at 8 ms per disk seek, 1-in-6 cache misses and ten links per page: derive the maximum crawl rate of the
   seek-bound eliminator.
8. A calendar site generates `/day/2031-01-01`, `/day/2031-01-02`, and so on without end. Give two independent
   defences and say what each would stop.

---

## Homework

1. Replace the sleep-free virtual clock in `crawl` with a thread pool and a real `Frontier` lock; run it against a local
   test server with ten hosts and verify the audit from the check on the real fetch log.
2. Add near-duplicate detection with a 64-bit SimHash of the body; measure false merges on a small corpus you collect.
3. Add re-crawl: give each page a change history and set its priority from it (as in Mercator's configuration); simulate
   pages that change at different rates and plot fetches wasted on unchanged pages.
4. Replace `owner` with the consistent-hash ring from sy45; measure how many hosts move when a partition is added.
5. Implement the batch merge on real files with `heapq.merge` over iterators, and time it against a seek-per-lookup
   version on a million fingerprints.
6. Read sections 4 to 6 of the IRLbot paper and write down what DRUM does differently from Mercator's disk eliminator.

---

## Sources

All read 2026-11-26 unless stated.

- Marc Najork and Allan Heydon, *High-Performance Web Crawling*, SRC Research Report 173, Compaq Systems Research
  Center, 26 September 2001 (PDF, read in full). Source for the architecture, frontier, eliminators, DNS findings and
  the 2000 crawl statistics.
- Sergey Brin and Lawrence Page, *The Anatomy of a Large-Scale Hypertextual Web Search Engine*, WWW 1998 (PDF; section
  4.3 on crawling read, the rest skimmed).
- Hsin-Tsang Lee, Derek Leonard, Xiaoming Wang, Dmitri Loguinov, *IRLbot: Scaling to 6 Billion Pages and Beyond*, WWW
  2008 (PDF; abstract and introduction read; the DRUM, STAR and BEAST sections and the experiments were not read in
  detail).
- M. Koster, G. Illyes, H. Zeller, L. Sassman, *Robots Exclusion Protocol*, RFC 9309, September 2022 (read in full).
- T. Berners-Lee, R. Fielding, L. Masinter, *Uniform Resource Identifier (URI): Generic Syntax*, RFC 3986, January 2005
  (sections 5.2.4 and 6.2.2 to 6.2.3 read; the rest not).

## Further reading (not consulted)

Heydon and Najork, *Mercator: A Scalable, Extensible Web Crawler* (World Wide Web, 1999), the shorter original paper;
Cho and Garcia-Molina on crawl ordering and freshness; Common Crawl documentation; the published crawler documentation
of Google and Bing. None were read for this revision.

*Last reviewed: 26 November 2026.*
