const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, 'data', 'new_lessons');
if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

// 1. ds24.md - Cyclic Sort
const ds24 = `# Cyclic Sort & In-Place State Encodings

> **Target Companies**: Amazon, Meta, Google, Microsoft (L4/L5 SWE)  
> **Key Frequency**: Highest yield pattern for "Find missing/duplicate numbers in [1..n] in O(n) time and O(1) space"

---

## 1. The Core Mental Model

The standard interview trap is reaching for a hash set or sorting:
- **Hash Set**: $O(n)$ time, but consumes $O(n)$ extra memory. Disqualified if the prompt demands $O(1)$ auxiliary space.
- **Comparison Sort**: $O(n \\log n)$ time, violates the $O(n)$ runtime constraint.

### The Invariant
When an array contains $n$ numbers within the range $[1..n]$ (or $[0..n]$), **each value itself is an implicit index**.
A correctly placed element $v$ must sit at position $v - 1$.
The Cyclic Sort pattern executes a cycle of in-place swaps until every number is either:
1. Sitting at its designated index (\`nums[i] == nums[nums[i] - 1]\`), or
2. Out-of-bounds (e.g. negative or $> n$ in *First Missing Positive*).

\`\`\`
Index:  [ 0,  1,  2,  3 ]
Value:  [ 3,  1,  4,  2 ]  --> Target: [ 1,  2,  3,  4 ]
\`\`\`

---

## 2. Invariants & Step-by-Step Cycle Walkthrough

\`\`\`mermaid
flowchart TD
    A["Read element at index i: x = nums[i]"] --> B{"Is x in range [1..n] AND nums[i] != nums[x-1]?"}
    B -- Yes --> C["Swap nums[i] with nums[x-1]"]
    C --> A
    B -- No --> D["i = i + 1 (advance pointer)"]
\`\`\`

### Why is this strictly $O(n)$ time?
At each iteration:
- Either the index $i$ increments by $1$, OR
- An element is swapped into its permanent home.
Since each of the $n$ elements can be placed into its correct home at most **once**, the maximum number of swaps across the entire loop is $n - 1$.
$$\\text{Total Operations} \\le n + (n - 1) = 2n - 1 = O(n)$$

---

## 3. Production Python Blueprint: First Missing Positive (LeetCode 41 Hard)

\`\`\`python
from typing import List

def first_missing_positive(nums: List[int]) -> int:
    \"\"\"
    Finds the smallest positive integer not in nums in O(n) time and O(1) auxiliary space.
    \"\"\"
    n = len(nums)
    i = 0
    while i < n:
        correct_idx = nums[i] - 1
        # Place nums[i] at correct_idx if in range [1, n] and not already there
        if 0 <= correct_idx < n and nums[i] != nums[correct_idx]:
            nums[i], nums[correct_idx] = nums[correct_idx], nums[i]
        else:
            i += 1

    # Second pass: first index where nums[i] != i + 1 is the missing positive
    for i in range(n):
        if nums[i] != i + 1:
            return i + 1

    return n + 1

# Verification test assertions
assert first_missing_positive([3, 4, -1, 1]) == 2
assert first_missing_positive([1, 2, 0]) == 3
assert first_missing_positive([7, 8, 9, 11, 12]) == 1
\`\`\`

---

## 4. Alternate In-Place Encoding: The Negative-Sign Flag
When an array contains integers in range $[1..n]$ and you cannot move elements:
Use the **sign of the value at index $(|val| - 1)$ as a 1-bit seen boolean**:
- To mark seen: \`nums[abs(x) - 1] = -abs(nums[abs(x) - 1])\`
- If already negative before marking $\\to$ duplicate found!

---

## 5. Mock Interview Traps & Diagnostics
1. **Infinite Loop Pitfall**: Doing \`nums[i] != i + 1\` instead of \`nums[i] != nums[correct_idx]\`. If duplicate numbers exist (e.g. \`[2, 2]\`), checking index causes an infinite loop!
2. **0-indexed vs 1-indexed shift**: Always map values $1..n$ to indices $0..n-1$ with \`val - 1\`.
`;

