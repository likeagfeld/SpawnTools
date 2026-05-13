"""PNG -> twiddled PVR pixel data, mirroring tex_decode.

Supports ARGB4444 / RGB565 / ARGB1555 in SQUARE_TWIDDLED (datafmt 0x01)
and RECTANGLE (0x09) / RECTANGLE_TWIDDLED (0x0D). Mipmaps and VQ NOT
implemented yet -- attempts on those will raise NotImplementedError.
"""
import struct
from PIL import Image


def twiddle_idx(x, y):
    """Inverse pairing of tex_decode.untwiddle_idx.
    addr bit 0 = X0, bit 1 = Y0, bit 2 = X1, bit 3 = Y1..."""
    idx = 0
    bit = 0
    while x or y:
        idx |= (x & 1) << bit; x >>= 1; bit += 1
        idx |= (y & 1) << bit; y >>= 1; bit += 1
    return idx


def encode_pixel(r, g, b, a, pixfmt):
    if pixfmt == 0x00:   # ARGB1555
        ab = 1 if a >= 128 else 0
        rb = (r * 31 + 127) // 255
        gb = (g * 31 + 127) // 255
        bb = (b * 31 + 127) // 255
        return (ab << 15) | (rb << 10) | (gb << 5) | bb
    if pixfmt == 0x01:   # RGB565
        rb = (r * 31 + 127) // 255
        gb = (g * 63 + 127) // 255
        bb = (b * 31 + 127) // 255
        return (rb << 11) | (gb << 5) | bb
    if pixfmt == 0x02:   # ARGB4444
        ab = (a * 15 + 127) // 255
        rb = (r * 15 + 127) // 255
        gb = (g * 15 + 127) // 255
        bb = (b * 15 + 127) // 255
        return (ab << 12) | (rb << 8) | (gb << 4) | bb
    raise ValueError(f"unsupported pixfmt 0x{pixfmt:02x}")


def twiddle_idx_2(x, y):
    """Twiddle index for a half-resolution map (used for VQ codes)."""
    return twiddle_idx(x, y)


def encode_image(img: Image.Image, pixfmt: int, datafmt: int) -> bytes:
    """Encode a PIL image (RGBA) to raw 16bpp PVR bytes."""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    w, h = img.size
    if datafmt == 0x02:
        raise NotImplementedError("non-VQ mipmap encode not implemented")
    if datafmt == 0x03:
        return encode_vq(img, pixfmt)
    if datafmt == 0x04:
        return encode_vq_mipmap(img, pixfmt)

    twiddled = datafmt in (0x01, 0x0D)
    px = img.load()
    raw = bytearray(w * h * 2)

    if twiddled:
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                val = encode_pixel(r, g, b, a, pixfmt)
                i = twiddle_idx(x, y)
                struct.pack_into('<H', raw, i * 2, val)
    else:  # rectangle / linear
        i = 0
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                val = encode_pixel(r, g, b, a, pixfmt)
                struct.pack_into('<H', raw, i * 2, val)
                i += 1
    return bytes(raw)


def encode_vq(img: Image.Image, pixfmt: int) -> bytes:
    """Vector-quantize with text-aware codebook seeding.

    Strategy: instead of pure k-means clustering, we DEDICATE codebook slots
    to the most common unique 2x2 blocks (highest-frequency exact matches).
    This preserves text edges (which are uniform color blocks) much better
    than k-means averaging.
    """
    import numpy as np
    from collections import Counter

    w, h = img.size
    px = np.array(img)
    bh, bw = h // 2, w // 2

    # Build all 2x2 blocks as 8-byte tuples
    block_bytes = []
    for by in range(bh):
        for bx in range(bw):
            block = []
            for sub in range(4):
                sx = (sub >> 1) & 1
                sy = sub & 1
                p = px[by*2 + sy, bx*2 + sx]
                val = encode_pixel(int(p[0]), int(p[1]), int(p[2]), int(p[3]), pixfmt)
                block.extend([val & 0xFF, (val >> 8) & 0xFF])
            block_bytes.append(bytes(block))

    n_clusters = 256
    # Get the 256 most-frequent unique blocks
    counter = Counter(block_bytes)
    most_common = counter.most_common(n_clusters)
    codebook = [b for b, _ in most_common]

    # Build a lookup: block -> codebook index (for exact-match cases)
    cb_set = {b: i for i, b in enumerate(codebook)}

    # If we have fewer than 256 unique blocks, pad with zeros
    while len(codebook) < n_clusters:
        codebook.append(b'\x00' * 8)

    # For each input block: exact match if possible; otherwise nearest by L2 dist
    import numpy as np
    cb_arr = np.array([list(b) for b in codebook[:n_clusters]], dtype=np.int32)
    raw_indices = bytearray(bh * bw)
    for i, b in enumerate(block_bytes):
        if b in cb_set:
            idx = cb_set[b]
        else:
            # nearest neighbor
            arr = np.array(list(b), dtype=np.int32)
            d = ((cb_arr - arr) ** 2).sum(axis=1)
            idx = int(d.argmin())
        # Twiddled placement
        by = i // bw
        bx = i % bw
        t = twiddle_idx_2(bx, by)
        raw_indices[t] = idx

    cb_array = np.array([list(b) for b in codebook[:n_clusters]], dtype=np.uint8)
    return cb_array.tobytes() + bytes(raw_indices)


