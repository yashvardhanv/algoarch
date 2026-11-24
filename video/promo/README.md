# AlgoArch product film (60 s, 1080p / 30 fps)

A Hyperframes composition (`index.html`) that tells one continuous product journey:
open the browser → explore tracks → learn by watching → write and run code → ask the AI mentor →
fast beat-cut montage → brand reveal. Silent footage + an original synthesized score.

```bash
cd video && npm install                  # once (Node >= 22, ffmpeg)
cd promo
npm run check                            # lint + layout + contrast
npx hyperframes snapshot --at 4,19,31,41,57
npx hyperframes render -o ../out/algoarch-film.mp4 --quality high --fps 30
```

## What is real, and what is stand-in

The browser window shows **the real AlgoArch UI** (dark theme), recorded from the running app by
`capture/` (Chromium + CDP screencast, so hover states, Monaco typing/autocomplete, in-browser
Python execution and streaming all behave as in the product). A few things cannot run in a
network-restricted sandbox, so they are stood in locally:

| Piece | Stand-in |
|---|---|
| AI mentor replies | `capture/mock-gemini.js`: the app's real server and real chat UI talk to a local fake Gemini that streams a scripted answer (the text is authored, not model output) |
| Video Vault player | The product embeds YouTube lectures. YouTube is unreachable here, so the embed is answered by an **original** lecture clip (`capture/lecture.html`) |
| Lecture thumbnails, avatar | Generated neutral gradients / initial (third-party images) |
| Runnable code cell | This checkout has no lesson documents, so `capture/seed.js` seeds one "Two Sum" cell into a **scratch** database (never `data/`). It runs real Python (Pyodide) with real tests |
| Monaco / Pyodide CDNs | Served from the same versions via npm (`capture/routes.js`) |
| Account | Local dev sign-in as `alex@example.com` on the Pro plan (scratch data dir) |

Not in the product (so not shown): a built-in video player with playlists/completion ticks,
"highlight text → explain simpler", and system-design diagrams in the 22 lessons that have bodies
in this repo. The mentor scene asks "Explain that in simpler terms." as a normal follow-up instead.

## Placeholders to replace

- **Site URL `algoarch.app`** is a placeholder, not a verified domain. Change it in `index.html`:
  the address-bar span (`data-site-url`) and the `#urlpill` element near the end.
- Captions/taglines come from the brief; edit them in the `#caps` block and in the
  `data-variable-values` of the `#brand` mount.

## Templates used

- `compositions/components/logo-brand-close.html` (Hyperframes catalog): finale lockup (installed as
  source; its duration was extended 4 s → 6 s and the app's real logo mark is drawn over it).
- `typewriter` and `soft-blur-in` patterns (catalog snippets, inlined in `index.html`) drive the URL typing and every caption.
  Other catalog blocks can be added with `npx hyperframes add <name>` (`npx hyperframes catalog` lists them).

## Pipeline (to re-record the footage)

```bash
# app (repo root): npm ci && npm run build
# scratch data: copy data/{curriculum,videos,resources}.json + data/new_lessons into $D, then
#   node tools/content/import.js --data $D --reset && node video/promo/capture/seed.js $D
# run the app + the fake Gemini:
#   ALGOARCH_DATA_DIR=$D PORT=5050 AUTH_SECRET=demo GEMINI_API_KEY=demo GEMINI_BASE_URL=http://127.0.0.1:5099 node server.js
#   node video/promo/capture/mock-gemini.js
cd capture && npm install && npm run login && npm run lecture && npm run takes && npm run conform
python3 ../tools/score.py ../assets/audio/score.wav     # music; also writes score.m4a (the file index.html uses)
```

`capture/conform.py` holds the edit decisions (segments, speed ramps) that fit each raw take to its
scene length; `index.html` holds the camera moves, captions and timing.
