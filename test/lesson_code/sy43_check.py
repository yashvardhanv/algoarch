"""Runs the python code blocks from data/new_lessons/sy43.md: geohash encode/decode against an independent
integer-scaling encoder, neighbours against bounding-box arithmetic, and radius and nearest-k search against
brute-force distance sorting, with point sets placed on the antimeridian, the poles, the equator and the prime
meridian. Also shows the naive searches the lesson warns about failing, and checks the figures the lesson quotes."""
import re, sys, random, math
src = open(sys.argv[1], encoding='utf-8').read()
blocks = re.findall(r"```python\n(.*?)```", src, re.S)
ns = {}
for b in blocks:
    exec(b, ns)
encode, decode, to_index, from_index, neighbours = ns['encode'], ns['decode'], ns['to_index'], ns['from_index'], ns['neighbours']
haversine, cover, GeoIndex, bits, R_KM = ns['haversine'], ns['cover'], ns['GeoIndex'], ns['bits'], ns['R_KM']
random.seed(43)
B32 = '0123456789bcdefghjkmnpqrstuvwxyz'

def ref_encode(lat, lon, p):
    """Independent: scale to integers, interleave longitude first, slice into 5-bit groups."""
    lb, ab = (5 * p + 1) // 2, 5 * p // 2
    col = min(int((lon + 180.0) / 360.0 * 2 ** lb), 2 ** lb - 1)
    row = min(int((lat + 90.0) / 180.0 * 2 ** ab), 2 ** ab - 1)
    out, ci, ri = [], lb - 1, ab - 1
    bitstr = ''
    for i in range(5 * p):
        if i % 2 == 0:
            bitstr += str(col >> ci & 1); ci -= 1
        else:
            bitstr += str(row >> ri & 1); ri -= 1
    return ''.join(B32[int(bitstr[i:i + 5], 2)] for i in range(0, 5 * p, 5))

def rand_point():
    return math.degrees(math.asin(2 * random.random() - 1)), random.uniform(-180, 180)

# ---- encode / decode
for _ in range(20000):
    lat, lon = rand_point()
    if random.random() < 0.1:
        lat, lon = random.choice([0.0, 90.0, -90.0, 45.0]), random.choice([0.0, 180.0, -180.0, 90.0])
    p = random.randint(1, 12)
    g = encode(lat, lon, p)
    assert g == ref_encode(lat, lon, p), (lat, lon, p, g, ref_encode(lat, lon, p))
    lo, hi, wlo, whi = decode(g)
    assert lo <= lat <= hi and wlo <= lon <= whi
    assert encode((lo + hi) / 2, (wlo + whi) / 2, p) == g
    assert from_index(*to_index(g), p) == g
    assert encode(lat, lon, 12).startswith(g)                 # coarser cell = prefix of the finer one
assert bits(6) == (15, 15) and bits(5) == (13, 12) and bits(7) == (18, 17)

# ---- figures the lesson quotes
SF = (37.7749, -122.4194)
assert encode(*SF, 6) == '9q8yyk'
lo, hi, wlo, whi = decode('9q8yyk')
kpd = 2 * math.pi * R_KM / 360
assert round((hi - lo) * kpd, 2) == 0.61 and round((whi - wlo) * kpd * math.cos(math.radians(SF[0])), 2) == 0.97
assert encode(0.0001, 0.0001, 5) == 's0000' and encode(-0.0001, -0.0001, 5) == '7zzzz'
assert round(haversine(0.0001, 0.0001, -0.0001, -0.0001) * 1000) == 31
assert len(cover(*SF, 0.5, 6)) == 6 and len(cover(*SF, 0.5, 7)) == 80
assert cover(*SF, 0.5, 7, limit=9) is None and cover(*SF, 0.5, 6, limit=9) is not None   # within() picks 6
assert round(math.cos(math.radians(80)), 3) == 0.174                                      # drill 4

# ---- haversine against an independent vector formula
for _ in range(5000):
    a, b = rand_point(), rand_point()
    def vec(lat, lon):
        la, lo_ = math.radians(lat), math.radians(lon)
        return math.cos(la) * math.cos(lo_), math.cos(la) * math.sin(lo_), math.sin(la)
    u, v = vec(*a), vec(*b)
    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    ang = math.atan2(math.sqrt(sum(c * c for c in cross)), sum(x * y for x, y in zip(u, v)))
    assert abs(haversine(*a, *b) - R_KM * ang) < 1e-6 * R_KM

