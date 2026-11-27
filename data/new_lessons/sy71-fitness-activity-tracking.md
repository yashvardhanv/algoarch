# Lesson 71 — Case Study: Fitness Activity Tracking (Strava)

> **Priority:** ★★☆☆☆ (proposed; the curriculum data holds the final rating) — it appears less often than the headline designs, but it exercises a pipeline problem every upload product has: noisy sensor data in, cheap summaries and a geographic match out, with retries that must not duplicate anything.
>
> **Study time:** 65 minutes. **Do this after:** Proximity Service & Location-Based Systems; Scaling Patterns II: Large Blobs, Long-Running Tasks and Real-Time Updates; Top-K and Trending (YouTube top videos, hashtags).
>
> **Level:** extended.

A phone or watch records a position every second; an hour of running is about 3,600 points. The service has to turn that into a distance, a climb, a map thumbnail and a time on every popular stretch of road the athlete passed, within seconds of upload, for millions of uploads a day, and survive the same file arriving twice. The code is checked in `test/lesson_code/sy71_check.py`; capacity figures come from `capacity_check_i.py`. Geographic indexing is not re-taught (see Proximity Service & Location-Based Systems), nor is leaderboard ranking (see Real-Time Gaming Leaderboard).

---

## 1. Mental Model

> **An activity is a noisy time series. Every number the product shows is a derived quantity, and each derivation has a failure mode you can state and test: distance from jittery points, climb from noisy altitude, a segment time from a track that merely passes near a start line.**

- **Raw points are write-once input; everything else is recomputable.** Keep the raw file and rebuild summaries if the algorithm improves.
- **Noise accumulates.** Adding up small altitude wiggles invents climbing. The cure is a threshold, and the threshold is a product decision (section 5).
- **Store the shape cheaply.** A track compresses well two ways: delta-encode it (polyline format) and drop points that do not change the shape (Douglas-Peucker).
- **Matching is geometry plus an index.** Testing one track against every segment is impossible; a grid on segment start points leaves a handful of candidates per point (section 7).
- **Process at least once, write idempotently.** Uploads are retried and workers die; the same job twice must leave the same rows.

---

## 2. Recognition Reflex

| If the prompt says... | Reach for |
|---|---|
| "upload a GPS file", "process after upload" | store the raw file, enqueue, return an id; workers compute summaries; client polls or gets a push (section 8) |
| "total distance and elevation" | haversine per step; climb with a noise threshold (section 5) |
| "draw the route on a feed card" | simplified, delta-encoded polyline, not the raw stream (section 6) |
| "fastest time on this hill", "segments" | grid index on segment starts, then a track walk (section 7) |
| "leaderboard per segment" | one sorted set per segment, best effort per athlete; see Real-Time Gaming Leaderboard |
| "heatmap of all activities" | aggregate points into tiles offline; see Top-K and Trending for counting at scale |
| "same activity uploaded from two apps" | exact duplicates by content hash; near-duplicates need a time-overlap rule, which hashing does not give you |

---

## 3. Requirements and Capacity

**Functional.** Upload a recording from a file or a device; compute distance, moving and elapsed time, climb; draw the route; find the athlete's time on each segment passed; show segment leaderboards; send updates to followers; let partner apps be notified of new activities.

**Non-functional.** An upload is accepted fast and processed within seconds; a duplicate delivery or a worker crash never creates two activities or two effort rows; summaries can be recomputed from the raw file; read traffic (feeds, maps) dominates processing traffic.

**Capacity.** Every input is an assumption chosen to size the design (not a product statistic); outputs are computed in `capacity_check_i.py`. The polyline and simplification sizes come from running this lesson's code on a synthetic track and are illustrative.

| Quantity | Assumption or derivation | Result |
|---|---|---|
| Activities per day | assumed | 5 million, about 58 per second average |
| Peak upload rate | assumed 10 times the average (a weekend morning) | about 579 per second |
| Points per activity | 1 hour at 1 point per second (assumed) | 3,600 |
| Raw size per activity | 16 bytes per point (assumed: time, latitude, longitude, altitude, heart rate) | 57,600 bytes |
| Raw size per day | 5 million x 57,600 bytes | 288 GB |
| Same track as an encoded polyline | synthetic 3 m/s winding track, one point per second; compared with latitude and longitude alone at 8 bytes per point (28,800 bytes) | 7,208 bytes, 4.0 times smaller |
| After Douglas-Peucker at 5 m, then encoded | same track | 64 of 3,600 points, 252 bytes |
| Jobs in flight at the peak | 579 per second x an assumed 2 seconds of processing | about 1,157 |
| Segment tests, scan everything | 3,600 points x an assumed 20 million segments | 72 billion per activity |
| Segment tests with a grid | 3,600 points x 9 cells x an assumed 5 segment starts per cell | 162,000 per activity |

