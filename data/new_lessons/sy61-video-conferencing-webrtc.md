# Lesson 61 — Case Study: Video Conferencing (Zoom / Meet, WebRTC)

> **Priority:** ★★★☆☆ (proposed; the curriculum data holds the final rating) — a call is the one design question where "send it through a server" is wrong at one size and right at the next, and the interesting answers are about packets, not storage.
>
> **Study time:** 85 minutes. **Do this after:** WhatsApp / Real-Time Chat; Networking, TLS & Load Balancing; Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates; Overload, Load Shedding and Cascading Failures.
>
> **Level:** extended.

A video call is many small flows, each useful for a few hundred milliseconds and worthless after. So the questions are where packets are copied, who decides the quality each viewer gets, and what happens to a stream when the sender changes. This lesson builds the pieces interviews probe as small tested code (`test/lesson_code/sy61_check.py`): the connectivity ranking of ICE, an SFU's per-receiver sequence numbers, the NACK message, and the choice of layers for one receiver. Capacity numbers come from `capacity_check_f.py`. Chat signalling and presence are not re-taught (see WhatsApp / Real-Time Chat), nor TLS and load balancing (see Networking, TLS & Load Balancing).

**What was and was not read.** The protocol facts come from the RFCs in Sources. For a real deployment, the only engineering source read is Discord's 2018 post on its voice servers (voice and video through a homegrown SFU). **No engineering post or paper from Zoom or Google Meet was read**, so nothing below says how they are built; the design is the general approach and the figures marked *assumed* are this lesson's own.

---

## 1. Mental Model

> **Media is not stored, it is forwarded, and every copy is a bill. Peer-to-peer makes the sender pay n-1 times; a mixer makes the server decode and re-encode; a selective forwarder (SFU) makes the server copy packets only, and lets each receiver have its own quality. The craft is in what the forwarder must preserve (sequence numbers, keyframes) and what it chooses (layers).**

- **The control plane and the media plane are separate.** Signalling (who is in the room, what each side can send) is ordinary request traffic; media is UDP packets with a deadline.
- **A late packet is a lost packet.** Reliability tricks (retransmission by NACK) work only within a small budget of milliseconds; beyond it you conceal or request a new keyframe.
- **Each receiver has its own bottleneck.** One sender, five viewers, five different downlinks: the server picks per receiver, which is why a forwarder beats a relay that copies everything.
- **Connectivity is a ranking problem.** The call must start even when no direct path exists, so there is always a last-resort relay.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "1:1 call", "2 to 4 people" | peer to peer works; the cost grows with n - 1 per sender (section 3) |
| "meeting with 25 / 100 / 1,000 people" | an SFU with simulcast, per-receiver layer choice, a few forwarded audio streams |
| "everyone must see one composite picture", "dial in from a phone or room system" | a mixer (MCU): decode, compose, re-encode; costly, but one stream per receiver |
| "users behind firewalls and NATs" | ICE with STUN, and a TURN relay as the last pair (section 6) |
| "video freezes when someone joins or the speaker changes" | layer switches only at keyframes; request one (section 7) |
| "one SFU is full" | place rooms across SFUs by region and load; RFC 7667 notes that selective forwarding middleboxes can be cascaded, but no design for it was read here |

---

## 3. Requirements and Capacity

**Functional.** Join and leave a room; audio and video with mute and camera toggles; screen share; an active-speaker view and a gallery; chat is a side channel. **Out of scope:** recording, transcription, end-to-end encryption design, the whiteboard.

**Non-functional.** Mouth-to-ear delay small enough for conversation; a call that connects behind most networks; degradation by quality, not by freezing; a failed media server costs seconds, not the meeting.

**Capacity estimate.** Every input is *assumed* and chosen to make the arithmetic readable, none is a vendor's number; results are reproduced by `capacity_check_f.py`.

| Input | Value |
|---|---|
| video layers a sender publishes (simulcast) | 150, 500 and 1,500 kbps |
| audio | 32 kbps per stream; a receiver gets the 3 most active speakers |
| gallery view of n people | all remote tiles at 150 kbps except the active speaker at 1,500 kbps |
| one server network card | 10 Gbps, planned at 50% |
| concurrent calls | 1,000 rooms of 25 people |
| calls needing a relay | 10% of participants |

