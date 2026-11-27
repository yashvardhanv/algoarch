# Lesson 65 — Case Study: Live Streaming with Live Comments (Twitch)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — a live stream with a chat is two different fan-out problems glued to one page: one that a cache solves and one that nothing but thinning solves.
>
> **Study time:** 85 minutes. **Do this after:** Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates; Scaling Patterns I: Reads, Writes and Contention; Overload, Load Shedding and Cascading Failures; Real-Time Gaming Leaderboard at 10M QPS.
>
> **Level:** extended.

A million people watching one broadcaster is a read problem: the same few bytes, requested by everyone, a moment after they exist. A million people reading one chat is a different animal: every message sent by one person must reach all of them, and the cost is messages times viewers. This lesson builds both halves as small tested models in `test/lesson_code/sy65_check.py`: the sliding-window playlist and the latency it implies, request coalescing so a new segment does not stampede the origin, and a live-comments hub with sequence numbers, resume and a thinning rule. Capacity numbers come from `test/lesson_code/capacity_check_g.py`. The general case of server push to many clients is in Scaling Patterns II and is not repeated.

---

## 1. Mental Model

> **Video is cacheable: one origin object, many identical reads, solved by a hierarchy of caches that must not all miss at once. Chat is not cacheable: every message is new and every viewer needs it, so the cost is the product of the two and the only defence is to cut the product.**

- **Video latency is a design parameter, not a bug.** The playlist rules of HLS put a viewer several segments behind the live edge (section 5); shorter segments shrink that and multiply requests.
- **The herd is at the edge of a new object.** Everyone wants segment N the instant it exists; the first request must go upstream and the rest must wait for it, not follow it (section 6).
- **Chat amplification is viewers times rate.** 500 messages a second into a million-viewer room is 500 million deliveries a second if you forward everything (section 3); no server fleet is sized for that, so the room is thinned and batched (section 7).
- **Order and resume come from one counter per room,** not from clocks (the same idea as a per-mailbox UID in Case Study: Email Service (Gmail)).
- **Decouple the two paths.** A chat outage must not stall video and a video stall must not drop the chat connection.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "design Twitch / live streaming" | ingest, transcode into several renditions, segment, CDN, player; chat as a separate service; say which half you deep dive |
| "viewers are 20 seconds behind" | segment length and the playlist join rule (section 5); low-latency modes exist and were not read |
| "a new segment makes the origin fall over" | request coalescing at every cache tier, plus an origin shield (section 6) |
| "millions in one chat room" | thin the room (cap messages per second delivered), batch per connection, fan out in a tree (section 7) |
| "chat disconnects and reconnects" | per-room sequence numbers and a bounded resume buffer; a "gap" answer when the buffer was overrun |
| "moderators, bans, slow mode" | a rules service in front of the room's publish; it adds latency to every message, which section 9 shows is a real outage cause |

---

## 3. Requirements and Capacity

**Functional.** A broadcaster pushes live video; viewers watch it in several qualities; viewers read and post chat; moderators can remove messages and ban users. **Out of scope:** recording and clips, payments and subscriptions, recommendations, the player UI.

**Non-functional.** Viewers start watching within seconds and stay within a bounded delay of live; the origin survives the start of each segment; chat messages arrive in order and in time; chat never takes video down.

**Capacity estimate.** Every input below is *assumed* by this lesson, not any company's figure (one assumption borrows a figure the Facebook post gave for a different product and is labelled); every result is reproduced by `capacity_check_g.py`.

| Input | Value |
|---|---|
| concurrent viewers of one very large stream | 1 million *(assumed)* |
| average delivered bitrate | 3 Mbps *(assumed)* |
| segment length | 2 s *(assumed)* |
| renditions (qualities) | 5, summing to 15 Mbps *(assumed)* |
| edge caches | 100 *(assumed)* |
| edge hit ratio with no coalescing | 98% *(assumed; the Facebook post reports more than 98 percent of segments served from edge caches for its own product, section 9)* |
| chat messages into the room | 500 per second *(assumed)* |
| delivered message size | 150 bytes *(assumed)* |
| chat connections per edge node | 100,000 *(assumed)* |
| messages a viewer is shown per second (thinning cap) | 20 *(assumed; a product decision)* |

