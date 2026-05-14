"""Per-game raw-blob pixfmt/datafmt auto-probe.

For every game with raw-blob containers (MvC2 STG*TEX.BIN, Power Stone 2
DM*_CONNECT.BIN, etc.) sample-decode each chunk with every (pixfmt,
datafmt) combo and score by:
  - decode succeeded without error
  - rendered image has non-degenerate variance (i.e., not solid black or
    one-color noise — the wrong format produces high-frequency garbage,
    the right one produces recognisable structure)

Picks the highest-scoring combo per game and writes
  spawntools/bundled/raw_format_profiles.json
which game_registry.py reads to set per-game defaults.

User never sees this — the right format is auto-applied on disc open.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'spawntools' / 'codecs'))

from spawntools.core import archives
import tex_decode
from PIL import Image
import statistics

OUT = REPO / 'spawntools' / 'bundled' / 'raw_format_profiles.json'

PIX_FMTS = [0x00, 0x01, 0x02]      # ARGB1555, RGB565, ARGB4444
DATA_FMTS = [0x01, 0x09, 0x0d]     # SQUARE_TWIDDLED, RECTANGLE, RECTANGLE_TWIDDLED


def image_score(img: Image.Image) -> float:
    """Higher score = more 'natural' looking. Wrong format produces high-
    frequency noise (high entropy across small windows); right format
    produces clusters of similar pixels."""
    if img is None: return -1.0
    w, h = img.size
    if w * h < 64: return -1.0
    # Resize to fixed 64x64 for fast scoring
    s = img.resize((64, 64))
    px = list(s.convert('RGBA').getdata())
    # Local variance: each pixel's distance to its right neighbour.
    diffs = []
    for y in range(64):
        row_start = y * 64
        for x in range(63):
            a = px[row_start + x]; b = px[row_start + x + 1]
            diffs.append((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)
    if not diffs: return 0.0
    mean = sum(diffs) / len(diffs)
    # Wrong format → mean diff ~50000+ (random noise). Right format → mean diff < 20000.
    # Also reject solid-colour (mean diff = 0).
    if mean < 50: return -1.0
    return 100000.0 / (mean + 1.0)


def probe_chunk(pvr_bytes: bytes, w: int, h: int):
    """Try every (pixfmt, datafmt) combo on a chunk. Return list of
    (pf, df, score) sorted by score descending."""
    out = []
    for pf in PIX_FMTS:
        for df in DATA_FMTS:
            if df == 0x01 and w != h: continue   # square-twiddled requires square
            if df in (0x09, 0x0d) and w == h: pass
            try:
                img = tex_decode.decode_texture(pvr_bytes, 0, w, h, pf, df)
            except Exception:
                continue
            if img is None: continue
            sc = image_score(img)
            out.append((pf, df, sc))
    out.sort(key=lambda x: -x[2])
    return out


def main():
    from spawntools.bundled import game_registry as reg
    profiles = {}
    for game in reg.GAMES:
        pat = game.rc2_dir / 'patches'
        if not pat.is_dir(): continue
        print(f'\n=== {game.slug} ===', flush=True)
        # Collect candidate chunks
        chunks = []
        for p in pat.rglob('*.BIN'):
            if p.name.startswith('ADX_') or p.name == '2_DP.BIN': continue
            try:
                kind, members = archives.list_members(p)
            except Exception:
                continue
            if not (kind == 'RAW' and members): continue
            for m in members[:3]:   # 3 samples per file
                if m.raw_width and m.raw_height:
                    chunks.append(m)
            if len(chunks) >= 12: break
        if not chunks:
            print(f'  no raw-blob chunks to probe')
            continue
        # Vote across all chunks
        votes = {}
        for m in chunks:
            for pf, df, sc in probe_chunk(m.pvr_bytes, m.raw_width, m.raw_height)[:1]:
                key = (pf, df)
                votes[key] = votes.get(key, 0.0) + sc
        if not votes: continue
        winner = max(votes.items(), key=lambda x: x[1])
        (pf, df), score = winner
        print(f'  best: pf=0x{pf:02x} df=0x{df:02x}  total_score={score:.0f}  chunks_probed={len(chunks)}')
        profiles[game.slug] = {
            'pixfmt':   pf,
            'datafmt':  df,
            'score':    round(score, 1),
            'probed_chunks': len(chunks),
        }

    OUT.write_text(json.dumps(profiles, indent=2), encoding='utf-8')
    print(f'\nwrote {OUT}  ({len(profiles)} games profiled)')


if __name__ == '__main__':
    main()