| Result | Arithmetic | Value |
|---|---|---|
| mesh, sender uplink | (n - 1) x 1,500 kbps for n = 4, 8, 25, 100 | 4,500; 10,500; 36,000; 148,500 kbps |
| SFU, sender uplink | 150 + 500 + 1,500 + 32 | 2,182 kbps, whatever n is |
| SFU, receiver downlink, n = 25 | 23 x 150 + 1,500 + 3 x 32 | 5,046 kbps |
| one 25-person room at the server | ingress 25 x 2,182; egress 25 x 5,046 | 54.55 Mbps in; 126.15 Mbps out |
| rooms per server card | 5,000 Mbps / 126.15 Mbps | 39 rooms, 975 participants |
| all 25,000 participants | 25,000 x 5,046 kbps | 126 Gbps out: 26 server cards |
| relayed 10% | 2,500 x (5,046 + 2,182) kbps | 18.07 Gbps through relays |

Four conclusions. **Mesh stops being possible at about the size of a family meeting:** an uplink of 10.5 Mbps at 8 people is more than many home connections have, and 148.5 Mbps at 100 is not a number any user has; the cost is on the sender, which the sender cannot negotiate. **An SFU makes the sender's cost constant** and moves the bill to the server's egress, which grows with the square of the room if everyone sees everyone (n people times n - 1 tiles). **Forwarding fewer, lower layers is the lever:** the gallery above sends 23 tiles at the lowest layer; without simulcast every tile would cost one full-size stream. **The card count is a ceiling from bandwidth only.** The real limit is often packets per second and CPU on the forwarder, and no figure for that was read; measure it. The relay share (10%) is an assumption: the RFC says a relay is for paths that cannot be made direct (section 6) and says nothing about how often that is.

---

## 4. API and Data Model

```
POST /rooms/{id}/join     {user, capabilities}  -> {sfu_endpoint, token, ice_servers}        # control plane
WS   signalling           offer / answer / candidate (trickle), mute, subscribe(track, layer), leave
```