// 2. ds25.md - Topological Sort
const ds25 = `# Topological Sort & DAG Dependency Resolution

> **Target Companies**: Google, Uber, Apple, Airbnb (L5 Senior SWE)  
> **Key Frequency**: Course Schedule, Build Systems, Package Resolvers, Lexicographical Dictionaries

---

## 1. The Core Mental Model

A **Topological Ordering** of a Directed Acyclic Graph (DAG) is a linear sequence of vertices such that for every directed edge $u \\to v$, $u$ appears before $v$.

### Two Core Algorithms Compared
| Algorithm | Mechanism | Time Complexity | Cycle Detection Mechanism |
| :--- | :--- | :--- | :--- |
| **Kahn's Algorithm (BFS)** | Track In-Degree of each node | $O(V + E)$ | Count of processed nodes $< V$ |
| **Tarjan's Post-Order (DFS)** | 3-Color State (White/Gray/Black) | $O(V + E)$ | Reaching a node currently in State Gray (Visiting) |

---

## 2. Invariants & Kahn's In-Degree Walkthrough

\`\`\`mermaid
flowchart LR
    CS1["CS 101 (In-degree 0)"] --> CS2["CS 201 (In-degree 1)"]
    MATH1["Math 101 (In-degree 0)"] --> CS2
    CS2 --> CS3["CS 301 (In-degree 1)"]
    CS2 --> CS4["CS 302 (In-degree 1)"]
\`\`\`

1. Initialize \`in_degree = [0] * numCourses\`.
2. Push all nodes with \`in_degree == 0\` into a queue.
3. Pop from queue, append to result order, decrement in-degree for all outgoing neighbors.
4. If neighbor's in-degree drops to 0, push into queue.

---

## 3. Production Python Blueprint: Course Schedule II (LeetCode 210)

\`\`\`python
from collections import deque, defaultdict
from typing import List

def find_order(num_courses: int, prerequisites: List[List[int]]) -> List[int]:
    \"\"\"
    Returns a valid topological ordering or empty list if a dependency cycle exists.
    \"\"\"
    adj = defaultdict(list)
    in_degree = [0] * num_courses

    for dest, src in prerequisites:
        adj[src].append(dest)
        in_degree[dest] += 1

    queue = deque([i for i in range(num_courses) if in_degree[i] == 0])
    order = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in adj[node]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    return order if len(order) == num_courses else []

# Verification
assert find_order(4, [[1,0],[2,0],[3,1],[3,2]]) in ([0,1,2,3], [0,2,1,3])
assert find_order(2, [[1,0],[0,1]]) == [] # Cycle
\`\`\`

---

## 4. Advanced Variant: Alien Dictionary (Lexicographical Order)
When given a sorted list of words in an alien language:
1. Compare adjacent words \`words[i]\` and \`words[i+1]\`.
2. Find the first differing character: \`w1[k] -> w2[k]\` defines a directed edge.
3. Validate prefix invariant: If \`w1\` is longer than \`w2\` and starts with \`w2\`, order is invalid (e.g. \`[\"abc\", \"ab\"]\`).
4. Run Kahn's algorithm or Tarjan's DFS with cycle check.
`;