The last two rows are the case for the index: about 444,444 times less work per activity. The "5 starts per cell" figure is an assumption about a 100 m cell; a dense city centre will be higher, and the design needs a finer grid or a cap for those cells.

---

## 4. API and Data Model

```
POST /uploads              multipart file (FIT, TCX, GPX, gz) -> {upload_id, status: queued}
GET  /uploads/{id}         -> {status: queued|processing|ready|error, activity_id?}
GET  /activities/{id}      -> summary fields + summary polyline
GET  /activities/{id}/streams?keys=time,distance,latlng,altitude
GET  /segments/{id}/leaderboard
POST webhook (to partner)  {object_type, object_id, aspect_type, owner_id, event_time}
```

| Store | Key | Notes |
|---|---|---|
| raw files | content hash | immutable, in object storage |
| activities | activity id | athlete, start time, summary figures, summary polyline, state |
| streams | activity id + stream key | arrays by time; fetched on demand, not on the feed |
| segments | segment id | polyline, length, grid cell of the start |
| efforts | (activity id, segment id) | elapsed time, start and end index; the unique key makes re-processing harmless |
| leaderboards | segment id | best effort per athlete; see Real-Time Gaming Leaderboard |

The shape of this API (asynchronous upload with a status step, streams by key, a segment search by bounding box, webhooks) follows what Strava's public developer documentation exposes, listed in section 8. How their servers are built is not public in anything read for this lesson.

---

## 5. Deep Dive 1: Distance, Climb and Moving Time From Noisy Points

```python
import math


def haversine(lat1, lon1, lat2, lon2, r=6_371_000.0):
    """Great-circle distance in metres between two latitude/longitude points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def elevation_gain(eles, thr):
    """Climb counted only when the level has moved at least `thr` metres from the last accepted level."""
    ref, gain = eles[0], 0.0
    for e in eles[1:]:
        if e - ref >= thr:
            gain += e - ref
            ref = e
        elif ref - e >= thr:
            ref = e
    return gain


def moving_time(ts, ds, v_min):
    """Seconds spent at or above v_min metres per second; ts are seconds, ds cumulative metres."""
    total = 0
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if dt > 0 and (ds[i] - ds[i - 1]) / dt >= v_min:
            total += dt
    return total
```

**Distance.** Sum the haversine distance of consecutive points. The check pins the one-degree value: 111,194.93 metres of latitude (`2 pi R / 360` with R = 6,371,000 m), the same for a degree of longitude on the equator, about half that at 60 degrees north, and correct across the antimeridian.

**Climb.** Summing every positive altitude step counts noise. On a perfectly flat track with 1 Hz altitude noise of up to 2 metres either way, 3,600 samples (seed 71) add up to 2,401 metres of invented climbing; `elevation_gain` with a 5 m threshold reports 0. The rule: keep a reference level, count the climb only when the level has moved at least the threshold from it, and move the reference on a drop of at least the threshold. On a true 300 m ramp with the same noise the check requires the result within 12 m of 300 over 50 runs. That 12 m is what the check observed on these ramps, not a theorem. The threshold also hides real climbs smaller than itself (a rolling course of 3-metre bumps reports zero) and it loses up to the threshold from every climb it does count: a 7 m climb in 1 m steps with a 5 m threshold reports 5 m, so a course of 7 m hills under-reports by about 30 percent. Choose it against the sensor, not once for everything. The check pins the edges: a climb of exactly the threshold counts, one hair below does not, a drop of exactly the threshold moves the reference, and descending first then climbing follows the drop. Strava's upload documentation says elevation gain is read from the file header when the device has a barometric altimeter and otherwise computed from the elevation data, so the two can differ.

**Moving time.** Elapsed time is end minus start; moving time counts only intervals at or above a speed floor. The check shows a stop removed, a speed exactly at the floor counted, a slow interval below the floor not counted, and a long standing gap not counted. Strava's activity objects carry both `moving_time` and `elapsed_time`. The floor is a choice: too high drops slow climbs, too low counts GPS jitter at a standstill as walking.

