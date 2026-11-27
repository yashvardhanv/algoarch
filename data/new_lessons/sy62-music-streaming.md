# Lesson 62 — Case Study: Music Streaming (Spotify)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — music streaming is the "small files, huge repeat, instant start" case, and it is a good place to show that capacity estimates can be dominated by latency and caching rather than bandwidth.
>
> **Study time:** 80 minutes. **Do this after:** YouTube / Netflix Video Streaming; Caching Patterns and Consistent Hashing; Real-Time Collaborative Docs & Whiteboard; Distributed Object Storage (S3).
>
> **Level:** extended.

A track is a few megabytes, the same few tracks are played constantly, and the listener expects sound within a fraction of a second of pressing play, and again when the song ends. So the design problem is less "how do we move the bytes" than "what is already on the device, what is fetched before it is needed, and how fast can a cold start be". The only primary source on a real music service that was read is a 2010 paper by Spotify's engineers, so this lesson is built around it, says what it does and does not tell you, and then teaches the parts that hold for any service: prefetch rules, chunk scheduling, a seek index, and playlist ordering, all as small tested code (`test/lesson_code/sy62_check.py`). Capacity figures come from `capacity_check_f.py`. Video streaming, caching and object storage are not re-taught (see YouTube / Netflix Video Streaming, Caching Patterns and Consistent Hashing, Distributed Object Storage (S3)).

**What was and was not read.** Kreitz and Niemelä, *Spotify: Large Scale, Low Latency, P2P Music-on-Demand Streaming* (IEEE P2P 2010), and RFC 8216 (HTTP Live Streaming, read in part). The paper describes **2010**: a desktop client, a library of 8 million tracks, 7 million users in six European countries, a peer-to-peer overlay, and it says the smartphone clients did not take part in the peer-to-peer protocol. **Nothing was read about how Spotify delivers audio today**, so no sentence here says it still works this way; the modern-service section is the general approach, labelled so. Figures marked *assumed* are this lesson's own.

---

## 1. Mental Model

> **Music is small, repetitive and predictable. Serve most bytes from a cache that is already close to the listener, make the next track already there when this one ends, and spend your engineering on the first few hundred milliseconds, on seeking, and on rights. Bandwidth is the easy part.**

- **The popular set is small.** In the paper's week of measurements, 88% of plays were within the most popular 12% of the library, yet about 60% of the library was played at least once. Both halves matter: a cache for the head, and a store that can serve the tail.
- **Latency has a floor you cannot cache away.** The paper notes that even a fully cached track waited for a network reply (rights checking) before playing, so start latency almost always includes one round trip.
- **Predictability is a resource.** 61% of plays in the paper started because the previous track ended or the user pressed next, so a client that fetches ahead wins most of the time.
- **Playlists are ordered, shared, and edited concurrently.** Ordering is a data-structure choice (section 9) as much as a UI one.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "stream music with instant playback" | a start path that is already warm: connection kept open, next track prefetched, first seconds from the nearest copy (sections 6) |
| "millions of listeners, bandwidth bill" | cache the head of the catalogue near listeners; measure what share of bytes each layer serves (section 3) |
| "seek anywhere in a track" | an index from time to byte offset; constant-bitrate arithmetic is wrong for variable bitrate (section 8) |
| "offline listening" | download at the lowest priority, with a license that expires; check rights on reconnect (section 10) |
| "collaborative playlist, drag to reorder" | order keys that can be inserted between two neighbours without renumbering (section 9) |
| "licensing: some tracks are not available in some countries" | a rights check on the play path and on catalogue views, per user country |

---

## 3. Requirements and Capacity

**Functional.** Search and browse; play a track with seek, pause and next; playlists, library and sharing; offline sync; recommendations (out of scope here). **Out of scope:** the recommender, payments, ads.

**Non-functional.** Start of playback fast and consistent; a stutter rate near zero (the paper reports under 1% of playbacks stuttering); the catalogue and rights correct per country; the bulk of bytes not paid for at the origin.

**Capacity estimate.** *Paper* marks figures the 2010 paper prints and are used as inputs. *Assumed* marks this lesson's own. Results are reproduced by `capacity_check_f.py`.