| Result | Arithmetic | Value |
|---|---|---|
| video egress for this one stream | 1,000,000 x 3 Mbps | 3 Tbps |
| segment requests | 1,000,000 / 2 s | 500,000 per second |
| playlist reloads | about one per target duration per viewer (more often when a reload finds no change) | about 500,000 per second, more in practice |
| a segment | 3 Mbps x 2 s / 8 | 0.75 MB |
| stored per hour for the stream | 15 Mbps x 3,600 s / 8 | 6.75 GB per hour |
| origin requests if 2% of requests miss | 500,000 x 2% | 10,000 per second |
| origin requests with coalescing | 100 edges x 5 renditions / 2 s | 250 per second |
| chat forwarded unthinned | 500 x 1,000,000 | 500 million deliveries per second, 600 Gbps |
| chat with a cap of 20 per second | 20 x 1,000,000 | 20 million message deliveries per second, 24 Gbps, 0.8% of the video |
| chat frames if batched once a second per connection | 1,000,000 frames of 20 x 150 B | 1 million frames per second, 3 KB each |
| edge nodes for the connections | 1,000,000 / 100,000 | 10 nodes |

Four conclusions. **Video bandwidth is a CDN problem and the origin is a coalescing problem:** 3 Tbps leaves the edges, 250 requests a second reach the origin when coalescing works and 10,000 when only a 98% hit ratio protects it; the gap is the whole case for section 6. **Unthinned chat does not fit:** 500 million deliveries a second is 600 Gbps of text, 20% of the video egress, and no per-message write path is sized for it; capped to 20 per second and batched, it is 24 Gbps and a million frames a second. **Ten edge nodes is a plan, not a measurement:** the 100,000 connections per node is an assumption, and a lower real figure multiplies the node count and the pubsub hops. **A message costs one hop per edge, not per viewer:** with the thinning rule, hops per message is the number of edge nodes (10), and deliveries per message is the number of viewers; the second term is what the cap controls.

---

## 4. API and Data Model

```
ingest:    broadcaster --RTMP--> ingest PoP --> transcode (5 renditions) --> segmenter --> origin
playback:  GET master.m3u8 -> GET media.m3u8 (live window) -> GET segment_N.ts      (HTTP, through the CDN)
chat:      WebSocket to an edge node: JOIN room, SEND text, resume(last_seq)  -> frames [{seq, user, text, prio}]
rules:     check(room, user, text) -> ok | slow_mode | banned | timeout           (before publish)
room       {id, seq, ring buffer of the last N messages}      edge {id, room -> connections}
```

Chat messages for a room are ordered by one **sequence number** the room assigns; a small **ring buffer** of the most recent messages serves resumes. A message is not stored per viewer. Durable chat history (search, moderation review) is a separate append-only store off the hot path; the hot path is memory.

---

## 5. Deep Dive 1: The Live Playlist and Where the Delay Comes From

HLS (RFC 8216) delivers video as a playlist of short segments the client fetches over HTTP. For a live stream the playlist is a **sliding window**: the server MAY remove old segments; if it does it must carry a media sequence number that goes up by one for every removed segment and never decreases; the playlist must not be shorter than three target durations; a new version must appear between half a target duration and one and a half after the previous one; a client must wait at least one target duration between reloads that found a change, and half of one after a reload that did not; and when starting, a client "SHOULD NOT choose a segment that starts less than three target durations from the end". A removed segment must stay available for at least the playlist's duration at the time of removal, so playback in progress is not cut off. (RFC 8216, sections 6.2.2, 6.2.1, 6.3.3 and 6.3.4.)