def _build_codebook_for_blocks(block_bytes, n_clusters=256):
    """Pick a 256-entry codebook by frequency over `block_bytes` (list of 8-byte tuples).

    Returns (codebook_list, cb_set, cb_arr_int32).
    Pads with zeros if fewer than n_clusters unique blocks present.
    """
    import numpy as np
    from collections import Counter
    counter = Counter(block_bytes)
    most_common = counter.most_common(n_clusters)
    codebook = [b for b, _ in most_common]
    cb_set = {b: i for i, b in enumerate(codebook)}
    while len(codebook) < n_clusters:
        codebook.append(b'\x00' * 8)
    cb_arr = np.array([list(b) for b in codebook[:n_clusters]], dtype=np.int32)
    return codebook, cb_set, cb_arr


def _quantize_blocks(block_bytes, cb_set, cb_arr):
    """Map each block to a codebook index: exact match if present, else nearest."""
    import numpy as np
    out = bytearray(len(block_bytes))
    for i, b in enumerate(block_bytes):
        if b in cb_set:
            out[i] = cb_set[b]
        else:
            arr = np.array(list(b), dtype=np.int32)
            d = ((cb_arr - arr) ** 2).sum(axis=1)
            out[i] = int(d.argmin())
    return out


def _blocks_from_image(img, pixfmt):
    """Return (list of 8-byte 2x2-block tuples, bw, bh).

    Each block is laid out per the Dreamcast VQ convention: 4 pixels in
    twiddled 2x2 order (sub=0->(0,0), 1->(0,1), 2->(1,0), 3->(1,1)).
    """
    import numpy as np
    w, h = img.size
    px = np.array(img.convert('RGBA'))
    bh, bw = h // 2, w // 2
    block_bytes = []
    for by in range(bh):
        for bx in range(bw):
            block = []
            for sub in range(4):
                sx = (sub >> 1) & 1
                sy = sub & 1
                p = px[by*2 + sy, bx*2 + sx]
                val = encode_pixel(int(p[0]), int(p[1]), int(p[2]), int(p[3]), pixfmt)
                block.extend([val & 0xFF, (val >> 8) & 0xFF])
            block_bytes.append(bytes(block))
    return block_bytes, bw, bh


