"""Project Justice (Capcom Dreamcast) inner-texture codec.

Format reverse-engineered from WMENU.AFS / MGDATA.AFS / etc. inner files
(extracted by archive_unpackers.AFS). 3SYS.BIN is data, not a loader;
1ST_READ.BIN is the runtime executable but no header is stored on disk.

Inner file layout (each .bin from an unpacked .AFS):

    [Naomi-LZSS-compressed stream] [zero-pad to AFS sector boundary]

Decompressed payload is raw 16-bpp PVR pixel data in SQUARE_TWIDDLED layout
(no PVRT header, no mip chain, no codebook). Dimensions are inferred from
the decompressed length (256x256 == 0x20000 is the overwhelming majority;
128x128, 512x512, plus a few atlases). The 16-bpp pixel format
(ARGB4444 / RGB565 / ARGB1555) is selected per texture by the caller --
in the JP game the loader is told the format at draw time, not in-file.
We heuristically detect format by trying all three and scoring which one
produces a coherent image (non-zero alpha variance for ARGB4444 vs. a
forced-opaque RGB565).

Public API:
    decompress(buf)            -> raw pixel bytes
    decode_pj_texture(buf,fmt=None)  -> PIL.Image (RGBA)
    encode_pj_texture(img,fmt) -> bytes (compressed, ready to repack)

The Naomi-LZSS codec is shared with MvC2 / CvS2 / Spawn-DC and lives in
naomi_lzss.py.
"""
import math
import struct
from typing import Optional, Tuple

from PIL import Image

from naomi_lzss import compress as _lzss_compress
from naomi_lzss import decompress as _lzss_decompress
from tex_decode import decode_pixel, untwiddle_idx
from tex_encode import encode_pixel, twiddle_idx

PIXFMT_ARGB1555 = 0x00
PIXFMT_RGB565 = 0x01
PIXFMT_ARGB4444 = 0x02

# Known good (width, height) candidates for unheaderless inner textures.
# Listed in descending preference (square first, then common 2:1 sprite sheets).
_DIM_CANDIDATES = [
    (256, 256),
    (128, 128),
    (512, 512),
    (64, 64),
    (512, 256),
    (256, 128),
    (128, 64),
    (64, 32),
    (32, 32),
    (1024, 512),
    (1024, 1024),
]


def decompress(buf: bytes) -> bytes:
    """Strip the AFS zero padding and Naomi-LZSS-decompress."""
    return _lzss_decompress(buf)


def infer_dimensions(pixel_byte_count: int) -> Optional[Tuple[int, int]]:
    """Return (w, h) such that w*h*2 == pixel_byte_count, preferring squares."""
    px = pixel_byte_count // 2
    for w, h in _DIM_CANDIDATES:
        if w * h == px:
            return (w, h)
        # tolerate up to a 4-byte LZSS terminator/padding overhang
        if 0 < px - w * h <= 4:
            return (w, h)
    # Fallback: any power-of-two square
    side = int(math.isqrt(px))
    if side * side == px and (side & (side - 1)) == 0:
        return (side, side)
    return None


def _decode_raw(raw: bytes, w: int, h: int, pixfmt: int) -> Image.Image:
    pixels = struct.unpack(f"<{w * h}H", raw[: w * h * 2])
    img = Image.new("RGBA", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = decode_pixel(pixels[untwiddle_idx(x, y)], pixfmt)
    return img


def _score_image(img: Image.Image) -> float:
    """Higher = more plausibly the right pixel format.

    Heuristics: ARGB4444 textures use the alpha channel; RGB565 forces
    alpha=255 everywhere; ARGB1555 yields binary alpha. A well-decoded
    image also has good luma variance.
    """
    px = list(img.getdata())
    n = len(px)
    # alpha entropy: how many distinct alpha values are there?
    alphas = {p[3] for p in px[::97]}  # sample
    # color variance: stddev of luma over a sample
    sample = px[::101]
    if not sample:
        return 0.0
    luma = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b, _) in sample]
    mean = sum(luma) / len(luma)
    var = sum((l - mean) ** 2 for l in luma) / len(luma)
    return var * (1 + len(alphas))


def decode_pj_texture(
    buf: bytes,
    pixfmt: Optional[int] = None,
    size: Optional[Tuple[int, int]] = None,
) -> Image.Image:
    """Decode one Project Justice inner .bin to a PIL Image.

    If pixfmt is None, all three 16-bpp formats are tried and the
    heuristically-best image is returned. Pass an explicit pixfmt
    (PIXFMT_ARGB4444 etc.) when the caller already knows the format
    -- this is much faster.
    """
    raw = decompress(buf)
    if size is None:
        size = infer_dimensions(len(raw))
        if size is None:
            raise ValueError(f"cannot infer dimensions for {len(raw)}-byte payload")
    w, h = size

    if pixfmt is not None:
        return _decode_raw(raw, w, h, pixfmt)

    best = None
    best_score = -1.0
    for pf in (PIXFMT_ARGB4444, PIXFMT_RGB565, PIXFMT_ARGB1555):
        img = _decode_raw(raw, w, h, pf)
        s = _score_image(img)
        if s > best_score:
            best_score = s
            best = img
    return best


def encode_pj_texture(img: Image.Image, pixfmt: int) -> bytes:
    """Encode a PIL Image to a Project Justice inner .bin (LZSS-compressed,
    twiddled, 16bpp). Caller is responsible for padding to AFS sectors
    when repacking the outer archive.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    # twiddled write
    out = bytearray(w * h * 2)
    src = img.load()
    for y in range(h):
        for x in range(w):
            i = twiddle_idx(x, y)
            r, g, b, a = src[x, y]
            v = encode_pixel(r, g, b, a, pixfmt)
            struct.pack_into("<H", out, i * 2, v)
    return _lzss_compress(bytes(out))


if __name__ == "__main__":
    # Self-test: round-trip a known-good WMENU texture
    import os
    import sys

    work = (
        r"D:\Capcom Dreamcast  Games - Joe Patched\RC2 Translated"
        r"\Project Justice (JP)\texture_work\WMENU.AFS_unpacked"
    )
    path = os.path.join(work, "file_0001.bin")
    if not os.path.exists(path):
        print("self-test data missing")
        sys.exit(0)
    with open(path, "rb") as fh:
        buf = fh.read()
    img = decode_pj_texture(buf, pixfmt=PIXFMT_ARGB4444)
    print(f"decoded: {img.size} mode={img.mode}")
    re_enc = encode_pj_texture(img, PIXFMT_ARGB4444)
    img2 = decode_pj_texture(re_enc, pixfmt=PIXFMT_ARGB4444)
    print(f"round-trip: re-encoded size={len(re_enc)} re-decoded={img2.size}")
    same = list(img.getdata()) == list(img2.getdata())
    print(f"pixel-perfect round-trip: {same}")