```python
import math

class LiveOrigin:
    """Segments of `target` seconds numbered 0, 1, 2 ...; the playlist shows the newest `window`; removed ones stay fetchable
    for the playlist duration (the RFC minimum)."""
    def __init__(self, target, window):
        assert window >= 3, 'a live playlist may not be shorter than three target durations'
        self.target, self.window, self.newest = target, window, -1
    def publish(self):
        self.newest += 1
    def media_sequence(self):
        return max(0, self.newest - self.window + 1)
    def playlist(self):
        return list(range(self.media_sequence(), self.newest + 1))
    def fetchable(self, seq):
        return 0 <= seq <= self.newest and seq > self.newest - 2 * self.window

def join_seq(origin):
    """Where a player starts: the third segment from the end, so the first frame is three target durations behind live."""
    pl = origin.playlist()
    assert len(pl) >= 3
    return pl[-3]

def join_latency(T, d, t0):
    """Segment n is available at (n + 1) * T + d (d: encode, package, upload). A player joining at t0 starts three from the
    end; the age of its first frame is t0 minus that segment's start."""
    newest = math.floor((t0 - d) / T) - 1
    assert newest >= 2
    return t0 - (newest - 2) * T

def pause_budget(W, retained):
    """Segments that can be published while a player (joined with join_seq) is paused before the segment it needs next is gone:
    from the playlist alone W - 3; if removed segments stay for a playlist duration, 2W - 3."""
    return 2 * W - 3 if retained else W - 3
```

**Latency, derived.** Segment n is complete at the end of its own time slot and available a little later (encode and packaging delay d, assumed). A player that joins right after a publish starts three segments back: its first frame is **3T + d** old; one that joins just before the next publish starts at the same third-from-end segment, one segment later: just under **4T + d**. The check sweeps join instants across ten segment lengths for four (T, d) pairs and confirms both ends. With T = 2 s and d = 1.5 s (assumed) that is **7.5 to 9.5 seconds**, before the player's own buffer and the network; with T = 6 s (also assumed; RFC 8216 itself says "a typical target duration is 10 seconds") it is **19.5 to 25.5 seconds**. Shorter segments cut the delay but double the request rate for each halving (section 3's 500,000 per second at 2 s would be 1,000,000 at 1 s), and add overhead to every segment. Newer low-latency variants of HLS and other protocols exist; none were read for this lesson, so none is described.

**How long may a player stall?** A player whose connection stops, or whose tab sleeps, must come back before the segment it needs next is gone. From the playlist alone, with a window of W segments: `W - 3` segments of media published before it is gone; if the origin keeps removed segments for the playlist duration, as the RFC requires at minimum, `2W - 3`. The check brute-forces both for windows 3 to 11 by publishing k more segments and asking. At W = 6 that is **3 segments** or **9 segments**. A player beyond it must re-join at the live edge (a visible jump). The window is therefore a trade: a bigger window gives more slack and more bytes in the playlist; the RFC floor is three target durations.

**Where each part runs.** The broadcaster pushes RTMP to an ingest point of presence; transcoding turns one stream into several qualities (an HLS rendition ladder); a segmenter cuts and publishes. Twitch's 2015 engineering overview describes this as ingest of RTMP, transcoding into multiple HLS streams, delivery to points of presence, and archiving for video on demand; its 2022 post describes about a hundred PoPs that ingest and forward to origin data centres (section 9). Everything the viewer fetches is a plain HTTP object, which is why the CDN can serve it.

---

## 6. Deep Dive 2: The Herd at a New Segment

A new segment is requested by everyone at once: before it exists in any cache every request is a miss. If each miss goes upstream, the origin receives one request per viewer, which is the thundering herd. The Facebook Live post (December 2015) describes the fix: edge caches in front of origin caches in front of the live server, and request coalescing: the edge returns a miss for the first request for a segment and queues the rest; when the segment arrives it is cached and the queued requests are answered from the edge; the origin applies the same logic across edge caches, so one object requested from two cities reaches the server once. The same post gives 3-second HLS segments and more than 98 percent served from an edge cache near the user, with about 1.8 percent still getting past the edge, which at a million viewers is a large absolute number. That product is not Twitch; the idea is the general one.

