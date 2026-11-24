#!/usr/bin/env python3
"""Conform raw takes into exact-length, speed-ramped clips for the Hyperframes timeline.
Each segment is (take, start_s, end_s, speed). Output is 2560x1440 @ 30fps H.264."""
import subprocess, sys, os
TAKES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'takes')
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'

SPEC = {
  's1-open':   (3.50, [('t1-landing', 0.40, 3.90, 1.0)]),
  's2-explore': (9.40, [('t2-explore', 0.55, 2.90, 1.3), ('t2-explore', 2.90, 6.90, 2.2), ('t2-explore', 6.90, 9.50, 1.5),
                        ('t2-explore', 9.50, 12.20, 1.55), ('t2-explore', 12.20, 14.60, 1.7)]),
  's3-watch':  (8.40, [('t3-vault', 1.20, 4.00, 2.4), ('t3-vault', 4.00, 7.20, 2.4), ('t3-vault', 7.20, 10.60, 2.0), ('t3-vault', 10.60, 17.40, 1.5)]),
  's4-code':   (11.40, [('t4-code', 0.50, 3.40, 1.7), ('t4-code', 3.40, 11.80, 1.36), ('t4-code', 11.80, 15.40, 1.0)]),
  's5-mentor': (12.40, [('t5-mentor', 0.80, 2.60, 1.3), ('t5-mentor', 2.60, 7.40, 1.7), ('t5-mentor', 7.40, 13.20, 1.35),
                        ('t5-mentor', 13.20, 16.00, 1.5), ('t5-mentor', 16.00, 18.60, 1.3)]),
  's6-montage': (8.40, [('t1-landing', 1.00, 2.20, 1.2), ('t2-explore', 2.90, 4.40, 1.5), ('t2-explore', 9.50, 11.00, 1.5),
                        ('t3-vault', 4.00, 5.50, 1.5), ('t4-code', 6.00, 7.50, 1.5), ('t4-code', 12.40, 13.40, 1.0),
                        ('t5-mentor', 9.20, 10.70, 1.5), ('t6-design', 0.80, 2.30, 1.5)]),
}

def build(name, target, segs):
    inputs, chains, labels = [], [], []
    idx = {}
    for t, *_ in segs:
        if t not in idx:
            idx[t] = len(idx); inputs += ['-i', os.path.join(TAKES, t + '.mp4')]
    for i, (t, s, e, sp) in enumerate(segs):
        chains.append(f"[{idx[t]}:v]trim=start={s}:end={e},setpts=(PTS-STARTPTS)/{sp},fps=30,scale=2560:1440:flags=lanczos,setsar=1[s{i}]")
        labels.append(f"[s{i}]")
    dur = sum((e - s) / sp for _, s, e, sp in segs)
    pad = max(0.0, target - dur) + 0.05
    chains.append(f"{''.join(labels)}concat=n={len(segs)}:v=1:a=0,tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={target},setpts=PTS-STARTPTS,format=yuv420p[v]")
    out = os.path.join(OUT, name + '.mp4')
    cmd = ['ffmpeg', '-y', '-v', 'error'] + inputs + ['-filter_complex', ';'.join(chains), '-map', '[v]', '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-r', '30', '-movflags', '+faststart', '-an', out]
    subprocess.run(cmd, check=True)
    print(f"{name}: natural {dur:.2f}s -> {target:.2f}s  ({'padded %.2fs' % (target-dur) if dur < target else 'TRIMMED %.2fs' % (dur-target)})")

if __name__ == '__main__':
    only = sys.argv[2:] 
    for n, (tg, sg) in SPEC.items():
        if not only or n in only: build(n, tg, sg)