// 3. sy42.md - Flash Sale & Ticket Reservation
const sy42 = `# Flash Sale & High-Concurrency Ticket Reservation (Ticketmaster)

> **Target Companies**: Amazon, Apple, Booking.com, Ticketmaster  
> **Scale**: 100,000 QPS, 50,000 concurrent buyers competing for 5,000 seats

---

## 1. The Core Architectural Challenge

When popular concert tickets or Apple devices drop, thousands of requests arrive in the first 500 milliseconds.
- **RDBMS row locking (\`SELECT ... FOR UPDATE\`)**: Deadlocks and exhausts the connection pool under $>2,000$ concurrent writes.
- **Naive NoSQL writes**: Incur double-booking and inventory overshoot under distributed partition failures.

---

## 2. End-to-End System Architecture

\`\`\`mermaid
flowchart TD
    Client["User Client"] --> Cloudflare["Cloudflare Waiting Room (Token Bucket)"]
    Cloudflare --> APIGW["API Gateway & Auth"]
    APIGW --> RedisCluster["Redis Cluster (Lua Inventory Script + TTL)"]
    RedisCluster -- "Reserved (10-min TTL)" --> Kafka["Kafka Reservation Topic"]
    Kafka --> OrderSvc["Order Processing Service"]
    OrderSvc --> DB[("PostgreSQL Master (ACID Finalize)")]
    OrderSvc --> Payment["Stripe / Payment Gateway"]
\`\`\`

---

## 3. High-Concurrency Reservation Invariants

### 1. Atomic Lua Script in Redis
Redis executes Lua scripts atomically in a single thread, eliminating multi-process race conditions entirely.

\`\`\`lua
-- KEYS[1]: event_inventory_key (e.g. 'inventory:concert_101:zone_A')
-- ARGV[1]: requested_quantity (e.g. 2)
-- ARGV[2]: user_id
-- ARGV[3]: hold_ttl_seconds (e.g. 600)

local current_stock = tonumber(redis.call('get', KEYS[1]) or '0')
local qty = tonumber(ARGV[1])

if current_stock >= qty then
    redis.call('decrby', KEYS[1], qty)
    local reservation_key = 'hold:' .. KEYS[1] .. ':' .. ARGV[2]
    redis.call('setex', reservation_key, tonumber(ARGV[3]), qty)
    return 1 -- Success
else
    return 0 -- Sold out / insufficient inventory
end
\`\`\`

### 2. The 10-Minute Reservation Hold & TTL Auto-Reclamation
If the user abandons checkout:
- Key in Redis expires automatically via \`setex\`.
- A Redis Keyspace Notification or periodic reconciliation worker refunds uncompleted seats back to \`inventory:concert_101:zone_A\`.

---

## 4. Preventing Double-Spending: Fencing Tokens & Distributed Locks

When using distributed locks (Redlock / ZooKeeper):
\`\`\`
Client 1 acquires Lock -> Pauses due to GC/Network hiccup -> Lock expires
Client 2 acquires Lock -> Writes to DB
Client 1 wakes up -> Writes stale data to DB (Corrupting state!)
\`\`\`
**Fix**: Append a strictly monotonic **Fencing Token** to every lock acquisition.
PostgreSQL checks: \`UPDATE inventory SET count = ... WHERE token > last_applied_token\`.
`;

// 4. sy43.md - Proximity Service
const sy43 = `# Proximity Service & Location-Based Systems (Google Maps / Uber)

> **Target Companies**: Google, Uber, Yelp, DoorDash (Staff L5/L6)  
> **Core Metric**: Sub-20ms radius queries across 200,000,000 venues & drivers

---

## 1. Comparing Spatial Indexing Approaches

\`\`\`mermaid
flowchart LR
    A["Raw Lat/Lon SQL"] --> B["Geohash (Base32 Grid)"]
    B --> C["QuadTree (Hierarchical Tree)"]
    C --> D["Uber H3 (Hexagonal Global Grid)"]
\`\`\`

| Index Type | Structure | In-Memory / Disk | Nearest Neighbors Handling |
| :--- | :--- | :--- | :--- |
| **Geohash** | Interleaves lat/lon bits into Base32 string | Key-Value Store (Redis / DynamoDB) | Border boundary issues (requires checking 8 adjacent neighbors) |
| **QuadTree** | 4-way recursive spatial tree | In-Memory (Node.js / Go microservice) | Dynamic re-balancing required under population density |
| **Uber H3** | Global discrete hexagonal grid system | Bitwise integer representations | Equal distance to all 6 adjacent neighbors (ideal for rideshare) |

---

## 2. Geohash Index Architecture

A Geohash breaks the earth into binary subdivided rectangles:
- Precision 5: $\\approx 4.9 \\text{ km} \\times 4.9 \\text{ km}$
- Precision 6: $\\approx 1.2 \\text{ km} \\times 0.61 \\text{ km}$ (Ideal neighborhood scale)

### Database Storage Schema (Redis / DynamoDB)
\`\`\`
Partition Key: geohash_prefix_4 (e.g. '9q8y')
Sort Key:      geohash_prefix_6 (e.g. '9q8yzh')
Attributes:    restaurant_id, name, lat, lon, rating
\`\`\`

Querying 3 km radius around user:
1. Calculate user's 6-character geohash.
2. Query user's geohash + 8 surrounding neighbor hashes.
3. Compute exact Haversine distance in-memory to filter edge discrepancies.
`;