```python
class CacheNode:
    """One cache tier. `lat` is the one-way delay to the tier above (or to the origin when `up` is None). Requests must be
    presented in time order. A request that finds the object in flight waits for it if `coalesce`, else goes up itself."""
    def __init__(self, lat, up=None, coalesce=True):
        self.lat, self.up, self.coalesce = lat, up, coalesce
        self.reply = {}          # segment -> time the reply reaches this node
        self.fetches = 0         # requests this node sent upward
    def get(self, seg, t):
        r = self.reply.get(seg)
        if r is not None and (r <= t or self.coalesce):
            return max(t, r)                              # cached, or in flight and we queue behind it
        self.fetches += 1
        arrive = t + self.lat
        answered = arrive if self.up is None else self.up.get(seg, arrive)
        done = answered + self.lat
        self.reply[seg] = done if r is None else min(r, done)
        return done
```

What the check shows: on one node with 1 to 60 requests inside a one-second window and upstream delays of 10, 50 and 200 milliseconds (300 runs), coalescing sends exactly **one** request upstream, every waiter is answered at the first reply or at once if it arrives later, and without coalescing the number of upstream requests equals the number of requests that arrive before the first reply, computed independently. For two tiers, 50 edges with 200 requests each and a shield above them: with coalescing at both tiers the origin sees one request and each edge one; without a shield each edge asks the origin itself, 50; with no coalescing anywhere the numbers become the figures in the next sentence. The measured herd (illustrative, seeded): with 50 edges of 200 requests each arriving across half a second and no coalescing, **1,624 requests leave the shield and 2,488 leave the edges** (of 10,000 viewer requests), against 1 and 50 with it.

**Limits the model leaves out.** A failed upstream fetch: all queued waiters fail together and the retry must also be coalesced, one retry per failed round and not one per waiter, or a failure becomes a herd at the moment the origin is weakest. Negative caching of a 404 for a segment not yet published (a request for a segment that does not exist yet is a request for the future): hold it briefly. Per-viewer playlists with tokens defeat caching, so tokens belong in a layer that does not change the cache key. The model's two delays are constants; real networks vary.

---

## 7. Deep Dive 3: Live Comments

The path of a message: viewer's connection to an edge node, a rules check (is this user banned, is slow mode on), publish to the room, fan-out to every edge node with viewers in the room, and from each node to its connections. The Twitch 2015 overview describes chat as a Go system with an **Edge** tier that speaks IRC over raw TCP and WebSockets, a **Pubsub** tier that distributes messages among edge nodes ("a hierarchical message distribution system which executes massive fanout"), **Clue** which runs user actions through the business logic (bans, subscriber checks) and **Room**, which manages viewer lists across Edges. The post does not give their protocols or capacity; the model below is the lesson's own.