---

## 6. Deep Dive 2: Storing and Shipping the Route

A route has to appear on feed cards and map pages, so the service wants a small version of it. Two independent tools:

1. **Encoded polyline.** The format Google documents: multiply each coordinate by 100,000 and round, store only the difference from the previous point, fold the sign into the low bit, then emit 5-bit chunks (low chunk first) with a continuation flag, each shifted by 63 into printable ASCII.
2. **Douglas-Peucker.** Keep the two endpoints; find the point farthest from the segment joining them; if it is more than `eps` away keep it and recurse on both halves, otherwise drop everything between.

```python
def _enc(v):
    v = ~(v << 1) if v < 0 else v << 1             # sign into the low bit
    out = ''
    while v >= 0x20:
        out += chr((0x20 | (v & 0x1F)) + 63)       # five bits, continuation flag, offset 63
        v >>= 5
    return out + chr(v + 63)


def encode_polyline(points):
    out, plat, plon = '', 0, 0
    for lat, lon in points:
        la, lo = math.floor(lat * 1e5 + 0.5), math.floor(lon * 1e5 + 0.5)    # half rounds up
        out += _enc(la - plat) + _enc(lo - plon)    # only the change from the previous point is stored
        plat, plon = la, lo
    return out


def decode_polyline(s):
    pts, i, lat, lon = [], 0, 0, 0

    def number():
        nonlocal i
        shift = result = 0
        while True:
            b = ord(s[i]) - 63
            i += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        return ~(result >> 1) if result & 1 else result >> 1

    while i < len(s):
        lat += number()
        lon += number()
        pts.append((lat / 1e5, lon / 1e5))
    return pts


def seg_dist(p, a, b):
    """Distance from point p to the segment ab (not the infinite line)."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def rdp(pts, eps):
    """Douglas-Peucker with an explicit stack: keep the endpoints, split at the farthest point if it is more than eps away."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        dmax, idx = -1.0, a
        for i in range(a + 1, b):
            d = seg_dist(pts[i], pts[a], pts[b])
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(pts, keep) if k]
```

The check pins the format against Google's page: the three points (38.5, -120.2), (40.7, -120.95), (43.252, -126.453) encode to `_p~iF~ps|U_ulLnnqC_mqNvxq`@`, and the single longitude -179.9832104 encodes to the chunks 33, 63, 48, 42, 34, 1 (before the 63 offset), as in the page's worked steps. Round trips of 300 random point lists at 5 decimal places, large jumps that need several chunks, and the empty list all pass. The format is lossy because of the rounding: a step is 1e-5 degrees (about 1.1 m), so a coordinate moves by at most about 0.56 m, and the check requires a point to move by less than 0.8 m over 200 random unrounded points. Python's `round` breaks exact ties to even, so the lesson rounds half up with `floor(x + 0.5)`; Google's page says only "rounding the result", so an encoder that ties differently can disagree by one unit at an exact half.

Douglas-Peucker is checked against a recursive reference on 400 random lattices (small integer coordinates, so distances equal to `eps` occur and the strict comparison matters) and for the property that matters: every dropped point lies within `eps` of the segment between the kept points on either side of it. That guarantee holds because `seg_dist` measures distance to the *segment*; measuring to the infinite line through the endpoints can drop a point that is far from the actual path. The iterative form avoids Python's recursion limit on a 5,000-point track.

Two measured facts, both on this lesson's synthetic tracks:

- On a smooth 3,600-point hour the encoded polyline alone is 7,208 bytes, 4.0 times smaller than the same two fields at the assumed 8 bytes per point (28,800 bytes; the polyline holds neither time, altitude nor heart rate, so against the full 57,600-byte record the saving would look like 8.0 times, which credits it for dropping three fields); adding Douglas-Peucker at 5 m keeps 64 points and 252 bytes. On a 5,000-point sine-like track with 1 m noise the check requires fewer than a quarter of the points to survive at `eps` 3.
- **The worst case is quadratic.** A zig-zag that alternates between two levels leaves nothing to drop, and the farthest-point search splits off one point at a time. The check keeps all 500 points of such a track (500 rather than 5,000 because the cost is quadratic). If an adversarial upload can do that, cap the point count or time-box the simplification.