def encode_vq_mipmap(img: Image.Image, pixfmt: int) -> bytes:
    """VQ-mipmapped encode.

    Output layout (matching tex_decode VQ_MIPMAP path):
      - 2048-byte codebook (256 entries x 8 bytes)
      - mipmap level codes from smallest -> largest:
          1x1 placeholder: 1 byte
          2x2 -> max(1, (2/2)^2) = 1 byte
          4x4 -> (4/2)^2 = 4 bytes
          ...
          w x h -> (w/2)*(h/2) bytes

    Codebook is built from the LARGEST level (preserves text edges), and the
    same codebook is reused for every mipmap level. Each level is twiddled
    independently.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    w, h = img.size
    if w != h:
        raise ValueError(f"VQ_MIPMAP requires square image, got {w}x{h}")

    # 1. Build codebook from the largest level
    full_blocks, bw_full, bh_full = _blocks_from_image(img, pixfmt)
    codebook, cb_set, cb_arr = _build_codebook_for_blocks(full_blocks, 256)

    # 2. Quantize each mipmap level using the same codebook.
    # File layout (per tex_decode.decode_texture VQ_MIPMAP path):
    #   - 1 byte placeholder (the +1 after the cw-loop)
    #   - smaller mipmaps stored cw=1,2,4,...,w//2 with max(1,(cw*cw)//4) bytes each
    #     here `cw` is the mip-level side length, so codes = cw*cw/4 (one byte each).
    #     For cw=1 we still write 1 byte. For cw=2: 1 byte (one 2x2 block).
    #   - largest level (cw=w) stores (w/2)*(h/2) codes, but the loop never reaches
    #     it because it stops at cw = w//2.
    mip_chunks = []

    # Placeholder byte: one byte. Use the codebook index that best matches
    # the image's average color (rendered as a 2x2 block).
    tiny = img.resize((2, 2), Image.LANCZOS)
    tiny_blocks, _, _ = _blocks_from_image(tiny, pixfmt)
    placeholder_idx = _quantize_blocks(tiny_blocks, cb_set, cb_arr)[0]
    mip_chunks.append(bytes([placeholder_idx]))

    # Smaller mipmap levels: cw runs 1, 2, 4, ..., w//2 (each is the side
    # length of that mip level in pixels). cw=1 emits 1 byte (placeholder
    # for a 1x1 level), cw=2 emits 1 byte (one 2x2 block), cw>=4 emits
    # cw*cw/4 twiddled-2x2-block indices.
    side = 1
    smaller_levels = []
    while side <= w // 2:
        smaller_levels.append(side)
        side *= 2
    for lvl_side in smaller_levels:
        if lvl_side == 1:
            # 1x1: 1 byte placeholder; pick codebook idx for the 1x1 image
            # rendered as a 2x2 block.
            t1 = img.resize((2, 2), Image.LANCZOS)
            tb, _, _ = _blocks_from_image(t1, pixfmt)
            mip_chunks.append(bytes([_quantize_blocks(tb, cb_set, cb_arr)[0]]))
            continue
        # Level image is lvl_side x lvl_side; has (lvl_side/2)^2 blocks
        if lvl_side == w:
            level_img = img
            level_blocks = full_blocks
            cw = bw_full
        else:
            level_img = img.resize((lvl_side, lvl_side), Image.LANCZOS)
            level_blocks, cw, _ = _blocks_from_image(level_img, pixfmt)
        idx_bytes = _quantize_blocks(level_blocks, cb_set, cb_arr)
        # Twiddle: each block at (bx, by) -> position twiddle_idx_2(bx, by)
        out = bytearray(cw * cw)
        for by in range(cw):
            for bx in range(cw):
                t = twiddle_idx_2(bx, by)
                out[t] = idx_bytes[by * cw + bx]
        mip_chunks.append(bytes(out))

    # Largest level: cw_full = w//2 blocks per side -> (w/2)*(h/2) codes
    idx_bytes = _quantize_blocks(full_blocks, cb_set, cb_arr)
    out = bytearray(bw_full * bh_full)
    for by in range(bh_full):
        for bx in range(bw_full):
            t = twiddle_idx_2(bx, by)
            out[t] = idx_bytes[by * bw_full + bx]
    mip_chunks.append(bytes(out))

    import numpy as np
    cb_array = np.array([list(b) for b in codebook[:256]], dtype=np.uint8)
    return cb_array.tobytes() + b''.join(mip_chunks)


def round_trip_test(src_png: str, pixfmt: int, datafmt: int) -> None:
    """Sanity test: decode raw -> PIL -> re-encode raw, check that re-encode
    produces nearly the same raw bytes (lossy due to quantization)."""
    img = Image.open(src_png).convert('RGBA')
    raw1 = encode_image(img, pixfmt, datafmt)
    # round-trip through bytes -> image -> raw
    from tex_decode import decode_texture, untwiddle_idx
    img2 = decode_texture(raw1, 0, img.size[0], img.size[1], pixfmt, datafmt)
    raw2 = encode_image(img2, pixfmt, datafmt)
    diff = sum(1 for a, b in zip(raw1, raw2) if a != b)
    print(f"round-trip diff bytes: {diff} / {len(raw1)}")
