"""Standalone Dreamcast PVR file codec.

PVR files start with either:
- "GBIX" (8-byte header w/ global index) + "PVRT" data
- "PVRT" data directly

PVRT header:
  bytes 0-3   "PVRT" magic
  bytes 4-7   u32 LE — data length (excluding 8-byte PVRT header)
  bytes 8     pixfmt (ARGB1555/RGB565/ARGB4444/etc.)
  byte  9     datafmt (twiddled/rectangle/VQ etc.)
  bytes 10-11 padding
  bytes 12-13 u16 width
  bytes 14-15 u16 height
  then pixel data (width*height*2 bytes for 16bpp, less for VQ)

We reuse tex_decode.decode_texture() for the pixel decode.
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image
from tex_decode import decode_texture
from tex_encode import encode_image


def parse_pvp(path):
    """Parse a Dreamcast PVP palette file.
    Format: 'PVPL' magic + u32 data_size + u8 pixfmt + 3 bytes pad +
            u32 num_entries + entries (4 bytes each, ARGB8888 LE).
    Returns (pixfmt, entries) or None."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'PVPL':
        return None
    pixfmt = data[8]
    n = struct.unpack('<I', data[12:16])[0]
    if n == 0 or n > 256:
        # Some PVPs store n at different offsets — fallback
        n = (len(data) - 16) // 4
    entries = []
    for i in range(n):
        off = 16 + i * 4
        if off + 4 > len(data): break
        b = data[off]; g = data[off+1]; r = data[off+2]; a = data[off+3]
        entries.append((r, g, b, a))
    return pixfmt, entries


def find_companion_palette(pvr_path):
    """Look for a sibling PVP file. Returns parsed palette or None."""
    dir = os.path.dirname(pvr_path)
    base = os.path.splitext(os.path.basename(pvr_path))[0]
    # Try same name as PVR
    same = os.path.join(dir, base + '.PVP')
    if os.path.exists(same):
        return parse_pvp(same)
    # Try BANK00.PVP / BANK01.PVP etc. (DP3 convention)
    for bank in ('BANK00.PVP', 'BANK01.PVP', 'BANK02.PVP', 'BANK03.PVP'):
        cand = os.path.join(dir, bank)
        if os.path.exists(cand):
            return parse_pvp(cand)
    return None


def parse_pvr(path):
    """Return (width, height, pixfmt, datafmt, pixel_offset_in_file, pixel_bytes)."""
    with open(path, 'rb') as f:
        data = f.read()
    pos = 0
    # Optional GBIX header
    if data[:4] == b'GBIX':
        gbix_len = struct.unpack('<I', data[4:8])[0]
        pos = 8 + gbix_len
    if data[pos:pos+4] != b'PVRT':
        return None
    # PVRT header
    body_len = struct.unpack('<I', data[pos+4:pos+8])[0]
    pixfmt = data[pos+8]
    datafmt = data[pos+9]
    width = struct.unpack('<H', data[pos+12:pos+14])[0]
    height = struct.unpack('<H', data[pos+14:pos+16])[0]
    pixel_off = pos + 16
    return {
        'width': width, 'height': height,
        'pixfmt': pixfmt, 'datafmt': datafmt,
        'pixel_offset': pixel_off,
        'header_len': pos + 16,
        'data_len': body_len,
        'gbix_prefix_len': pos,
        'raw': data,
    }


def decode_paletted_pvr(info, palette):
    """Decode a paletted (PAL_4BPP / PAL_8BPP) PVR using a palette table.
    palette: list of (r,g,b,a) tuples.

    PAL_8BPP: pixfmt 0x06, one byte = one palette index.
    PAL_4BPP: pixfmt 0x05, two indices per byte; pixel i is lower nibble if
              i is even, upper nibble if i is odd.
    Twiddled: index layout follows the Dreamcast morton/twiddle order
              (datafmt 0x05/0x06/0x07).
    """
    from PIL import Image
    from tex_decode import untwiddle_idx
    w = info['width']; h = info['height']
    pixel_data = info['raw'][info['pixel_offset']:]
    is_8bpp = info['pixfmt'] == 0x06
    is_4bpp = info['pixfmt'] == 0x05
    is_twiddled = info['datafmt'] in (0x05, 0x06, 0x07)

    img = Image.new('RGBA', (w, h))
    px = img.load()
    if is_8bpp:
        for y in range(h):
            for x in range(w):
                if is_twiddled:
                    i = untwiddle_idx(x, y)
                else:
                    i = y * w + x
                if i >= len(pixel_data): continue
                idx = pixel_data[i]
                if idx < len(palette):
                    px[x, y] = palette[idx]
    elif is_4bpp:
        for y in range(h):
            for x in range(w):
                if is_twiddled:
                    i = untwiddle_idx(x, y)
                else:
                    i = y * w + x
                byte_pos = i // 2
                if byte_pos >= len(pixel_data): continue
                nibble_byte = pixel_data[byte_pos]
                # Lower nibble holds the even-i index, upper nibble holds odd.
                idx = (nibble_byte & 0x0F) if (i & 1) == 0 else ((nibble_byte >> 4) & 0x0F)
                if idx < len(palette):
                    px[x, y] = palette[idx]
    return img