Keep the raw stream for analysis and store the simplified polyline as the summary field; Strava's API reference shows an activity map with both a full `polyline` and a `summary_polyline`.

Visual (planned): a track, the first split point, and the corridor of width eps around the simplified path.

---

## 7. Deep Dive 3: Segment Matching

A segment is a stretch of road with a start, an end and a shape. An effort is a stretch of the athlete's track that starts near the segment start, stays on the segment's line, and ends near its end. The matcher below uses planar metres (convert latitude and longitude to a local projection first; the geometry is the same).

```python
import hashlib
from collections import defaultdict


def pdist(p, poly):
    return min(seg_dist(p, poly[i], poly[i + 1]) for i in range(len(poly) - 1))


class SegmentIndex:
    """Segment start points in a grid. A cell at least as wide as the tolerance means a 3 x 3 look-up cannot miss."""
    def __init__(self, segments, tol, cell):
        assert cell >= tol
        self.segs, self.tol, self.cell = segments, tol, cell
        self.starts = defaultdict(list)
        for sid, poly in segments.items():
            self.starts[self._cell(poly[0])].append(sid)

    def _cell(self, p):
        return (math.floor(p[0] / self.cell), math.floor(p[1] / self.cell))

    def near_start(self, p):
        cx, cy = self._cell(p)
        return [sid for dx in (-1, 0, 1) for dy in (-1, 0, 1) for sid in self.starts.get((cx + dx, cy + dy), ())
                if math.dist(p, self.segs[sid][0]) <= self.tol]


def match_efforts(track, index):
    """track: [(t, x, y)]. Returns {segment id: (elapsed, start index, end index)}, the best effort per segment.
    An effort starts near the segment start, stays within tol of the segment's line, passes near each intermediate
    vertex in order, and ends near its end."""
    tol, best = index.tol, {}
    for i, (t0, x, y) in enumerate(track):
        for sid in index.near_start((x, y)):
            poly = index.segs[sid]
            m, k = len(poly) - 1, 1                     # vertices 1 .. m-1 are the intermediate ones; k is the next to visit
            for j in range(i, len(track)):
                p = track[j][1:]
                if pdist(p, poly) > tol:
                    break                               # left the segment: no effort from this start
                while k < m and math.dist(p, poly[k]) <= tol:
                    k += 1
                if j > i and k == m and math.dist(p, poly[-1]) <= tol:
                    cand = (track[j][0] - t0, i, j)
                    if sid not in best or cand < best[sid]:
                        best[sid] = cand
                    break
    return best


class ActivityStore:
    """The activity id is a hash of (athlete, track); effort rows are keyed (activity, segment), so replays overwrite."""
    def __init__(self):
        self.activities, self.efforts = {}, {}

    def ingest(self, athlete, track):
        aid = hashlib.sha256(repr((athlete, track)).encode()).hexdigest()[:16]
        self.activities.setdefault(aid, {'athlete': athlete, 'track': track, 'state': 'queued'})
        return aid

    def process(self, aid, index, crash_after=None):
        act = self.activities[aid]
        if act['state'] == 'done':
            return
        n = 0
        for sid, effort in sorted(match_efforts(act['track'], index).items()):
            self.efforts[(aid, sid)] = effort
            n += 1
            if crash_after is not None and n >= crash_after:
                raise RuntimeError('worker died')
        act['state'] = 'done'
```

The rules, in the order the matcher applies them:

1. **Index lookup.** Segment starts sit in a grid whose cells are at least as wide as the tolerance, so a start within `tol` of a point is always in the point's cell or one of the eight around it. The constructor refuses a cell narrower than the tolerance, and the check puts a start at x = 99 and a track point at x = 101, across a cell border.
2. **Stay on the line.** From a start index, walk forward while every point is within `tol` of the segment polyline; a point farther away ends the attempt. That rejects a shortcut (start and end near, middle far): the check's straight cut across an L-shaped segment is not an effort, and neither is riding the segment backwards.
3. **Visit the vertices in order, then end near the end.** The effort must pass within `tol` of each intermediate vertex of the segment in order, and the first point after that which is near the segment end completes it; its time is the difference of the two timestamps. Without the vertex rule a loop, a lap or an out-and-back (whose end is within `tol` of its start) would "finish" one sample after it started, and every rider would hold the record. The same rule makes a track visit the tip of a spur. Its limit: vertices only constrain the track where the segment has them, so a segment with long straight edges can still be cut short between two vertices inside the tolerance; a minimum distance travelled along the segment is the usual extra guard.
4. **Best effort.** Several candidate starts (every point within tolerance) and several laps give several efforts; keep the smallest elapsed time (two starts of one effort cannot tie unless two samples share a timestamp, so no tie-break is needed). The check's two-lap track keeps the second lap (6 s against 9 s).