| Input | Value |
|---|---|
| library | 8 million tracks *(paper, 2010)* |
| audio | Ogg Vorbis, quality 5 averaging roughly 160 kbps; quality 9 roughly 320 kbps for premium *(paper)* |
| where playback data came from | 8.8% servers, 35.8% peers, 55.4% local cache *(paper, one measurement period)* |
| concentration | 88% of plays in the top 12% of the library *(paper)* |
| client cache | at least 50 MB, at most 10 GB by default; 56% of clients had a maximum cache size of 5 GB or more, which fits about 1,000 tracks *(paper)* |
| average track | 4 minutes *(assumed)* |
| renditions stored per track | 96, 160 and 320 kbps *(assumed)* |
| concurrent listeners | 1,000,000, each at 160 kbps *(assumed)* |

| Result | Arithmetic | Value |
|---|---|---|
| one track at 160 kbps | 160,000 / 8 x 240 s | 4.8 MB |
| the 2010 library, one rendition | 8,000,000 x 4.8 MB | 38.4 TB |
| three renditions | 38.4 TB x (96 + 160 + 320) / 160 | 138.24 TB |
| the head: top 12% at 160 kbps | 960,000 x 4.8 MB | 4.608 TB |
| what a 5 GB cache holds | 5,000 MB / 4.8 MB | 1,041 tracks (the paper says about 1,000) |
| playback rate | 1,000,000 x 160 kbps | 160 Gbps |
| servers' share with the paper's mix | 160 x 8.8% | 14.08 Gbps |
| servers' share with no peer network | 160 x (8.8% + 35.8%) | 71.36 Gbps, 5.07 times as much |
| plays started per second | 1,000,000 / 240 | 4,167 plays per second |
| cost of switching off prefetch (paper) | median start 390 ms against 265 ms; stutter 1.8% against 1.0% | 47% slower median start; 80% more stutter |

Five conclusions. **The catalogue is small by modern standards:** 138.24 TB for three renditions of an 8 million track library is small next to modern disk sizes (the number of servers depends on replication and per-server capacity, which this lesson does not assume); the 4.6 TB head fits in memory and flash across a modest cache tier. **The bandwidth bill is a hit-ratio question,** not a catalogue question: the paper's mix made servers 8.8% of the data, and the same mix with no peer network would be 5.07 times as much (applying a share of counted data to a playback rate is a rough scaling, not something the paper computed; it also assumes the cache share is unchanged). **Start latency is the number to defend:** the paper's own experiment turned off prefetching for a week and saw the median start go from 265 ms to 390 ms. **Skips make the worst case:** 39% of playbacks in the paper were random access (the user picked a track), which cannot be prefetched. **Event volume is small:** about 4,167 plays per second at the assumed 1,000,000 listeners.

---

## 4. API and Data Model

```
GET  /tracks/{id}/play?quality=normal   ->  {manifest_url, key_id, expires_at}     # rights checked here, country from the session
GET  {manifest_url}                      ->  {segments: [{t_ms, offset, length, url}]}   # also the seek index (section 8)
PUT  /playlists/{id}/items               {track, after_key, before_key}  ->  {key}       # order keys (section 9)
POST /events                             {user, track, started_at, ms_played, idempotency_key}   # play counts and royalties
```

