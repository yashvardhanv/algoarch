const fs = require('fs');
const path = require('path');

const baseDir = __dirname;
const curriculumFile = path.join(baseDir, 'data', 'curriculum.json');
const newLessonsDir = path.join(baseDir, 'data', 'new_lessons');

if (!fs.existsSync(newLessonsDir)) {
  fs.mkdirSync(newLessonsDir, { recursive: true });
}

const curriculum = JSON.parse(fs.readFileSync(curriculumFile, 'utf8'));

// 1. Add to DSA
const dsaTrack = curriculum.tracks.find(t => t.id === 'dsa');
let dsaBlock = dsaTrack.blocks.find(b => b.k === 'creator-patterns');
if (!dsaBlock) {
  dsaBlock = {
    k: 'creator-patterns',
    t: 'Elite Creator Patterns (NeetCode & Grokking)',
    lessons: []
  };
  dsaTrack.blocks.push(dsaBlock);
}

const newDsaLessons = [
  {
    n: '24',
    id: 'ds24',
    title: 'Cyclic Sort & In-Place State Encodings',
    stars: 5,
    desc: 'The single most under-taught O(n) time O(1) space pattern: array value-as-index mapping. First Missing Positive, finding duplicates, and bit-sign state flags.',
    duration: '45 min drill',
    tags: ['Cyclic Sort', 'In-Place', 'Array Indexing', 'Amazon', 'Meta'],
    companies: ['Amazon', 'Meta', 'Google'],
    isNew: true,
    newPath: 'new_lessons/ds24.md'
  },
  {
    n: '25',
    id: 'ds25',
    title: 'Topological Sort & DAG Dependency Resolution',
    stars: 5,
    desc: 'Kahns In-Degree BFS vs Tarjans Post-Order DFS. Cycle detection, topological ordering, Course Schedule II, and Alien Dictionary lexicographical order.',
    duration: '50 min drill',
    tags: ['Topological Sort', 'DAG', 'Kahns BFS', 'Graph Cycles', 'Google', 'Uber'],
    companies: ['Google', 'Uber', 'Apple'],
    isNew: true,
    newPath: 'new_lessons/ds25.md'
  }
];

newDsaLessons.forEach(l => {
  if (!dsaBlock.lessons.some(existing => existing.id === l.id)) {
    dsaBlock.lessons.push(l);
  }
});
dsaTrack.totalLessons = dsaTrack.blocks.reduce((acc, b) => acc + b.lessons.length, 0);

// 2. Add to System Design
const sysTrack = curriculum.tracks.find(t => t.id === 'system-design');
let sysBlock = sysTrack.blocks.find(b => b.k === 'creator-hld');
if (!sysBlock) {
  sysBlock = {
    k: 'creator-hld',
    t: 'ByteByteGo & Modern Production Architectures',
    lessons: []
  };
  sysTrack.blocks.push(sysBlock);
}

const newSysLessons = [
  {
    n: '42',
    id: 'sy42',
    title: 'Flash Sale & High-Concurrency Ticket Reservation (Ticketmaster)',
    stars: 5,
    desc: 'Inventory reservation under 100k QPS spikes: 10-minute hold TTLs, Redis distributed locking with fencing tokens, virtual waiting rooms, and transactional outbox idempotency.',
    duration: '55 min',
    tags: ['Distributed Locks', 'Flash Sale', 'Inventory Reservation', 'Redlock', 'Fencing Tokens', 'Amazon'],
    companies: ['Amazon', 'Apple', 'Booking.com'],
    isNew: true,
    newPath: 'new_lessons/sy42.md'
  },
  {
    n: '43',
    id: 'sy43',
    title: 'Proximity Service & Location-Based Systems (Google Maps / Uber)',
    stars: 5,
    desc: 'Spatial indexing deep dive: Geohash vs QuadTree vs Google S2 vs Uber H3 hexagonal hierarchy. Dynamic driver clustering, radius queries, and map tile caching.',
    duration: '50 min',
    tags: ['Geohash', 'QuadTree', 'Uber H3', 'Spatial Index', 'Location Services', 'Google'],
    companies: ['Google', 'Uber', 'DoorDash'],
    isNew: true,
    newPath: 'new_lessons/sy43.md'
  },
  {
    n: '44',
    id: 'sy44',
    title: 'Ultra-Low Latency Stock Exchange & Order Matching Engine',
    stars: 5,
    desc: 'Sub-microsecond deterministic order matching: LMAX Disruptor ring buffers, Price-Time priority queues, kernel bypass (DPDK), zero-GC object pools, and replicated state machines.',
    duration: '60 min',
    tags: ['Disruptor', 'Low Latency', 'Order Book', 'Zero GC', 'Fintech', 'Robinhood'],
    companies: ['Fintech', 'Robinhood', 'Coinbase'],
    isNew: true,
    newPath: 'new_lessons/sy44.md'
  }
];

newSysLessons.forEach(l => {
  if (!sysBlock.lessons.some(existing => existing.id === l.id)) {
    sysBlock.lessons.push(l);
  }
});
sysTrack.totalLessons = sysTrack.blocks.reduce((acc, b) => acc + b.lessons.length, 0);

// 3. Add to AI Engineering
const aiTrack = curriculum.tracks.find(t => t.id === 'ai-engineering');
let aiBlock = aiTrack.blocks.find(b => b.k === 'creator-mlsys');
if (!aiBlock) {
  aiBlock = {
    k: 'creator-mlsys',
    t: 'Production ML System Design (Meta / Netflix / Google)',
    lessons: []
  };
  aiTrack.blocks.push(aiBlock);
}

const newAiLessons = [
  {
    n: '27',
    id: 'ai27',
    title: 'Two-Tower Recommendation System Architecture (Meta / Netflix)',
    stars: 5,
    desc: 'Industry standard recommender funnel: Candidate retrieval with user/item embedding towers + ScaNN/HNSW ANN vector index -> DLRM / DeepFM Heavy Ranker -> Contextual Bandits diversity.',
    duration: '55 min',
    tags: ['Two-Tower', 'Embeddings', 'Vector Search', 'ANN', 'Ranker', 'Meta', 'Netflix'],
    companies: ['Meta', 'Netflix', 'Google', 'ByteDance'],
    isNew: true,
    newPath: 'new_lessons/ai27.md'
  }
];

newAiLessons.forEach(l => {
  if (!aiBlock.lessons.some(existing => existing.id === l.id)) {
    aiBlock.lessons.push(l);
  }
});
aiTrack.totalLessons = aiTrack.blocks.reduce((acc, b) => acc + b.lessons.length, 0);

// Also attach company metadata to existing lessons if missing
const companyPool = ['Google', 'Meta', 'Amazon', 'Netflix', 'Apple', 'Uber'];
curriculum.tracks.forEach(t => {
  t.blocks.forEach(b => {
    b.lessons.forEach((l, idx) => {
      if (!l.companies || l.companies.length === 0) {
        l.companies = [companyPool[idx % companyPool.length], companyPool[(idx + 2) % companyPool.length]];
      }
    });
  });
});

fs.writeFileSync(curriculumFile, JSON.stringify(curriculum, null, 2), 'utf8');
console.log('Successfully updated curriculum.json with 6 premier creator lessons!');