The check compares this matcher with an exhaustive one over 60 random cases of 12 segments each (8 cut from the track with noise, about a third of those ridden reversed, 3 random lines and a loop cut from the track), over tracks that either do or do not follow them, and the efforts agree in every case, with more than 50 efforts across the run so the comparison is not vacuous. The exhaustive version is written as a specification, not as a copy of the matcher: it tries every start and end pair and requires every point between to be near the line and the intermediate vertices to be matched by a chain of points in order (a set-based search, not the matcher's walk). Hand cases cover a loop sat on at its start (no effort), a loop ridden in full (8 s), a loop with a corner cut (none), an out-and-back ridden in full and one turned around halfway (none), a spur ridden past and ridden to its tip.

**Resolution.** Times come from sample timestamps, not interpolation, so an effort has the sampling resolution of the recording (one second at 1 Hz), and a tolerance of 25 m can start the clock a few seconds before the true line. Leaderboard fairness depends on that choice; interpolating the crossing time is the usual refinement and is left to the homework.

**Backfill.** A new segment applies to future uploads for free. Applying it to past activities needs a scan of activities whose track passes through the new segment's start cell, which is a reason to keep a cell index of recorded tracks too.

---

## 8. Deep Dive 4: The Upload Pipeline

An upload goes through four steps: accept and store the raw file, parse and summarise, match segments, publish (feed fan-out, webhooks to partners). The accept step returns before the rest runs. Each later step must tolerate running twice, because the queue delivers at least once and workers die mid-job.

`ActivityStore` above does this with two keys. The activity id is a hash of the athlete and the track, so a repeated upload maps to the same row (`ingest` twice gives one record; a different athlete gives a different one). Effort rows are keyed by `(activity, segment)`, so a re-run overwrites rather than appends, and the state flips to done only after all rows are written. The check crashes the worker after the first, second and third effort row, re-runs it twice, and requires the same three rows as a clean run each time.

**Limits of the hash.** A content hash catches the same file twice. It does not catch the same ride recorded by a watch and a phone, whose points differ. That needs a rule (same athlete, overlapping time window, similar start point) and a product decision about which copy wins.

**What Strava's public documentation says** (pages read on 27 November 2026): an upload is asynchronous and "enqueues the file for processing"; the activity does not appear in other API requests until processing finishes; polling at one second or longer is recommended; the mean processing time is stated as under 2 seconds; errors include duplicate data submission. Its webhook events API pushes a POST on activity creation, deletion and a few field updates, expects a 200 within two seconds, retries up to a total of three attempts, and tells receivers to do heavier work asynchronously. The default application rate limit is 200 requests per 15 minutes and 2,000 per day, with 100 and 1,000 for the non-upload endpoints; limits are returned in response headers and exceeding them returns 429. The lesson uses these as hints about the shape of such a platform, not as statements about the internals.

---

## 9. Failure Modes

| What breaks | What happens | Mitigation |
|---|---|---|
| Same file delivered twice | two activities or double effort rows | content-hash id; keyed effort rows |
| Worker dies mid-processing | half the efforts written | state flips last; re-run overwrites |
| Noisy altitude | thousands of metres of fake climb | threshold; barometer data when the file has it |
| GPS jitter at a standstill | "moving time" runs on | speed floor; ignore intervals with tiny displacement |
| Tunnel or dropped signal | long gap, then a jump | a gap rule: do not count or interpolate across long gaps |
| Cell with thousands of segment starts | candidate lists explode | finer grid for dense cells |
| Adversarial track for simplification | quadratic time | cap points; time-box |
| Webhook receiver slow | retries after two seconds | acknowledge first, process asynchronously |
| Algorithm changes | old summaries disagree with new | keep the raw file; recompute in the background |

---

## 10. What Real Companies Did

The only Strava material read for this lesson is its public developer documentation (the API reference and the upload, webhook and rate-limit pages), summarised in section 8; those pages describe public behaviour. Strava's engineering blog is hosted on Medium, which returned HTTP 403 to a plain fetch, so nothing is said here about how Strava stores tracks, matches segments or ranks leaderboards. Google's documentation of the encoded polyline format, which the lesson implements and checks, was read in full. The rest of the lesson (the matcher, the store, the pipeline model) is the general design built and tested here; it is not attributed to any company.

---

## 11. Pitfalls Checklist

1. Summing altitude deltas without a noise threshold.
2. Using distance to the infinite line in Douglas-Peucker and calling the result "within eps of the path".
3. Recursion in Douglas-Peucker on thousands of points.
4. A grid cell narrower than the matching tolerance, so starts across a border are missed.
5. Matching only start and end, which accepts shortcuts and finishes a loop in one sample.
6. Appending effort rows on every attempt instead of keying them.
7. Marking the activity done before its effort rows are written.
8. Calling a hash dedupe a solution to "uploaded from two devices".
9. Treating elapsed time and moving time as the same number.
10. Quoting a company's segment algorithm you have not read.

---

## Drills

1. Why is the polyline format "lossy", and how large is the error?
2. A flat track with 1 Hz altitude noise of 2 m either way reports 2,401 m of climb with the naive sum. What does the threshold change, and what real climbs does it hide?
3. Why must the grid cell be at least as wide as the tolerance? What goes wrong with a 10 m cell and a 50 m tolerance?
4. What does Douglas-Peucker guarantee about dropped points, and why does the distance function matter for that guarantee?
5. A worker dies after writing two of three effort rows. What state is the activity in, and what does the retry do?
6. The activity id hashes the athlete and the track. Name one real upload that this does not deduplicate.
7. Estimate the work per activity for 3,600 points against 20 million segments with and without the grid, and name the assumption that could make the grid answer wrong.
8. Which parts of Strava's public documentation does the lesson use, and which parts of how Strava works does it leave unstated?

---

## Homework

1. Add interpolation of the crossing time to `match_efforts`: linearly interpolate the time at which the track first comes within `tol` of the start and of the end. Write a test where the sampling is 10 seconds and show the old and new times.
2. Implement a gap rule for `moving_time`: intervals longer than 30 seconds are never moving. Test it against a pause.
3. Write a brute-force near-duplicate activity detector (same athlete, overlapping window, start within 100 m) and test it on a watch and a phone recording of one synthetic route.
4. Replace the grid with sorting by x and a sweep; compare the candidate counts on a dense cluster of 5,000 starts.
5. Measure `rdp` on zig-zag tracks of 500, 1,000 and 2,000 points; confirm the quadratic growth.

---

## Sources

All read on 27 November 2026.

- Google, *Encoded Polyline Algorithm Format*, developers.google.com/maps/documentation/utilities/polylinealgorithm (read in full). Source for the encoding steps, the 5-decimal precision, the 63 offset, the worked single-value example and the three-point example.
- Strava, *API reference*, developers.strava.com/docs/reference/ (read in part: activity objects with `moving_time`, `elapsed_time`, `polyline` and `summary_polyline`; streams; segments; the explore-segments endpoint, which returns the top 10 and is limited to an extended-access tier).
- Strava, *Uploading to Strava*, developers.strava.com/docs/uploads/ (read in part: the opening description, supported file types, duplicate errors and the elevation note). Source for asynchronous processing and the under-2-second mean.
- Strava, *Webhook Events API*, developers.strava.com/docs/webhooks/ (read in full). Source for the two-second acknowledgement, three attempts and the event fields.
- Strava, *Rate Limits*, developers.strava.com/docs/rate-limits/ (read in full). Source for the default limits and the 429 response.
- Wikipedia, *Ramer-Douglas-Peucker algorithm*, en.wikipedia.org/wiki/Ramer%E2%80%93Douglas%E2%80%93Peucker_algorithm (read as extracted text; a secondary source, used for the algorithm statement only).
- Not read: Strava's engineering blog (HTTP 403), the Garmin FIT protocol page (returned almost no text), the original Douglas and Peucker papers.

## Further reading (not consulted)

- Douglas and Peucker (1973), *Algorithms for the reduction of the number of points required to represent a digitized line or its caricature*.
- The Garmin FIT SDK and the GPX 1.1 schema.
- Strava's engineering blog on segment matching and heatmaps.

*Last reviewed: 27 November 2026.*