- `tracks(id, album, artist, duration_ms, available_countries, renditions[])`, `renditions(track, quality, object_key, bytes, seek_index_ref)`, `playlists(id, owner, items[(key, track, added_by)])`, `library(user, saved_tracks, downloaded[])`.
- **The play path is the only place that checks rights.** The catalogue views filter by country too, so users do not see what they cannot play, but only the play path decides (the paper notes a user's accessible tracks depend on the home country).
- **Events are idempotent.** A play can be reported twice (retry, offline replay); the idempotency key makes it one play (see Idempotency, Outbox & Sagas).

---

## 5. What the 2010 Paper Built

Read in full from the abstract to the measurements; these are its facts, not a claim about any later system.

- **A desktop client with a long-lived connection to a server.** Messages are prioritised on that one connection, with interactive browsing ahead of bulk traffic. The transport is TCP (the authors give simplicity, friendliness to other TCP traffic and firewall handling as reasons), and a single TCP connection per pair of hosts multiplexes the messages.
- **Three sources for a track:** the client's own cache, other clients (the peer-to-peer overlay), and Spotify's servers. A client uploads only tracks it holds completely, which keeps the protocol simple because tracks are small.
- **Locating peers:** a **tracker** in the back end that keeps the 20 most recent peers for each track and answers with up to 10 who are online, and a search among neighbours that reaches peers within distance two. Spotify chose not to use a distributed hash table, citing lookup time (tracks are short, so lookups are frequent), simplicity and overhead.
- **Chunks of 16 kB**, requested from several peers at once, in order, scheduled by estimated download time (section 7).
- **Latency first.** The design goal stated is that using peers must not worsen playback latency; the client uses the server for latency-critical parts and the overlay for the rest, and measured a median start of 265 ms, 515 ms at the 75th percentile and 1,047 ms at the 90th percentile.
- **Limits stated by the authors:** the protocol is unsuited to live broadcast, the measurements are one period in six European countries, and the real-time cost of rights checking is part of the start latency.
- **Two overlays.** Clients connect to one of two data centres, each with its own overlay, so the peer-to-peer network is split in two.

Why it is still worth teaching: the *ideas* (long-lived connection, prefetch rules, chunk scheduling by expected download time, a tracker that is allowed to be approximate) transfer to a CDN design, which is what the modern-service section (11) assumes. The *numbers* are 2010.

---

## 6. Starting Fast: Prefetch and Source Rules

From the paper: the client begins searching for peers and downloading the next track when **30 seconds or less** remain in the current one; when **10 seconds or less** remain it prefetches the beginning of the next track **from the server if needed**; for a random access (the user picks a track), it asks the server for about **15 seconds** of music at once while searching for peers; the server is throttled so the client is not more than about **15 seconds** ahead if peers exist; and below **3 seconds** buffered the client enters an "emergency mode" and pauses uploading to its peers. Measured: of listeners who reached within 10 or 30 seconds of the end, 94% and 92% continued to the next scheduled track.

```python
def prefetch_stage(remaining_s: float, next_buffered_s: float) -> str:
    """'none': too early. 'peers': 30 s or less left, look for the next track among peers/caches. 'server': 10 s or less
    left and fewer than 15 s of the next track in hand (the lesson's reading of the paper's 'if needed'), fetch its start from the server."""
    if remaining_s > 30:
        return "none"
    if remaining_s <= 10 and next_buffered_s < 15:
        return "server"
    return "peers"


def choose_source(buffered_s: float, have_peers: bool):
    """(source, pause_upload). Below 3 s: emergency, server, stop uploading. Below 8 s (assumed): server.
    Otherwise the cheaper source, peers, when there are any."""
    if buffered_s < 3:
        return "server", True
    if buffered_s < 8 or not have_peers:
        return "server", False
    return "peers", False


def server_may_fetch(ahead_s: float, have_peers: bool) -> bool:
    """With peers available, the server is used only to stay about 15 s ahead of the play point."""
    return (not have_peers) or ahead_s < 15
```

The 30, 10, 15 and 3 second thresholds are the paper's; the 8 seconds in `choose_source` is this lesson's assumption (the paper says only "low"), and the reading of "if needed" is marked. The check pins every boundary: 30.0001 s remaining is too early and 30 is not; 3 s buffered is not an emergency and 2.9 is; having 15 s of the next track means no server fetch. **What to say in an interview:** the rules are an explicit trade of cost for latency, stated by the authors (they say the design prioritises playback latency and stutter over server load), and each threshold is tunable by measuring the effect on median start and on skipped prefetches (about 8% of the prefetches by listeners who reached the last 30 seconds went to a track that was not played next).

---

## 7. Chunks, Peers and the Client Cache

**Scheduling a chunk.** From the paper: peers are sorted by *expected download time* (bytes of outstanding requests divided by average speed); the client greedily requests the most urgent chunk from the peer with the lowest estimate, then updates it; a client may have outstanding requests from a peer for at most what it believes the peer can deliver within **2 seconds**, except that **32 kB** is always allowed; and a block whose estimated download time exceeds the time it is needed is not requested (it goes to the server). Here the estimate includes the chunk itself, since the deadline concerns when the block arrives (the lesson's reading).

```python
CHUNK = 16 * 1024


def assign_chunks(needed, peers):
    """needed: [(chunk_id, seconds_until_needed)] most urgent first. peers: {name: {"speed": bytes/s, "out": outstanding bytes}}.
    Returns [(chunk_id, peer_name or "server")]. Does not modify `peers`."""
    out = {k: v["out"] for k, v in peers.items()}
    plan = []
    for cid, deadline in needed:
        best = None
        for name in sorted(peers):
            speed = peers[name]["speed"]
            if speed <= 0:
                continue
            est = (out[name] + CHUNK) / speed                       # seconds until this chunk would arrive
            if out[name] + CHUNK <= max(32 * 1024, 2 * speed) and est <= deadline and (best is None or est < best[0]):
                best = (est, name)
        if best:
            out[best[1]] += CHUNK
            plan.append((cid, best[1]))
        else:
            plan.append((cid, "server"))
    return plan
```

The check compares this with an independent per-step argmin on 500 random peer sets, and verifies on every one that the outstanding cap and the deadline hold for each assignment; hand cases show the 32 kB rule (a 10 kB/s peer takes two chunks, the third goes to the server), the boundary (a chunk due exactly when it would arrive is accepted) and that the busy fast peer yields to an idle slower one.

**The tracker.** Allowed to be approximate, and cheap: a bounded, most-recent-first list per track.

```python
class Tracker:
    """The 20 most recent peers per track (the paper's figure); a reply has at most 10 who are online, newest first (the order is the lesson's choice)."""
    KEEP, REPLY = 20, 10

    def __init__(self):
        self.by_track = {}

    def play(self, track, peer):
        lst = [p for p in self.by_track.get(track, []) if p != peer]
        self.by_track[track] = ([peer] + lst)[: self.KEEP]

    def peers(self, track):
        return list(self.by_track.get(track, []))

    def lookup(self, track, online):
        return [p for p in self.by_track.get(track, []) if p in online][: self.REPLY]
```

It is compared with a naive model on 200 random sequences. The paper's design point worth remembering: clients are added only when they play a track and do not report cache contents or removals, so the tracker is a hint, and the connecting peer simply asks and may be refused.

**The client cache.** The paper reports an LRU policy over large caches, and simulations showing the eviction policy had little effect because caches are large.

```python
from collections import OrderedDict


class LruCache:
    """Byte-bounded LRU. put() returns False (and changes nothing) for an item larger than the whole cache."""

    def __init__(self, capacity: int):
        self.capacity, self.used, self.items = capacity, 0, OrderedDict()

    def get(self, key) -> bool:
        if key in self.items:
            self.items.move_to_end(key)
            return True
        return False

    def has(self, key) -> bool:
        return key in self.items

    def keys(self):
        return list(self.items)

    def put(self, key, size: int) -> bool:
        if size > self.capacity:
            return False
        self.used -= self.items.pop(key, 0)
        self.items[key] = size
        self.used += size
        while self.used > self.capacity:
            _, s = self.items.popitem(last=False)
            self.used -= s
        return True
```

Compared with a reference on 300 random runs (a touched item survives; a re-put replaces rather than adds; nothing evicted for an oversized item).

---

## 8. Seeking in Variable-Bitrate Audio

Variable bitrate means bytes per second are not constant, so the byte for a given time is not `time x average rate`. The paper adds that Ogg Vorbis offers limited support for seeking while streaming, and Spotify added a custom header to its files for it. A time-to-offset index does the same job (a table of points, found by binary search):

```python
from bisect import bisect_right


class SeekIndex:
    """points: [(t_ms, byte_offset)] sorted by time, the first at (0, 0). offset_for(t) is the offset of the last point at or before t."""

    def __init__(self, points):
        self.t = [p[0] for p in points]
        self.b = [p[1] for p in points]

    def offset_for(self, t_ms: int) -> int:
        i = bisect_right(self.t, t_ms) - 1
        return self.b[i] if i >= 0 else 0
```

**The example** (illustrative): a 240-second track with a quiet 60-second intro at 100 kbps and 180 seconds at 200 kbps is 5,250,000 bytes. Seeking to 60 seconds with the constant-rate guess (60/240 of the file) asks for byte 1,312,500; the true byte is 750,000, so the guess is off by 562,500 bytes and lands at **82.5 seconds**, 22.5 seconds late. The check compares the index with a linear scan on 300 random indexes and pins this example. Index granularity is a trade: finer points cost bytes in the manifest, coarser points make the player discard more data before the target.

---

## 9. Ordering a Playlist

A playlist is an ordered list with concurrent inserts and reorders. Storing a position integer forces renumbering on every insert; a linked list needs a transaction per move. A common technique is a **fractional key**: a string that sorts between its neighbours, so an insert writes one row. The lesson's version uses base-62 digits in ASCII order, with no trailing zero digit so each position has one spelling.

```python
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"   # string order == numeric order


def midpoint(a: str, b):
    """A key strictly between a and b (b None means the top). Requires a < b and no trailing '0'."""
    if b is not None:
        n = 0
        while n < len(b) and (a[n] if n < len(a) else "0") == b[n]:
            n += 1
        if n > 0:
            return b[:n] + midpoint(a[n:], b[n:])
    da = DIGITS.index(a[0]) if a else 0
    db = DIGITS.index(b[0]) if b is not None else 62
    if db - da > 1:
        return DIGITS[(da + db) // 2]
    if b is not None and len(b) > 1:
        return b[0]
    return DIGITS[da] + midpoint(a[1:], None)


def between(a, b):
    """A key for an item inserted after `a` (None: at the start) and before `b` (None: at the end)."""
    a = a or ""
    if b is not None and a >= b:
        raise ValueError("a must sort before b")
    return midpoint(a, b)
```

The check builds 300 playlists of 150 random inserts and verifies that every key sorts strictly between its neighbours both as a string and as an exact fraction (`fractions.Fraction`), that no key ends in `0`, and that two equal or reversed neighbours are refused.

**The hole, measured.** Repeated inserts at the same spot make keys longer: **201 characters after 1,000 inserts at the front**, **167 at the end**, and **201 just after one fixed key** (the check computes all three). Real playlists have a few hundred items and most inserts are at the end, so growth is slow, but a bulk import that always inserts at one position grows a key by about one character for every five or six inserts. Fixes: re-spread the keys of a playlist when any key is long (a rare background rewrite), or generate keys with a random component. **Concurrent inserts into the same gap produce the same key**; break the tie with a total order such as (key, writer id), and accept that two people dropping a track into the same slot see them in a stable but arbitrary order. For richer merges (text, moves of a block), see Real-Time Collaborative Docs & Whiteboard; whether any music service uses this exact scheme was not read.

---

## 10. Rights, DRM and Offline

- **The play path asks for rights every time.** The paper observes that even cached content waited for a network reply (DRM), so the start latency almost always includes at least one round trip, unless the track was synchronised for offline playback. The general fix: request the license and the first audio bytes in parallel, and keep a short-lived license on the device.
- **Offline is a download with an expiry.** The paper lists "offline synchronization" as the lowest of three request priorities (current track, prefetch, offline sync): offline work must never compete with the track being played. The general design adds a licence lifetime and a periodic online check so removed tracks disappear.
- **Per-country catalogues** (the paper: availability depends on home country) are a filter on search results and on the play check.
- **Counting plays for royalties** is a separate, auditable pipeline: events carry an idempotency key, and the definition of "a play" is a product and contract decision; no source on any service's rule was read.

---

## 11. A General Design Today (not from a source)

This section is the general approach for a service today, not a description of any company.

1. **Catalogue and metadata** in a database with search (see Distributed Search Engine (Elasticsearch at Scale)); playlists and the library in a store keyed by user.
2. **Playback service:** checks rights and plan, returns a short-lived signed manifest (the list of segments and offsets of section 8) and a license reference.
3. **Audio delivery from a CDN** with HTTP range or segment requests: the standard route for adaptive streaming (RFC 8216 describes HTTP Live Streaming as playlists of media segments fetched over HTTP; read in part). A cache tier in front of the object store serves the head of the catalogue; the tail goes to the origin. Bytes played from the device's own cache never reach the CDN, so start from the network share: with the paper's 55.4% local-cache share kept as an assumption, the CDN carries 160 x 44.6% = 71.36 Gbps, and origin load is that times (1 - edge hit ratio): at an assumed 90% hit ratio 7.14 Gbps at the origin, at 99% 0.71 Gbps. (Charging the CDN for the full 160 Gbps would overstate both by 2.24 times.)
4. **Client behaviour from sections 6 to 8:** keep a connection warm, prefetch the next track, cache, seek by index.
5. **Events** into a log (see Kafka I: The Log & Producers), counted idempotently.

What a CDN does not replace: the first-byte latency of a track nobody has played recently (a cold miss), and the rights round trip.

---

## 12. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| cold miss on an old track | a slow start | origin close to the cache; prefetch on browse hints; accept it |
| prefetch wasted | bandwidth for tracks not played | a later threshold; the paper's 30 and 10 second rules cost about 8% unused starts |
| rights service slow or down | every play waits | cache licences on the device; fail open for already-downloaded tracks |
| bad seek index | a seek lands seconds off or in the middle of a frame | index at frame boundaries; verify indexes at ingest |
| peer or cache gives bad data | a corrupt chunk | verify by content hash; fall back to the server |
| tracker stale | requests to peers that no longer have the track | it is only a hint: ask, time out, use the server |
| playlist keys grow | long keys, slow rows | rebalance when a key passes a length (section 9) |
| duplicate play events | double counted plays | idempotency key per event |
| offline licence expires | downloaded tracks stop playing | periodic online check; clear message |

---

## 13. What Real Systems Did

- **Spotify, 2010** (Kreitz and Niemelä, read 2026-11-27): the design in section 5, a mix of server, peers and local cache, with the measured shares in section 3. The paper was written by two Spotify engineers, who describe their own system.
- **Spotify later:** not read. Do not assume the peer-to-peer overlay exists today.
- **HTTP Live Streaming** (RFC 8216, read in part): the segment-and-playlist model that a modern general design uses; the RFC does not say which music services use it.
- **Other services:** no source read.

---

## 14. Pitfalls Checklist

1. **Sizing on bandwidth alone.** The catalogue is small and the head cacheable; latency and hit ratio decide the design.
2. **`time x average rate` for seeking.** Wrong for variable bitrate; use an index.
3. **No prefetch rule.** Median start rises by about half in the paper's own experiment.
4. **Prefetch with no cost control.** Late thresholds, and the lowest priority for offline sync.
5. **A position integer per playlist item.** Every insert renumbers the rest.
6. **Comparing keys that are not in the same sort order as the keys' meaning.** Digits must be in ASCII order or string comparison misorders them.
7. **Trusting the tracker.** It is a hint; verify and fall back.
8. **Checking rights only in the catalogue.** The play path decides.
9. **Counting plays without an idempotency key.** Retries and offline replay double count.
10. **Presenting a 2010 paper as how a service works now.** Say what year and what was measured.

---

## Drills

1. A user presses play on a track that is not cached. List what the client does in the first 300 ms, and say why the paper's median start is lower than the first-byte latency of the server alone would suggest.
2. When does the 2010 client look for peers for the next track, and when does it fetch from the server? Give the thresholds, and say which one this lesson assumed.
3. A client has outstanding requests of 24 kB to a peer measured at 10 kB/s. May it request another 16 kB chunk? Why?
4. Why is seeking by `time x average bitrate` wrong for variable bitrate, and what lands where in the lesson's example?
5. Insert a track between playlist keys `1` and `2`, then between `1V` and `2`, then between `z` and the end. What property must each answer have?
6. Two people drop a track into the same gap of a shared playlist at the same moment. What happens with fractional keys, and what do you do about it?
7. Compute the head of a catalogue of 8 million tracks (12% at 4.8 MB) and the origin load for 1,000,000 listeners at 160 kbps, given that 55.4% of played data comes from the device cache and the CDN has a 95% edge hit ratio.
8. Why is the tracker allowed to be approximate, and what does the client do when it is wrong?

---

## Homework

1. Run `sy62_check.py` on this file. Change `assign_chunks` to compare `est < deadline` and find the failing assertion; then drop the 32 kB exception and find which one fails.
2. Build a seek index for a real MP3 or Ogg file by scanning its frames, and measure how far a constant-rate guess lands from the target at ten positions.
3. Add a `rebalance(keys)` that respaces a playlist's keys, and a check that order is preserved and no key is longer than three characters for a 200-item playlist.
4. Replace the tie-break in section 9 with a random digit appended to the key and measure how often two concurrent inserts still collide.
5. Read RFC 8216 and write the playlist for a two-segment track with the seek points of section 8.

---

## Sources

All read 2026-11-27. The code, the thresholds marked *assumed*, the modern-service section and the figures marked *assumed* are this lesson's own.

- Gunnar Kreitz and Fredrik Niemelä, *Spotify: Large Scale, Low Latency, P2P Music-on-Demand Streaming*, IEEE Tenth International Conference on Peer-to-Peer Computing, 2010. Read in full (the PDF text; the figures were not examined). Obtained from the Internet Archive's copy of the authors' former page, since the original address no longer served the paper.
- RFC 8216, *HTTP Live Streaming* (August 2017): the introduction and playlist and segment overview, read in part.

## Further reading (not consulted)

Anything on how Spotify or any other service delivers audio today; Spotify engineering posts of any year; Apple's and Google's music-service documentation; DASH (ISO/IEC 23009-1); the Ogg and Vorbis specifications; any engineering write-up of fractional indexing at a named company; royalty and rights-management systems. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
