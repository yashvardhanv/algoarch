// Controllable stand-in for the Gemini streaming API. The app's real server + real mentor UI
// talk to this; chunks are released on demand so frame capture is deterministic.
const http = require('http');
const ANSWERS = [
[
`**A transformer in one idea:** instead of reading a sentence one word at a time, every token looks at **every other token at once** and decides what matters. That mechanism is called **self-attention**.\n\n`,
`### The moving parts\n`,
`1. **Embeddings + positions**: tokens become vectors, and positional encodings tell the model *where* each token sits.\n`,
`2. **Self-attention**: each token makes a query (Q), a key (K) and a value (V). Scores are Q·Kᵀ/√d, softmax turns them into weights, and the output is a weighted sum of V.\n`,
`3. **Feed-forward + residuals**: stack that block N times.\n\n`,
`### A practical example\n`,
"```python\nimport numpy as np\n\ndef attention(Q, K, V):\n    scores = Q @ K.T / np.sqrt(K.shape[-1])\n    w = np.exp(scores - scores.max(-1, keepdims=True))\n    w /= w.sum(-1, keepdims=True)\n    return w @ V\n```\n\n",
`In *"the **cat** sat because **it** was tired"*, attention lets **it** put most of its weight on **cat**, which is how the model resolves what the pronoun refers to.`
],
[
`**Simpler version:** imagine a group chat where every word can read all the other messages before it replies.\n\n`,
`- Each word asks, *"who here is relevant to me?"*\n`,
`- It gives the relevant words a higher score and mostly ignores the rest.\n`,
`- Then it blends what it learned from them into its own meaning.\n\n`,
`That's attention: **look at everything, focus on what matters.** A transformer just repeats that many times in a row.`
]
];
// tokenise each answer into word-sized pieces so the UI streams like a real model
for (let i = 0; i < ANSWERS.length; i++) ANSWERS[i] = ANSWERS[i].join('').match(/\S+\s*|\s+/g);
let turn = 0, pending = null;
const frame = (text, finish) => 'data: ' + JSON.stringify({ candidates: [{ content: { parts: [{ text }] }, ...(finish ? { finishReason: 'STOP' } : {}) }] }) + '\r\n\r\n';
http.createServer((req, res) => {
  if (req.method === 'POST') {
    let b = ''; req.on('data', c => b += c); req.on('end', () => {
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      pending = { res, chunks: ANSWERS[Math.min(turn++, ANSWERS.length - 1)].slice() , sent: 0 };
      console.log('stream opened, turn', turn);
    });
  } else if (req.url.startsWith('/emit')) {
    const n = Number(new URL(req.url, 'http://x').searchParams.get('n') || 1);
    let out = 0;
    while (pending && n > out && pending.chunks.length) {
      const c = pending.chunks.shift(); out++;
      pending.res.write(frame(c, false));
    }
    const done = pending && !pending.chunks.length;
    if (done) { pending.res.end(frame('', true)); pending = null; }
    res.end(JSON.stringify({ emitted: out, done: !!done, open: !!pending }));
  } else if (req.url.startsWith('/reset')) { turn = 0; pending = null; res.end('ok'); }
  else res.end('mock ok');
}).listen(5099, '127.0.0.1', () => console.log('mock gemini on 5099'));
