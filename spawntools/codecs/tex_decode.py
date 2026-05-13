"""Decode Spawn Dreamcast TXB0 .TEX containers to PNG.

TXB0 format reverse-engineered from CFGJP/CFGUS/LOBBY37.TEX headers:
  bytes  0..3  : magic 'TXB0'
  bytes  4..7  : u32 LE  -- number of texture entries
  bytes  8..11 : u32 LE  -- absolute file offset where pixel data begins
  bytes 12..15 : pad
  then N x 16-byte records:
    u16 width, u16 height, u8 pixfmt, u8 datafmt, u16 pad,
    u32 offset (relative to pixel-data start), u32 pad

Pixel formats (Dreamcast PVR convention):
  0x00 ARGB1555   0x01 RGB565   0x02 ARGB4444
  0x03 YUV422     0x05 PAL_4BPP 0x06 PAL_8BPP

Data formats:
  0x01 SQUARE_TWIDDLED        0x02 SQUARE_TWIDDLED_MIPMAP
  0x03 VQ                     0x04 VQ_MIPMAP
  0x09 RECTANGLE              0x0D RECTANGLE_TWIDDLED
"""
import os, sys, struct, glob
from PIL import Image

EXTRACTED = r"D:\Capcom Dreamcast  Games - Joe Patched\translated\spawn_jp\extracted"
OUT = r"D:\Capcom Dreamcast  Games - Joe Patched\translated\spawn_jp\scan\png"


def untwiddle_idx(x, y):
    """Morton/twiddle index for square textures.
    Dreamcast convention: addr bit 0 = X0, bit 1 = Y0, bit 2 = X1, bit 3 = Y1..."""
    idx = 0
    bit = 0
    while x or y:
        idx |= (x & 1) << bit; x >>= 1; bit += 1
        idx |= (y & 1) << bit; y >>= 1; bit += 1
    return idx


def decode_pixel(val, pixfmt):
    """Convert one 16-bit pixel value to (R,G,B,A)."""
    if pixfmt == 0x00:  # ARGB1555
        a = 255 if (val >> 15) & 1 else 0
        r = ((val >> 10) & 0x1F) * 255 // 31
        g = ((val >> 5)  & 0x1F) * 255 // 31
        b = (val & 0x1F) * 255 // 31
    elif pixfmt == 0x01:  # RGB565
        r = ((val >> 11) & 0x1F) * 255 // 31
        g = ((val >> 5)  & 0x3F) * 255 // 63
        b = (val & 0x1F) * 255 // 31
        a = 255
    elif pixfmt == 0x02:  # ARGB4444
        a = ((val >> 12) & 0xF) * 17
        r = ((val >> 8)  & 0xF) * 17
        g = ((val >> 4)  & 0xF) * 17
        b = (val & 0xF) * 17
    else:
        return (0, 0, 0, 0)
    return (r, g, b, a)


def decode_texture(data, off, w, h, pixfmt, datafmt):
    """Decode a single texture starting at data[off:]. Returns PIL Image or None."""
    if pixfmt > 0x02:
        return None  # skip palette/YUV for now

    bpp = 16  # all of pixfmt 0..2 are 16-bit
    twiddled = datafmt in (0x01, 0x02, 0x0D)
    vq       = datafmt in (0x03, 0x04)
    has_mip  = datafmt in (0x02, 0x04)

    img = Image.new('RGBA', (w, h))
    px = img.load()

    if vq:
        # VQ: 2KB codebook (256 entries x 8 bytes = 4 twiddled pixels per code) followed by codes
        codebook = data[off:off + 2048]
        codes_off = off + 2048
        if has_mip:
            # skip mipmaps: tiny ones come first; sum of (w/2^i)^2 / 4 codes
            mip_bytes = 0
            cw = w // 2
            while cw >= 1:
                mip_bytes += max(1, (cw * cw) // 4)
                cw //= 2
            mip_bytes += 1  # 1x1 placeholder
            codes_off += mip_bytes
        # each code is one byte indexing into codebook; covers a 2x2 twiddled block
        for by in range(h // 2):
            for bx in range(w // 2):
                idx = untwiddle_idx(bx, by)
                if codes_off + idx >= len(data):
                    return None
                code = data[codes_off + idx]
                base = code * 8
                # codebook entry has 4 pixels in twiddled 2x2 order: (0,0)(0,1)(1,0)(1,1)
                for sub in range(4):
                    val = struct.unpack_from('<H', codebook, base + sub * 2)[0]
                    sx = (sub >> 1) & 1
                    sy = sub & 1
                    px[bx * 2 + sx, by * 2 + sy] = decode_pixel(val, pixfmt)
        return img

    # Non-VQ paths
    pixel_count = w * h
    needed = pixel_count * 2
    if has_mip:
        # mipmaps stored smallest-first; main image is last. Skip them.
        mip_bytes = 0
        cw = w // 2
        while cw >= 1:
            mip_bytes += cw * cw * 2
            cw //= 2
        mip_bytes += 2  # 1x1 placeholder pixel
        off += mip_bytes

    if off + needed > len(data):
        return None
    pixels = struct.unpack_from(f'<{pixel_count}H', data, off)

    if twiddled:
        # square twiddled
        for y in range(h):
            for x in range(w):
                i = untwiddle_idx(x, y)
                px[x, y] = decode_pixel(pixels[i], pixfmt)
    else:
        i = 0
        for y in range(h):
            for x in range(w):
                px[x, y] = decode_pixel(pixels[i], pixfmt)
                i += 1
    return img


def parse_tex(path):
    """Return list of (index, w, h, pixfmt, datafmt, pil_image_or_None)."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'TXB0':
        return None
    n = struct.unpack_from('<I', data, 4)[0]
    data_off = struct.unpack_from('<I', data, 8)[0]
    out = []
    for i in range(n):
        rec = data[16 + i * 16: 16 + (i + 1) * 16]
        w = struct.unpack_from('<H', rec, 0)[0]
        h = struct.unpack_from('<H', rec, 2)[0]
        pixfmt = rec[4]
        datafmt = rec[5]
        offset = struct.unpack_from('<I', rec, 8)[0]
        try:
            img = decode_texture(data, data_off + offset, w, h, pixfmt, datafmt)
        except Exception as e:
            img = None
        out.append((i, w, h, pixfmt, datafmt, img))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    targets = sorted(glob.glob(os.path.join(EXTRACTED, '*.TEX')))
    total = ok = fail = skipped = 0
    summary = []
    for path in targets:
        name = os.path.splitext(os.path.basename(path))[0]
        result = parse_tex(path)
        if result is None:
            skipped += 1
            continue
        for i, w, h, pixfmt, datafmt, img in result:
            total += 1
            tag = f"{name}_{i:02d}_w{w}h{h}_pf{pixfmt:02x}_df{datafmt:02x}"
            if img is None:
                fail += 1
                summary.append(f"FAIL {tag}")
                continue
            img.save(os.path.join(OUT, tag + '.png'))
            ok += 1
        if len(targets) < 60 or len(summary) % 50 == 0:
            print(f"  {os.path.basename(path):<30} n={len(result)}")
    print(f"\nDONE: {total} sub-textures, {ok} decoded, {fail} failed, {skipped} files skipped (not TXB0)")
    if fail:
        for s in summary[:30]:
            print(' ', s)


if __name__ == '__main__':
    main()