- `rooms(id, region, sfu_id, created_at)` and a presence set per room (`participants(room, user, tracks, muted)`), held in memory on the control plane and rebuilt from the SFU on failover.
- **Join information should be small.** Discord's post says a standard offer and answer exchange can be "close to ten kilobytes in size round-trip" and that their native clients exchange about 1,000 bytes (server address and port, encryption method and keys, codec, stream ids); their browser path stays under 1,200 bytes and synthesises the description on the client.
- **The server places the room, the client does not choose.** Discord's guild service watches service discovery and assigns the least utilised voice server in the region; the signalling component then pushes the room's state to that server and tells the clients (this lesson's design reuses the pattern for rooms; the read source describes it for voice channels).
- **Media security** (SRTP keyed through a DTLS handshake) is the browser default and is not re-taught here; note Discord's native clients use their own transport and keys, which is possible only because they control both ends.

---

## 5. Three Topologies

The RTP topologies RFC (7667) defines the vocabulary; the three that matter:

| Topology | Who copies | Server cost | Sender cost | Per-receiver quality |
|---|---|---|---|---|
| **Mesh** (peer to peer) | each sender, to every peer | none | n - 1 encoded streams | one per peer, but the sender encodes each |
| **Mixer (MCU)** | the server decodes, composes and re-encodes | CPU: decode every input, one encode per receiver mix | one stream | one stream per receiver, fixed layout |
| **SFU** (selective forwarding) | the server copies packets, never decodes | egress bandwidth and forwarding | one stream, or a few simulcast layers | per receiver, by choice of layer |

On audio mixing, the RFC notes that N inputs need N or N+1 mixes because each participant must hear everyone except themselves, which is why audio mixers decode every stream. On the SFU, the RFC describes the middlebox as selecting which of the active sources go to each endpoint, and says it came with simulcast and scalable video coding. Discord's reasons for a server in the middle, from its post: peer-to-peer "becomes prohibitively expensive" as participants grow (they report seeing 1,000 people taking turns speaking), the server keeps users' IP addresses from each other, and moderation (server mute drops the packets) is possible.

---

## 6. Connectivity: ICE, STUN and TURN

Each side gathers **candidates** (a transport address it might be reached on): *host* (a local interface), *server-reflexive* (what a STUN server saw), *relayed* (an address on a TURN server). ICE then tests candidate **pairs** with connectivity checks in priority order and uses the first that works. Priorities are formulas in RFC 8445:

- candidate priority = 2^24 x type preference + 2^8 x local preference + (256 - component id); recommended type preferences are 126 host, 110 peer-reflexive, 100 server-reflexive, 0 relayed; local preference 0 to 65535, component id 1 to 256;
- pair priority = 2^32 x MIN(G, D) + 2 x MAX(G, D) + (1 if G > D else 0), where G is the controlling agent's candidate priority and D the controlled agent's; checklists are sorted in decreasing pair priority.

```python
TYPE_PREF = {"host": 126, "prflx": 110, "srflx": 100, "relay": 0}   # RFC 8445 recommended values


def cand_priority(kind: str, local_pref: int = 65535, component: int = 1) -> int:
    return (1 << 24) * TYPE_PREF[kind] + (1 << 8) * local_pref + (256 - component)


def pair_priority(g: int, d: int) -> int:
    """g: the controlling agent's candidate priority, d: the controlled agent's."""
    return (1 << 32) * min(g, d) + 2 * max(g, d) + (1 if g > d else 0)


def pick_pair(local, remote, works, controlling: bool = True):
    """local, remote: [(kind, priority)]. works(i, j): does the connectivity check on that pair succeed.
    Returns (i, j) for the highest-priority working pair, or None."""
    pairs = []
    for i, (_, lp) in enumerate(local):
        for j, (_, rp) in enumerate(remote):
            p = pair_priority(lp, rp) if controlling else pair_priority(rp, lp)
            pairs.append((-p, i, j))
    for _, i, j in sorted(pairs):
        if works(i, j):
            return i, j
    return None
```

What the check pins: a default host candidate is **2130706431**, the number you see in session descriptions; a pair containing a relayed candidate ranks below every pair of non-relayed candidates (the MIN term dominates, and a relayed candidate with type preference 0 is below 2^24), tested on 2,000 random pairs; `pick_pair` returns the best working pair, compared with brute force on 300 random candidate sets in both roles; and when only the relayed pair works, ICE falls through to it.

**The 64-bit trap.** The largest pair priority is about 2^63, and **two distinct pairs of host candidates differ by less than a double-precision float can represent** above 2^53: the check finds distinct pair priorities that are equal as floats. In a language whose numbers are doubles (JavaScript), keep these as BigInt or integers; sorted by float, ties break arbitrarily and the controlled side may rank pairs differently from the controlling side, which is the one thing the formula exists to prevent. The maximum fits a signed 64-bit integer (also asserted: below 2^63).

**Why TURN exists, from RFC 8656:** hole punching generally fails when both hosts are behind NATs with address-dependent mapping; many enterprise networks forbid direct UDP, and "WebRTC requires support for this scenario"; some users want IP location privacy and send only relayed candidates. Discord's design sidesteps ICE: every client talks to its media server, so they "do not need ICE", and periodic pings keep firewall holes open (their native clients; the browser path still uses the standard stack). **An SFU deployment is ICE-simple on the server side (a public address) and TURN-heavy on the client side**, because the server cannot reach into a client's NAT.

---

## 7. What an SFU Must Preserve

An SFU forwards RTP packets without decoding them. RFC 7667 section 3.7 is precise about what it must rewrite: each receiver sees an independent RTP session, so SSRC numbers can differ per receiver, and **the sequence number must be consecutively incremented for the packets actually sent in that session; the offset changes each time a source is turned on; the timestamp (possibly offset) stays the same**. Discord's post says the same cost applies to silence suppression: when a client stops sending audio, "both client and server must be prepared to cease receiving audio data any time and rewrite audio/video packet sequence numbers".

Why it matters: a receiver detects loss from gaps in sequence numbers (RFC 3550 keeps a 16-bit number and an extended count of wraps). If the SFU copies upstream numbers when it switches from speaker A to speaker B, the receiver sees a jump (A at 1,200, then B at 40,000) and treats it as 38,800 lost packets, asks for them, and corrupts its statistics. The rule, and the test, is: **preserve a real upstream gap, hide a switch.**

```python
M16 = 1 << 16


class Forwarder:
    """One receiver's view of one forwarded stream. Forwards a single source at a time. A switch (or a resume after
    a pause) waits for a keyframe of the wanted source. Within a source the receiver sees the upstream sequence gaps
    (so it can ask for the missing packets); at a switch the numbers continue straight on, with no gap. A packet from just before (within 100 numbers of)
    the keyframe the run started on is dropped (it would reuse a number already sent). A keyframe whose sequence number jumps
    (a sender that restarted its numbering) starts a new run the same way; a jump without a keyframe waits for one. Timestamps pass through."""
    WINDOW = 1024
    MAX_DROPOUT, MAX_MISORDER = 3000, 100      # the thresholds RFC 3550 appendix A.1 uses to judge a sequence number

    def __init__(self, first_out: int = 0):
        self.next_out = first_out % M16
        self.src = None            # the source currently forwarded
        self.want = None           # the source the receiver should get
        self.offset = 0            # out = (source seq + offset) mod 2^16, valid for the current run
        self.anchor = 0            # source seq of the keyframe the current run started on
        self.hi = 0                # highest source seq seen in the current run
        self.sent = {}             # out seq -> (source, source seq), the most recent WINDOW

    def select(self, src):
        self.want = src
        if src is None:
            self.src = None        # paused: nothing flows until a keyframe of a wanted source arrives

    def _start_run(self, src, seq):
        self.src, self.anchor, self.hi = src, seq, seq
        self.offset = (self.next_out - seq) % M16

    def forward(self, src, seq: int, ts: int, key: bool):
        if src == self.want and src != self.src:
            if not key:
                return None        # cannot start in the middle of a picture
            self._start_run(src, seq)
        elif src is not None and src == self.src:
            delta = (seq - self.hi) % M16
            if self.MAX_DROPOUT <= delta < M16 - self.MAX_MISORDER:      # neither next nor a little late: the numbering restarted
                if not key:
                    return None
                self._start_run(src, seq)
        if src != self.src:
            return None
        if (seq - self.anchor) % M16 >= M16 - self.MAX_MISORDER:
            return None            # a straggler from just before the keyframe this run started on
        if (seq - self.hi) % M16 < M16 // 2:
            self.hi = seq
        out = (seq + self.offset) % M16
        if (out + 1 - self.next_out) % M16 < M16 // 2:     # a late packet must not move the counter backwards
            self.next_out = (out + 1) % M16
        self.sent.pop(out, None)
        self.sent[out] = (src, seq)
        while len(self.sent) > self.WINDOW:
            del self.sent[next(iter(self.sent))]
        return out, ts

    def lookup(self, out: int):
        """A NACK for `out`: the source packet to resend, or None (never received upstream: ask the sender)."""
        return self.sent.get(out)
```

The check does not trust a reference copy of this code: it generates 400 random sessions (three sources with start numbers near the 16-bit wrap, random selects and pauses, random upstream gaps, random keyframes) and verifies the **receiver-visible spec** on every pair of consecutive forwarded packets: within one source, the distance between output numbers equals the distance between upstream numbers; across a switch, it is exactly one; timestamps are untouched; the first packet takes the receiver's first number; and every recent output number maps back to its source packet. Hand cases pin that nothing flows before a keyframe, that the old source keeps flowing until the new keyframe arrives, that a late packet takes its own number without moving the counter, that a restarted sender (a keyframe whose sequence number jumps, in the same source) starts a new run with no gap, that a jump without a keyframe is dropped, and that a packet of the new source older than the switch keyframe is dropped instead of reusing a number already sent. A restart normally brings a new SSRC, which this model would treat as a new source; the same-source case is covered because a sender may keep its SSRC. The limit, as in RFC 3550's own heuristic: a restart to a number within 100 below the last one looks like a late packet and is dropped until the numbers move on.

**NACK.** Loss feedback is RFC 4585's Generic NACK: a packet id (PID) and a 16-bit mask for the 16 packets after it, so one entry reports up to **17 packets** (the sender must not infer that unmarked packets arrived). The packing is a covering problem on extended sequence numbers (the receiver already keeps 32 bits per RFC 3550), with the 16-bit reduction applied last so a run across the wrap packs into one entry:

```python
def nack_fcis(lost):
    """lost: extended (non-wrapping) sequence numbers. Returns [(pid, blp)] covering exactly those packets, greedy from the lowest."""
    xs = sorted(set(lost))
    out, i = [], 0
    while i < len(xs):
        start, blp = xs[i], 0
        i += 1
        while i < len(xs) and xs[i] - start <= 16:
            blp |= 1 << (xs[i] - start - 1)
            i += 1
        out.append((start % M16, blp))
    return out


def nack_decode(fcis):
    """The set of 16-bit sequence numbers an entry list reports lost."""
    got = set()
    for pid, blp in fcis:
        got.add(pid)
        got |= {(pid + k) % M16 for k in range(1, 17) if blp >> (k - 1) & 1}
    return got
```

Checked: decode equals the input reduced mod 2^16 (no phantom losses) on 500 random sets including ones across the wrap; the packing has the minimum number of entries compared with brute force on every set of nine or fewer; 17 consecutive packets fit in one entry and an 18th needs another.

**Keyframes.** Switching sources or layers cannot start mid-picture, which is why `forward` waits for a keyframe; the RFC notes the middlebox needs conference-related control such as a Full Intra Request to ask the sender for a switching point. A burst of switches is therefore a burst of keyframe requests, which are large; limit the rate of layer changes and prefer a conservative step up.

---

## 8. Choosing Layers per Receiver

The sender publishes a few simulcast layers (RFC 8834 describes systems that show the active speaker large and others as thumbnails, with senders sending high and low resolution versions). The SFU decides, per receiver, which layer of which sender to forward, under that receiver's estimated downlink. That is a *multiple-choice knapsack*: each tile takes one option (including "off"), each costs bitrate and gives value (the tile's weight times the layer's quality). The values below (weights 1 to 5, quality 1, 2, 3 for the three layers) are *assumed*.

```python
def allocate(budget: int, tiles):
    """Exact. tiles: [(weight, [(kbps, quality), ...])] with each option list starting at (0, 0). budget in kbps (integer).
    Returns (value, index of the chosen option per tile) maximising sum(weight x quality) within the budget."""
    best = [0] * (budget + 1)
    picks = []
    for w, opts in tiles:
        new, pick = [0] * (budget + 1), [0] * (budget + 1)
        for b in range(budget + 1):
            for k, (kbps, q) in enumerate(opts):
                if kbps <= b and best[b - kbps] + w * q > new[b]:
                    new[b], pick[b] = best[b - kbps] + w * q, k
        picks.append(pick)
        best = new
    b, chosen = budget, []
    for t in range(len(tiles) - 1, -1, -1):
        k = picks[t][b]
        chosen.append(k)
        b -= tiles[t][1][k][0]
    return best[budget], chosen[::-1]


def greedy(budget: int, tiles):
    """Upgrade the tile with the best value gained per extra kbps until nothing fits."""
    pick, used = [0] * len(tiles), 0
    while True:
        cand = None
        for i, (w, opts) in enumerate(tiles):
            if pick[i] + 1 < len(opts):
                dk = opts[pick[i] + 1][0] - opts[pick[i]][0]
                dv = w * (opts[pick[i] + 1][1] - opts[pick[i]][1])
                if used + dk <= budget and (cand is None or dv / dk > cand[0]):
                    cand = (dv / dk, i, dk)
        if cand is None:
            break
        pick[cand[1]] += 1
        used += cand[2]
    return sum(w * opts[pick[i]][1] for i, (w, opts) in enumerate(tiles)), pick
```

**The example** (assumed values): one speaker (weight 3) and eight thumbnails (weight 1), three layers each. With a 1,800 kbps downlink the exact answer is unique: the speaker at 500 kbps and every thumbnail at 150 kbps, 1,700 kbps in all, value 14; the 1,500 kbps layer for the speaker would leave only 300 kbps for eight thumbnails. With 1,500 kbps the best value is 12, and it switches two thumbnails off rather than lower the speaker. At 2,000 kbps two different plans tie at value 14, so a real allocator needs a tie rule (prefer the plan that uses less bandwidth, to leave headroom). The check compares `allocate` with brute force over every combination on 300 random calls, requires that the budget is never exceeded, that more bandwidth never lowers the value, and that the greedy heuristic is never better than exact. Greedy is a reasonable heuristic that is not exact: on 300 random calls it was worse than exact in 20 of 300 random calls, worst 13% below (a seeded simulation; illustrative, not a property of any product).

**Honest limits.** A real allocator has more inputs than this model: the downlink estimate is itself noisy, the rule must not flap (each switch needs a keyframe), tile size on screen should cap the layer, and audio is always kept ahead of video. The RFCs on congestion control (RFC 8836 gives requirements) and the sender-side estimators were not read in depth here; the lesson's allocator shows the shape of the decision, not a tuned one.

---

## 9. High-Level Design

1. **Signalling service** (WebSocket): joins, offers, candidates, mute, subscriptions; stateless beyond a room's membership, which it can rebuild.
2. **Room placement:** choose the SFU for a room by region and current load; keep a room on one SFU so forwarding is local; tell the clients where to connect.
3. **SFU:** receives each sender's layers, forwards per receiver (sections 7 and 8), terminates RTCP feedback, and reports load.
4. **TURN fleet** reachable on UDP and TCP/443 for restrictive networks, scaled on relayed bandwidth.
5. **Recording and transcription** consume a copy of the forwarded streams as an extra "receiver", off the call's critical path.

Discord's failover design, as read: the signalling component constantly monitors its media process, restarts it on a crash and rebuilds its state without client involvement; if a voice server dies, it fails its periodic ping, drops out of service discovery, and clients reconnect to a newly assigned server after the guild service pushes the room state to it. A denial-of-service attack is handled the same way (remove the server, reassign, re-add when it subsides). That is the pattern: **keep the room's state somewhere rebuildable, and make "assign a new media server" the one recovery action.**

---

## 10. Failure Modes

| What breaks | What you see | Defence |
|---|---|---|
| SFU process crash | a brief interruption (Discord's post says a few dropped packets when its SFU process is restarted; a host failure takes longer, and no figure for it was read) | the signalling side restarts it and replays room state; clients reconnect |
| SFU host lost or attacked | everyone in the rooms on it drops | remove from discovery, reassign rooms, push state (Discord's pattern) |
| sequence copied across a switch | receivers request tens of thousands of "lost" packets | rewrite per receiver (section 7) |
| layer flapping | repeated keyframes, frozen video | hysteresis on the allocator, a minimum time between changes |
| no relay reachable | some users cannot join | TURN on TCP/443 and over TLS; measure join failures by network type |
| everyone sees everyone in a big room | egress grows with n squared | forward audio of the few loudest, video of the visible tiles at the lowest layer that fits |
| pair ranking differs between the peers | a call connects on a worse path than needed | exact integer priorities (the float trap, section 6) |
| NACK storm | retransmissions use the bandwidth that was already short | limit the NACK budget; ask for a keyframe instead beyond a threshold |

---

## 11. What Real Systems Did

- **Discord** (Jozsef Vass, "How Discord Handles Two and Half Million Concurrent Voice Users using WebRTC", 10 September 2018, read in full 2026-11-27): an SFU written in C++ forwarding audio and video, native clients built on the WebRTC native library with their own transport, Elixir signalling, service discovery on etcd, and "more than 850 voice servers in 13 regions" at the time of writing. The post is about voice channels (with video added) at one company in 2018; do not assume it describes any other product.
- **The RFCs** (read in the parts listed below) define the topologies, the ICE ranking, the TURN relay and the feedback messages; they do not say what any vendor's SFU does internally.
- **Zoom, Google Meet:** no source read.

---

## 12. Pitfalls Checklist

1. **Mesh for "small" rooms without the arithmetic.** n - 1 uplinks is a sender-side cost the sender cannot negotiate.
2. **Copying upstream sequence numbers across a switch.** The receiver sees a huge loss.
3. **Rewriting the timestamp.** The RFC keeps it (possibly offset); touching it breaks lip sync.
4. **Switching layers mid-picture.** Wait for a keyframe, and rate-limit switches.
5. **Float priorities.** Above 2^53 two different pairs compare equal; use integers.
6. **No relay.** Some networks have no direct path at all (RFC 8656's own motivation).
7. **Sizing by bandwidth only.** Packets per second and CPU limit a forwarder first; measure.
8. **Treating NACK as unlimited.** Each retransmission competes with live media; past a budget, ask for a keyframe.
9. **Room state only in the media process.** A restart loses the room; keep it rebuildable elsewhere.
10. **Claiming a product's design from a vendor blog about another.** Say which source says what.

---

## Drills

1. A room of 8 uses mesh at 1.5 Mbps video. What uplink does each person need, and what changes with an SFU and three simulcast layers?
2. Why does a candidate pair containing a relayed candidate always rank below a pair of host and server-reflexive candidates, however the local preferences are set?
3. Explain with numbers why computing pair priority in a double-precision float can give two different pairs the same priority.
4. An SFU switches a receiver from speaker A (sequence 1,200) to speaker B (sequence 40,000) and copies the numbers. What does the receiver do, and what should the SFU have sent?
5. The receiver lost packets 65,534, 65,535, 0 and 1 (wrapping). Write the Generic NACK entry and say how many packets one entry can report.
6. A receiver has 1,800 kbps downlink, one speaker and eight thumbnails, with three layers each. Which layers does the exact allocation choose, and what does greedy risk?
7. A room's SFU host dies. List the steps from detection to media flowing again, and say what must be stored outside the media process.
8. For 1,000 rooms of 25, compute the egress and the number of server cards, and name the two limits the calculation ignores.

---

## Homework

1. Run `sy61_check.py` on this file. Make `Forwarder.forward` copy the upstream sequence number and find the first failing assertion; then drop the keyframe wait and find which fails.
2. Change `pair_priority` to use `float` and find the smallest local-preference difference at which two pairs collide.
3. Add a late-join case to the forwarder: a receiver that joins mid-stream must start at a keyframe; write the failing test first.
4. Add a minimum dwell time (hysteresis) to a stateful allocator wrapper and measure the number of layer changes on a noisy budget series against the memoryless one.
5. Read RFC 8445 section 6.1.2 and list which fields in your candidate structure the controlled side must also know.

---

## Sources

All read 2026-11-27. The code, the allocator's values and the figures marked *assumed* are this lesson's own.

- RFC 7667, *RTP Topologies* (November 2015): the contents and sections 3.4 (mesh), 3.6.1 (media-mixing mixer) and 3.7 (selective forwarding middlebox) read; the rest not read.
- RFC 8445, *Interactive Connectivity Establishment* (July 2018): section 5.1.2 (candidate priority) and section 6.1.2.3 (pair priority) read; the rest searched, not read in full.
- RFC 8656, *TURN* (February 2020): the introduction on why a relay is needed; the protocol details not read.
- RFC 3550, *RTP*: the sequence-number fields and appendix A.1 (validity and wrap handling) read; the rest not read.
- RFC 4585, *RTP/AVPF*: section 6.2.1 (Generic NACK) read.
- RFC 8834, *Media Transport and Use of RTP in WebRTC*: the passage on simulcast and middleboxes only.
- Jozsef Vass, Discord engineering blog, 10 September 2018: read in full.

## Further reading (not consulted)

Anything from Zoom, Google Meet, Jitsi, mediasoup or Microsoft Teams; the WebRTC W3C specification; the Google congestion-control and transport-wide feedback documents (RFC 8836 was opened for its title and scope only); RFC 8853 on simulcast signalling; RFC 5389 on STUN; research on cascaded SFUs and end-to-end encrypted conferencing. None were read, so no claim is made about them.

*Last reviewed: 27 November 2026.*
