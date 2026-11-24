# AlgoArch videos

Video projects built with [Hyperframes](https://hyperframes.heygen.com) (HTML + GSAP in, MP4 out).
Needs Node >= 22 and ffmpeg. This folder is separate from the app, so the app's own
`package.json` and Node 18 support are untouched.

## What's here

| Project | What it is |
|---|---|
| `intro/` | 10 s "Yashvardhan + AlgoArch" intro (pure motion graphics) |
| `promo/` | 60 s product film built from **real recordings of the app** + an original score (see `promo/README.md`) |

Rendered films are written to `out/`, which is git-ignored.

## intro/ — 10 s "Yashvardhan + AlgoArch" intro

1920x1080, 30 fps, silent. Colors and fonts come from the app's design tokens
(`public/style.css`); fonts and GSAP are vendored in `intro/assets/` so renders work offline.

```bash
cd video && npm install        # once
cd intro
npm run dev                    # live preview in the Hyperframes studio
npm run check                  # lint + layout + contrast
npx hyperframes snapshot --at 1,4,7,9.8   # PNG frames to eyeball
npm run render -- -o ../out/algoarch-intro.mp4 --quality high
```

Edit copy and timing in `intro/index.html` (scene start times live in the `S` constant and the
`data-start` attributes; the three wipes are `#w1`–`#w3`).
