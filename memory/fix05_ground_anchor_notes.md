# FIX05 GROUND ANCHOR / ELLIPSE HARDENING — learnings (commit 85b53b0)

## Changed files
- backend/tele_clip.py (only production file): _smooth, _ground_anchor, _draw_ring
- backend/tests/test_fix05_ground_anchor_ellipse.py (new, E1–E18, 23 tests)
- telestration.py / server.py untouched — parity already delegated to tele_clip._draw_ring

## Exact function changes
- `_smooth`: (cx, feet_y) RAW passthrough; only (w, h) ±2 averaged. server.py pos_at format unchanged.
- `_ground_anchor`:
  - duel gate: 2nd component ≥55% sub-mass AND full-crop centroid dx >0.35*bw → None (hide)
  - line rejection: band_h ≤ max(3, 0.06*bh) AND foot_w ≥ 0.85*bw → treated as pitch line, climb
  - elevation clamp 0.55→0.35*bh → bbox-bottom fallback (airborne never rings knee/shin)
- `_draw_ring`:
  - state smoothing clamped to raw anchor ±0.30*bw / ±0.12*bh; teleport-glide branch removed
  - ring width continuity ±15%/frame via state["rw"]
  - step-5 restore: connectedComponents, only components reaching centre columns
    (own_r = max(0.55*rw, 0.6*foot_w)) are restored — neighbour never resurrected

## Synthetic test gotchas
- Synthetic players NEED a hip bar connecting legs to torso, else legs become separate
  components and the anchor climbs to the torso bottom.
- Flatness monotonicity breaks at floor-clamped tiny rings (rh min 4px) — test perspective
  at 960x540 scale where geometry is representative.
- Restore mask is blurred (7x7): interior assertions need ≤12 tolerance, not exact equality.
- GREEN=(50,170,60) BGR maps inside the renderer's HSV grass range; KIT=(36,28,200) doesn't.

## Test counts (all green)
FIX05 23 / FIX04 38 / FIX03 26 / FIX02 29 / FIX01 29 / FIX00B 31 / FIX00A 16 = 192.
Legacy tests/test_iter94_tele_clips.py + test_iter55_marker_premium.py: 13 failed on BOTH
the changed and untouched tree (git stash verified) — pre-existing offline/media/server deps.
