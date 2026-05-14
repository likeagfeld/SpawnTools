"""Raw-pixel blob decoder for Capcom proprietary texture containers.

MvC2's STG*TEX.BIN, EFKYTEX.BIN, PL*_DAT.BIN (and similar containers in other
games) store concatenated raw twiddled pixel data with NO PVR header. The
dimensions + pixfmt for each blob live in the game's 1ST_READ.BIN texture-load
function, not in the texture file itself.

Until we RE every game's dimension table, this module:
  1. Detects raw-pixel-data BIN files (no PVR magic, but byte distribution
     looks like twiddled 16-bpp pixels — i.e. lots of 16-bit values clustered
     near their neighbours).
  2. Generates a list of plausible (width, height, pixfmt, datafmt) tuples
     for the file size.
  3. Lets the GUI cycle through hypotheses so the user can pick the right one
     by visual inspection.

Common Capcom DC sizes are 256×256, 512×512, 256×128, 128×256, 1024×512, etc.
For a given blob-byte-length N at 16 bpp, the candidate dim list is every
(w, h) ∈ {power-of-two ≤ 1024} × {power-of-two ≤ 1024} where w*h*2 == N.
"""
from __future__ import annotations
import os
import sys
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Power-of-two dimensions used by Dreamcast PVRs
DIMS = (8, 16, 32, 64, 128, 256, 512, 1024)
PIXFMTS = (0x00, 0x01, 0x02)   # ARGB1555, RGB565, ARGB4444
DATAFMTS_SQUARE = (0x01,)       # SQUARE_TWIDDLED only for square
DATAFMTS_RECT = (0x09, 0x0d)    # RECTANGLE, RECTANGLE_TWIDDLED for non-square


@dataclass
class BlobHypothesis:
    offset: int          # byte offset within source file where the blob starts
    width: int
    height: int
    pixfmt: int
    datafmt: int
    bytes_used: int      # w * h * 2
    confidence: str = ''


def _ensure_codecs():
    codecs_dir = Path(__file__).resolve().parent.parent / 'codecs'
    if str(codecs_dir) not in sys.path:
        sys.path.insert(0, str(codecs_dir))


def looks_like_raw_pixels(data: bytes, sample: int = 4096) -> bool:
    """Heuristic: is this a raw twiddled pixel blob?

    Returns True when the byte distribution shows the typical clustering of
    pixel data (many repeated near-duplicate 16-bit values) and NO known
    container magic in the first 64 bytes.
    """
    if len(data) < 1024: return False
    head = data[:64]
    # Reject known containers
    if head[:4] in (b'PVRT', b'GBIX', b'TXB0', b'AFS\x00'): return False
    # Reject text/code files: lots of ASCII / cp932 patterns
    sample_bytes = data[:sample]
    high_count = sum(1 for b in sample_bytes if b >= 0x80)
    null_count = sample_bytes.count(0)
    # Raw pixel data is roughly random-looking but with clustering. Rough test:
    # at least 25% high bytes (the upper nibble of 16-bit pixels often has bits set).
    if high_count < sample // 4: return False
    if null_count > sample * 0.5: return False
    return True


def candidate_dims(blob_size: int, max_dim: int = 1024) -> list[tuple[int, int]]:
    """Every (w, h) power-of-two pair s.t. w*h*2 == blob_size."""
    pixel_count = blob_size // 2
    out = []
    for w in DIMS:
        if w > max_dim: continue
        if pixel_count % w: continue
        h = pixel_count // w
        if h in DIMS and h <= max_dim:
            out.append((w, h))
    return out


def hypotheses_for_file(path: Path, offset: int = 0,
                         length: int | None = None) -> list[BlobHypothesis]:
    """List every plausible (offset, w, h, pixfmt, datafmt) interpretation
    for the blob at [offset:offset+length] inside `path`. If length is None,
    the entire file from `offset` is considered as a single blob."""
    sz = path.stat().st_size
    if length is None:
        length = sz - offset
    out: list[BlobHypothesis] = []
    for w, h in candidate_dims(length):
        for pf in PIXFMTS:
            datafmts = DATAFMTS_SQUARE if w == h else DATAFMTS_RECT
            for df in datafmts:
                out.append(BlobHypothesis(
                    offset=offset, width=w, height=h,
                    pixfmt=pf, datafmt=df,
                    bytes_used=w * h * 2,
                ))
    return out


def decode_hypothesis(path: Path, hyp: BlobHypothesis):
    """Decode the blob under one hypothesis, returning a PIL Image (or None)."""
    _ensure_codecs()
    import tex_decode
    data = path.read_bytes()
    body = data[hyp.offset:hyp.offset + hyp.bytes_used]
    if len(body) < hyp.bytes_used:
        return None
    try:
        return tex_decode.decode_texture(
            body, 0, hyp.width, hyp.height, hyp.pixfmt, hyp.datafmt,
        )
    except Exception:
        return None


def find_subblobs_via_offset_table(path: Path) -> list[BlobHypothesis]:
    """For PL*_DAT.BIN-style files: read the leading u32 LE table and yield
    one hypothesis per entry. Each entry's blob size is the next entry's
    offset minus this one. Zero-entries are end markers; we resume after
    them (PL*_DAT has multi-section tables separated by zeros)."""
    data = path.read_bytes()
    sz = len(data)
    hyps: list[BlobHypothesis] = []
    # The header is at most 256 bytes — read 64 u32s
    n_to_read = min(64, sz // 4)
    raw = struct.unpack_from(f'<{n_to_read}I', data, 0)
    # First entry must be small (offset of the first blob)
    if raw[0] < 0x10 or raw[0] > sz // 2: return []
    # Build (offset, end) pairs
    valid_offsets = []
    for v in raw:
        if v == 0 or v > sz: continue
        valid_offsets.append(v)
    valid_offsets = sorted(set(valid_offsets))
    if len(valid_offsets) < 2: return []
    # Each pair (offsets[i], offsets[i+1]) defines a blob. Last blob ends at file size.
    boundaries = valid_offsets + [sz]
    for i in range(len(valid_offsets)):
        off = valid_offsets[i]
        end = boundaries[i + 1]
        length = end - off
        if length < 1024: continue   # too small to be a texture
        for w, h in candidate_dims(length):
            for pf in PIXFMTS:
                datafmts = DATAFMTS_SQUARE if w == h else DATAFMTS_RECT
                for df in datafmts:
                    hyps.append(BlobHypothesis(
                        offset=off, width=w, height=h,
                        pixfmt=pf, datafmt=df,
                        bytes_used=w * h * 2,
                    ))
    return hyps


__all__ = [
    'BlobHypothesis', 'looks_like_raw_pixels', 'candidate_dims',
    'hypotheses_for_file', 'decode_hypothesis', 'find_subblobs_via_offset_table',
]