def _quantize_to_palette(img, palette):
    """Map every pixel in `img` (RGBA) to the nearest palette entry by
    squared-distance over RGBA. Returns a flat list of palette indices in
    row-major (y*w + x) order.

    Uses a small per-color cache so large images with few unique colors
    quantize quickly. numpy speeds up the bulk path when available.
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    w, h = img.size
    try:
        import numpy as np
        pal_arr = np.array(palette, dtype=np.int32)  # (N,4)
        pix = np.array(img, dtype=np.int32).reshape(-1, 4)  # (h*w,4)
        # Compute squared distance from each pixel to each palette entry.
        # Chunked to keep memory bounded for big textures.
        out = np.empty(pix.shape[0], dtype=np.uint8)
        chunk = 65536
        for s in range(0, pix.shape[0], chunk):
            seg = pix[s:s+chunk]
            d = ((seg[:, None, :] - pal_arr[None, :, :]) ** 2).sum(axis=2)
            out[s:s+chunk] = d.argmin(axis=1).astype(np.uint8)
        return out.tolist()
    except ImportError:
        cache = {}
        px = img.load()
        out = [0] * (w * h)
        for y in range(h):
            for x in range(w):
                rgba = px[x, y]
                idx = cache.get(rgba)
                if idx is None:
                    best = 0; bestd = 1 << 30
                    for k, p in enumerate(palette):
                        d = (rgba[0]-p[0])**2 + (rgba[1]-p[1])**2 + (rgba[2]-p[2])**2 + (rgba[3]-p[3])**2
                        if d < bestd:
                            bestd = d; best = k
                    cache[rgba] = best
                    idx = best
                out[y * w + x] = idx
        return out


def encode_paletted_pvr(img, info, palette):
    """Encode `img` (PIL Image) to packed twiddled palette-index bytes
    matching the PVR's pixfmt/datafmt. Returns a bytes object that drops
    in at info['pixel_offset'] and fits the original budget.

    Quantization is nearest-color in palette (RGBA squared distance).
    Palette is restricted to its first 16 entries when encoding 4BPP.
    """
    from tex_encode import twiddle_idx
    w = info['width']; h = info['height']
    if img.size != (w, h):
        raise ValueError(f"image size {img.size} != PVR {(w, h)}")
    is_8bpp = info['pixfmt'] == 0x06
    is_4bpp = info['pixfmt'] == 0x05
    if not (is_8bpp or is_4bpp):
        raise ValueError(f"not a paletted pixfmt: 0x{info['pixfmt']:02x}")
    is_twiddled = info['datafmt'] in (0x05, 0x06, 0x07)

    # For 4BPP, restrict to first 16 palette entries.
    eff_pal = palette[:16] if is_4bpp else palette[:256]
    if not eff_pal:
        raise ValueError("empty palette")

    indices_rowmajor = _quantize_to_palette(img, eff_pal)

    if is_8bpp:
        # One byte per pixel, placed at twiddled offset (or linear).
        out = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                i = twiddle_idx(x, y) if is_twiddled else (y * w + x)
                out[i] = indices_rowmajor[y * w + x] & 0xFF
        return bytes(out)
    else:
        # 4BPP: two indices per byte. Pixel i (in storage order) goes in the
        # lower nibble if i is even, upper nibble if i is odd. We must build
        # an array of length w*h indices (in storage order) first, then pack.
        storage_idx = [0] * (w * h)
        for y in range(h):
            for x in range(w):
                i = twiddle_idx(x, y) if is_twiddled else (y * w + x)
                storage_idx[i] = indices_rowmajor[y * w + x] & 0x0F
        out = bytearray((w * h + 1) // 2)
        for i, v in enumerate(storage_idx):
            bp = i >> 1
            if (i & 1) == 0:
                out[bp] = (out[bp] & 0xF0) | (v & 0x0F)
            else:
                out[bp] = (out[bp] & 0x0F) | ((v & 0x0F) << 4)
        return bytes(out)


def decode_pvr(path):
    """Returns (PIL Image, metadata) or (None, metadata)."""
    info = parse_pvr(path)
    if not info:
        return None, None
    img = None
    # Palette-format detection
    if info['pixfmt'] in (0x05, 0x06):
        pal = find_companion_palette(path)
        if pal:
            _, palette = pal
            try:
                img = decode_paletted_pvr(info, palette)
                info['paletted'] = True
                info['palette'] = palette
                return img, info
            except Exception:
                pass
    try:
        pixel_data = info['raw'][info['pixel_offset']:]
        img = decode_texture(pixel_data, 0, info['width'], info['height'],
                             info['pixfmt'], info['datafmt'])
    except Exception:
        pass
    return img, info


def encode_pvr_inplace(path, new_img, info):
    """Re-encode new_img using info's pixfmt/datafmt and overwrite path.

    For paletted PVRs (pixfmt 0x05 / 0x06) the companion palette is loaded
    from the sibling .PVP and used to quantize new_img.
    """
    if (new_img.size[0], new_img.size[1]) != (info['width'], info['height']):
        return False

    if info['pixfmt'] in (0x05, 0x06):
        palette = info.get('palette')
        if palette is None:
            pal = find_companion_palette(path)
            if not pal:
                return False
            _, palette = pal
        new_pixels = encode_paletted_pvr(new_img, info, palette)
    else:
        new_pixels = encode_image(new_img, info['pixfmt'], info['datafmt'])

    # Build new file: original header + new pixel data
    raw = bytearray(info['raw'])
    pixel_off = info['pixel_offset']
    # Budget check before writing.
    if len(new_pixels) > len(info['raw']) - pixel_off:
        return False
    raw[pixel_off:pixel_off + len(new_pixels)] = new_pixels
    with open(path, 'wb') as f:
        f.write(bytes(raw))
    return True


if __name__ == '__main__':
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            img, info = decode_pvr(path)
            if img:
                out = os.path.splitext(path)[0] + '.png'
                img.save(out)
                print(f'  {path} -> {out}  ({info["width"]}x{info["height"]}  pf={info["pixfmt"]:#x} df={info["datafmt"]:#x})')
            else:
                print(f'  {path}  FAILED to decode (info={info})')