# ---- neighbours against bounding-box arithmetic
for _ in range(5000):
    lat, lon = rand_point()
    if random.random() < 0.3:
        lat = random.choice([89.9999, -89.9999, lat])
        lon = random.choice([179.9999, -179.9999, lon])
    p = random.randint(1, 9)
    g = encode(lat, lon, p)
    lo, hi, wlo, whi = decode(g)
    h, w = hi - lo, whi - wlo
    want = set()
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if not (dr or dc):
                continue
            clat = (lo + hi) / 2 + dr * h
            clon = (wlo + whi) / 2 + dc * w
            if not -90 < clat < 90:
                continue
            clon = (clon + 180) % 360 - 180
            want.add(encode(clat, clon, p))
    got = neighbours(g)
    assert set(got) == want and len(got) == len(want), (g, sorted(got), sorted(want))

# ---- search vs brute force
def brute(points, lat, lon, r=None, k=None):
    d = sorted((haversine(lat, lon, *pt), pid) for pid, pt in points.items())
    if r is not None:
        d = [x for x in d if x[0] <= r]
    return d if k is None else d[:k]

HOT = [(0.0, 0.0), (0.0, 180.0), (0.0, -180.0), (89.99, 0.0), (-89.99, 45.0), (90.0, 0.0), (-90.0, 0.0),
       SF, (-17.7, 178.0), (65.8, -168.9)]          # equator/prime meridian, antimeridian, poles, Fiji, Bering
def cluster_point(c, spread):
    lat = max(-90.0, min(90.0, c[0] + random.gauss(0, spread)))
    lon = (c[1] + random.gauss(0, spread) + 180) % 360 - 180
    return lat, lon

searches = 0
for trial in range(120):
    pts = {}
    for i in range(random.randint(1, 250)):
        if random.random() < 0.5:
            pts['p%d' % i] = rand_point()
        else:
            pts['p%d' % i] = cluster_point(random.choice(HOT), random.choice([0.0005, 0.01, 0.3, 3]))
    idx = GeoIndex(pts)
    for _ in range(25):
        q = rand_point() if random.random() < 0.3 else cluster_point(random.choice(HOT), random.choice([0.0005, 0.01, 0.5]))
        r = random.choice([0.01, 0.1, 0.5, 2, 25, 300, 3000, 25000])
        assert idx.within(*q, r) == brute(pts, *q, r=r), (q, r)
        k = random.randint(1, 12)
        assert idx.nearest(*q, k, r0_km=random.choice([0.01, 1.0])) == brute(pts, *q, k=k), (q, k)
        searches += 2

# ---- the naive searches the lesson warns about
def own_cell_only(idx, lat, lon, r, p):
    return sorted((haversine(lat, lon, *idx.points[x]), x) for x in idx._scan(encode(lat, lon, p))
                  if haversine(lat, lon, *idx.points[x]) <= r)
def three_by_three(idx, lat, lon, r, p, wrap=True):
    g = encode(lat, lon, p)
    cells = [g] + neighbours(g)
    if not wrap:
        lb, _ = bits(p)
        col, _ = to_index(g)
        cells = [c for c in cells if abs(to_index(c)[0] - col) <= 1]          # drop wrapped columns
    out = []
    for c in cells:
        for x in idx._scan(c):
            d = haversine(lat, lon, *idx.points[x])
            if d <= r:
                out.append((d, x))
    return sorted(out)

edge = GeoIndex({'a': (0.0001, 0.0001)})
assert own_cell_only(edge, -0.0001, -0.0001, 1.0, 6) == [] and len(edge.within(-0.0001, -0.0001, 1.0)) == 1
date_line = GeoIndex({'a': (10.0, 179.9999)})
assert three_by_three(date_line, 10.0, -179.9999, 1.0, 5, wrap=False) == []
assert len(three_by_three(date_line, 10.0, -179.9999, 1.0, 5)) == 1 == len(date_line.within(10.0, -179.9999, 1.0))
pole = GeoIndex({'a': (89.999, 180.0)})
assert haversine(89.999, 0.0, 89.999, 180.0) < 1.0
assert three_by_three(pole, 89.999, 0.0, 1.0, 5) == []                 # 3 x 3 misses the point behind the pole
assert len(pole.within(89.999, 0.0, 1.0)) == 1

print('sy43 code checks passed (%d searches against brute force)' % searches)