```python
class Room:
    """One counter orders the room; a bounded ring of recent messages serves resumes."""
    def __init__(self, ring=1000):
        self.ring, self.seq, self.buf = ring, 0, []
    def publish(self, user, text, prio=0):
        self.seq += 1
        self.buf.append({'seq': self.seq, 'user': user, 'text': text, 'prio': prio})
        self.buf = self.buf[-self.ring:]
        return self.seq
    def since(self, last):
        """Messages after `last`: ('ok', [...]) or ('gap', oldest seq still held) if some were overwritten."""
        if last >= self.seq:
            return 'ok', []
        oldest = self.buf[0]['seq']
        if last + 1 < oldest:
            return 'gap', oldest
        return 'ok', [m for m in self.buf if m['seq'] > last]

class Hub:
    """Rooms, and which connections of which edge nodes watch them. A publish costs one hop per edge with viewers."""
    def __init__(self, ring=1000):
        self.ring, self.rooms, self.subs = ring, {}, {}
    def join(self, room, edge, conn):
        self.subs.setdefault(room, {}).setdefault(edge, set()).add(conn)
    def leave(self, room, edge, conn):
        edges = self.subs.get(room, {})
        edges.get(edge, set()).discard(conn)
        if edge in edges and not edges[edge]:
            del edges[edge]                              # an edge with no viewers stops receiving the room
    def publish(self, room, user, text, prio=0):
        seq = self.rooms.setdefault(room, Room(self.ring)).publish(user, text, prio)
        edges = self.subs.get(room, {})
        return {'seq': seq, 'hops': len(edges), 'deliveries': sum(len(c) for c in edges.values())}

class Client:
    """A viewer's connection state: accepts the next sequence number, detects a hole, resumes, records unrecoverable gaps."""
    def __init__(self, name):
        self.name, self.last, self.start, self.received, self.gaps = name, None, None, [], []
    def connect(self, room):
        if self.last is None:
            self.last = self.start = room.seq            # first join: from now on
        else:
            self.sync(room)                              # reconnect: ask for what was missed
    def on_live(self, room, msg):
        if self.last is None or msg['seq'] <= self.last:
            return                                       # duplicate or stale
        if msg['seq'] == self.last + 1:
            self.received.append(msg['seq'])
            self.last = msg['seq']
        else:
            self.sync(room)                              # a hole: do not skip over it, resume
    def sync(self, room):
        kind, got = room.since(self.last)
        if kind == 'gap':
            self.gaps.append((self.last + 1, got - 1))   # lost for good: say so, do not pretend
            self.last = got - 1
            kind, got = room.since(self.last)
        for m in got:
            self.received.append(m['seq'])
            self.last = m['seq']

def select(batch, cap, rng):
    """Thinning: from one tick's messages deliver at most `cap`. Priority messages (moderators, subscribers, the broadcaster)
    come first, the newest of them if they alone exceed the cap; the remaining slots are a uniform sample of the rest."""
    if cap <= 0:
        return []
    prio = [m for m in batch if m['prio']]
    rest = [m for m in batch if not m['prio']]
    if len(prio) >= cap:
        chosen = sorted(prio, key=lambda m: m['seq'])[-cap:]
    else:
        slots = cap - len(prio)
        chosen = prio + (rng.sample(rest, slots) if len(rest) > slots else rest)
    return sorted(chosen, key=lambda m: m['seq'])
```

**What is asserted.** The room: sequence numbers 1, 2, 3 with no skips; `since` against a brute-force reference over 500 random ring sizes and message counts, including the exact boundary (a ring of 5 holding 4 to 8 answers a request after 3 completely, and after 2 with a gap and the oldest number); asking past the newest gives an empty answer. The hub: 3 edges and 4 connections is 3 hops and 4 deliveries; an edge with no viewers left stops costing a hop; a million-viewer-style closed form (1,000 viewers on 10 edges, 7 messages: 70 hops, 7,000 deliveries). The clients: 300 seeded random runs with a ring of 3 and 300 with a ring of 10,000, four clients joining, leaving, losing live deliveries (20% of them) and reconnecting; every client's received list is strictly increasing with no duplicates, the sum of received and recorded-lost messages equals the span it joined for, no recorded-lost range overlaps a received message, and every online client ends at the room's last sequence number. With the small ring there are gaps (it must be honest about them); with the big ring there are none. Thinning: output size is the smaller of the cap and the batch, in order, a subset; priority messages always survive; priority alone over the cap keeps the newest; and in 40,000 draws of 8 ordinary messages with 3 slots each is kept with probability 3/8 within one percentage point, newest and oldest alike.