// 5. sy44.md - Ultra-Low Latency Stock Exchange
const sy44 = `# Ultra-Low Latency Stock Exchange & Order Matching Engine

> **Target Companies**: Robinhood, Coinbase, Citadel, Jump Trading (L5/L6 Low-Latency SWE)  
> **Key Metric**: Sub-microsecond (99.9th percentile $< 5 \\mu s$) deterministic matching

---

## 1. Architecture of a Modern Matching Engine

Traditional enterprise architectures (microservices, JSON HTTP, distributed transactions) are disqualified by orders of magnitude:
- Network roundtrip over HTTP: $5,000 \\mu s$
- Linux kernel context switch: $1.5 \\mu s$
- Memory allocation & Java/Node GC pause: $10,000 \\mu s$ to $100,000 \\mu s$

\`\`\`mermaid
flowchart LR
    ClientOrder["Fix Protocol / WebSocket"] --> Gateway["Kernel Bypass Gateway (DPDK)"]
    Gateway --> Sequencer["Deterministic Sequencer (Raft / Aeron)"]
    Sequencer --> RingBuffer["LMAX Disruptor Lock-Free Ring Buffer"]
    RingBuffer --> MatchEngine["In-Memory Single-Threaded Matcher"]
    MatchEngine --> Journal["Zero-Copy Binary Journal (NVMe SSD)"]
\`\`\`

---

## 2. The LMAX Disruptor Pattern
Instead of standard thread-safe queues with lock contention:
- A single pre-allocated circular ring buffer (power of 2 size).
- Sequence numbers managed with atomic CAS (\`AtomicLong\`) operations.
- Zero CPU cache-line bouncing (cache line padding around sequence counters).

---

## 3. Order Book Data Structure: Price-Time Priority
- **Price Levels**: Balanced Binary Search Tree (Red-Black) or B-Tree of limit prices.
- **At Each Price**: Doubly Linked List of Orders (FIFO queue for time priority).
- **Lookup Map**: Hash map of \`order_id -> OrderNode\` for $O(1)$ cancelation and amendment.
`;

// 6. ai27.md - Two-Tower Recommendation System
const ai27 = `# Two-Tower Recommendation System Architecture (Meta / Netflix)

> **Target Companies**: Meta, Netflix, Google, ByteDance (Senior Machine Learning Engineer)  
> **Scale**: 1 Billion users, 100 Million candidate items, $<50$ms end-to-end response budget

---

## 1. The Multi-Stage Recommendation Funnel

\`\`\`mermaid
flowchart TD
    Pool["100M+ Candidate Corpus"] --> Retrieval["Stage 1: Candidate Retrieval (Two-Tower ANN) -> Top 1,000"]
    Retrieval --> Ranking["Stage 2: Heavy Ranking (DLRM / DeepFM) -> Top 100"]
    Ranking --> Diversity["Stage 3: Reranking & Diversity (Contextual Bandits) -> Final 20"]
\`\`\`

---

## 2. Two-Tower Architecture Breakdown

- **User Tower**: Computes a dense vector representation $u \\in \\mathbb{R}^d$ from user history, demographics, and real-time context (time of day, device).
- **Item Tower**: Computes a dense vector representation $v \\in \\mathbb{R}^d$ from item metadata, embeddings, and category.
- **Matching Score**: Dot product $\\langle u, v \\rangle$ or cosine similarity.

### Real-Time Vector Indexing
Item embeddings are computed offline and indexed in an approximate nearest neighbor (ANN) vector database (FAISS, Google ScaNN, or HNSW).
At query time:
1. User passes through user tower in $\\approx 4$ms.
2. Vector query against ScaNN retrieves top 1,000 candidates in $\\approx 8$ms.
3. Top 1,000 fed into Deep & Cross / DLRM model for pointwise CTR prediction.
`;

fs.writeFileSync(path.join(dir, 'ds24.md'), ds24, 'utf8');
fs.writeFileSync(path.join(dir, 'ds25.md'), ds25, 'utf8');
fs.writeFileSync(path.join(dir, 'sy42.md'), sy42, 'utf8');
fs.writeFileSync(path.join(dir, 'sy43.md'), sy43, 'utf8');
fs.writeFileSync(path.join(dir, 'sy44.md'), sy44, 'utf8');
fs.writeFileSync(path.join(dir, 'ai27.md'), ai27, 'utf8');

console.log('Successfully written all 6 detailed lesson markdown guides!');