**Why thin the room, and where.** Sampling once per room and tick, then sending the **same** selection to every viewer, gives every viewer the same transcript and costs one random draw per tick, not one per viewer per message. Per-viewer sampling hides different messages from different people and costs more. The cap is a product choice (what can anyone read at that rate?); the price is that a hot chat is a sample, a fact worth showing in the UI. Messages from the broadcaster and moderators are priority so a sample never hides them. Fan-out then goes through a tree: the room publishes once per edge node, each node writes one batched frame per connection per tick (section 3: 1 million frames of 3 KB per second across 10 nodes), which is far cheaper than a write per message per viewer.

**Chat against video time.** The video is 7.5 to 9.5 seconds behind live (section 5); chat arrives in a fraction of a second, so a viewer reads the reaction before the event. A client can hold chat back by its own measured video delay. This is the lesson's suggestion, not a described design, and it needs a reference clock for video position that the playlist's program date-time tags may provide; not read.

---

## 8. Failure Modes

| Failure | What happens | Defence |
|---|---|---|
| segment published, every viewer asks at once | origin gets one request per viewer | coalescing at every tier; origin shield (1 versus the herd of section 6) |
| a failed origin fetch | queued waiters all retry | one retry per failed round, not per waiter |
| player stalls beyond the window | the segment it needs is gone | re-join at live; window and retention sized to the tolerated stall (3 or 9 segments at W = 6) |
| edge node dies | its connections drop | clients reconnect with their last sequence number; the ring buffer fills the hole |
| reconnect after a long outage | ring overrun | `since` answers gap; show a visible break rather than invent history |
| viral stream: messages x viewers | outbound saturates | thinning, batching per connection, tree fan-out |
| rules service slow | every publish waits | timeouts that also cancel the work (a Twitch outage, section 9); rules checks off the critical path where policy allows |
| chat outage | chat stops | video path independent; the player keeps playing |
| one hot room on one shard | a single room's ring and counter are a single writer | a room's counter is sequential by design; scale by giving huge rooms a dedicated shard, not by splitting the counter |

---

## 9. What Real Systems Did

Only what was read.

- **Twitch engineering overview (blog.twitch.tv, 18 December 2015):** chat is a Go system with Edge (IRC over TCP and WebSockets), Pubsub, Clue and Room as described above; video as RTMP ingest, transcode to multiple HLS streams, distribution to PoPs, and archiving. The post gives two chat figures that conflict ("over 10 billion messages a day" in one place and "hundreds of billions" in another), so none is repeated here.
- **Twitch, "Regarding recent chat issues" (28 June 2013):** edge servers called a stateless "clue" backend over HTTP and JSON; after a change to how web chat authenticated, extra work left the clue CPUs busy with SSL negotiation; the edge's 20-second timeout cancelled the client's request but the clue server was not told, so it kept working through abandoned requests while the edge kept adding new ones; the fix included dropping SSL for requests inside the data centre. The lesson for Overload, Load Shedding and Cascading Failures: a timeout that does not cancel the work is a retry storm.
- **Twitch, "Ingesting Live Video Streams at Global Scale" (26 April 2022):** nearly a hundred PoPs; a proxy in each PoP terminates incoming streams (RTMP and WebRTC are named as examples) and carries them on a canonical internal protocol over a private backbone to origin data centres; a routing service decides where streams go, first as an offline optimisation pushed as static configuration, later using live capacity and network status with a randomised greedy algorithm.
- **Facebook, "Under the hood: Broadcasting live video to millions" (3 December 2015):** 3-second HLS segments, edge and origin caches, the coalescing described in section 6, more than 98 percent from edge caches; and a separate path using RTMP for lower latency (about two to three seconds) for smaller interactive broadcasts. The post says nothing about comments.
- **RFC 8216 (HLS):** the playlist rules of section 5.

**Not read, so nothing is claimed:** Twitch's current chat architecture, how it rate-limits or samples chat, its video transcoding and low-latency delivery, LinkedIn's "Streaming a Million Likes/Second" (the page could not be fetched), Apple's low-latency HLS, WebRTC, any YouTube or Facebook comment-system post. The window arithmetic, the `CacheNode`, the hub, the resume buffer and the thinning rule are this lesson's.

---

## 10. Pitfalls

1. Treating chat as video: it cannot be cached, and fan-out grows with viewers times rate.
2. Forwarding every message to every viewer in a million-viewer room.
3. One write per message per connection instead of one batch per tick.
4. A playlist shorter than three target durations, or a player that starts at the very end.
5. Letting every cache miss go upstream at the start of a segment (no coalescing, no shield).
6. Retrying a failed upstream fetch once per waiter.
7. No sequence numbers: clients cannot tell a hole from silence, or resume.
8. A resume buffer with no "gap" answer, so a long outage silently skips messages.
9. Timeouts that do not cancel the work behind them (the 2013 Twitch chat incident).
10. Per-viewer tokens in the segment cache key.
11. Claiming how a named company samples or caches chat with no source.
12. Ignoring that chat runs ahead of video.

---

## Drills

1. With 2-second segments and a 1.5-second packaging delay, what is the range of the age of a viewer's first frame, and which rule from RFC 8216 gives the "3"?
2. A player is paused while 5 more segments are published, window 6. Does the playlist alone allow it to resume? Does the RFC's retention minimum?
3. 1,000,000 viewers, 2-second segments: how many segment requests per second leave the edges, and how many reach the origin with 100 edges and 5 renditions if coalescing works?
4. The first request for a segment goes upstream; 199 arrive before the reply. What happens to them with and without coalescing, and what does the origin see across 50 edges with and without a shield?
5. 500 messages a second into a room of a million, forwarded to everyone: how many deliveries per second, and what do you change?
6. A client has `last = 40`; the ring holds 45 to 90. What does `since(40)` return and what must the client do?
7. Why is a message sample drawn once per room and tick rather than once per viewer? Give one cost of each.
8. Chat shows a goal 8 seconds before the video does. Why, and name one fix and its cost.

---

## Homework

1. Run `test/lesson_code/sy65_check.py`; change the retention rule in `fetchable` from 2W to W and say which assertion fails and what the new pause budget is.
2. Extend `CacheNode` with a retry on failure: the first fetch fails, one waiter retries for all. Write the test that fails if each waiter retries.
3. Add per-user slow mode to `Hub.publish` (one message per N seconds per user) and show how it changes the number of messages entering the room in a simulated burst.
4. Implement per-viewer thinning and compare the deliveries and the random draws per second with room-level thinning at 1,000 viewers.
5. Read RFC 8216 section 6.2.2 and write the rule a segmenter must follow when it removes a segment, in four sentences.
6. Practice: sketch how a stream with 100 viewers differs from one with a million, and at what scale each simplification of this lesson (no tree, no thinning, no shield) becomes necessary.

---

## Sources

All accessed 27 November 2026. Web pages other than the RFC were read through a summarising fetch tool, so wording is as reported by it and each page was read in part (the tool returns a summary, not the page).

- RFC 8216 (HTTP Live Streaming, R. Pantos and W. May, August 2017): fetched as text and searched; sections 6.2.1, 6.2.2, 6.3.3 and 6.3.4 read in context; the rest not read.
- Twitch Engineering, "Twitch Engineering: An Introduction and Overview" (18 December 2015).
- Twitch Engineering, "Regarding recent chat issues" (28 June 2013).
- Twitch Engineering, "Ingesting Live Video Streams at Global Scale" (26 April 2022).
- Facebook (Meta) Engineering, "Under the hood: Broadcasting live video to millions" (3 December 2015).

**Not consulted:** Twitch's current chat and video low-latency material; LinkedIn's likes-streaming post (fetch failed); Apple's low-latency HLS; WebRTC specifications; any paper on live comment systems. The capacity inputs are this lesson's assumptions; the 98% hit ratio is borrowed from the Facebook post and used as an assumption. Simulation figures are illustrative (seeded Python runs on 3.13). The models and the thinning rule are this lesson's, not a company's.

*Last reviewed: 27 November 2026.*
