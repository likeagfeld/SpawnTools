"""Unpackers for Capcom/Sega Dreamcast archive formats:
- AFS (Sega "AFS" format - Project Justice, JoJo)
- PAC (Capcom .PAC archives - Vampire Chronicle, Power Stone 2)
- PVS (Capcom .PVS archives - JoJo)
- PZZ (Capcom .PZZ archives - Street Fighter III 3rd Strike)
- SLW (Capcom .SLW raw-VRAM container - Net de Tennis)

These contain PVR textures (and other assets) which can then be processed
by pvr_codec.py for translation.

PZZ format (reverse-engineered for SF III 3rd Strike, May 2026):
  - 128-byte header = 16 (offset_u32_le, size_u32_le) pairs
  - Each non-empty entry is Naomi-LZSS compressed (see naomi_lzss.py)
  - Decompressed content is a raw PVR (PVRT magic, optionally GBIX-prefixed)
  - First entry typically starts at 0x80 (right after header)
  - Unused entries have offset=size=0

SLW format (reverse-engineered for Net de Tennis, May 2026):
  - No magic - file IS a Naomi-LZSS stream (first u16 is the LZSS bitmask).
  - Decompresses to a concatenation of raw VRAM textures (no per-texture
    header). Dimensions/pixel format are NOT in the file; they are
    supplied at upload time by the game code.
  - Empirical: most files are ARGB4444 (pixfmt 0x02) twiddled, common
    dims 512x512, 256x256, 256x128, 128x128, 512x256. Title screens
    (TITLE.SLW, MELODY.SLW, SELECT.SLW) are multi-texture concatenations
    (e.g. 512x512 + 256x256). NETWK_B.SLW = 1024x512.
  - 1ST_READ.BIN contains a 44-byte-per-entry file index table
    (filename[16] + load_addr_u32 + size_u32 + first4bytes + path[16])
    starting near offset 0x107a48; entries are stored one-shifted (each
    entry's addr/size/cache refer to the NEXT filename in sequence).
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
try:
    import naomi_lzss
except Exception:
    naomi_lzss = None


def unpack_afs(path, out_dir):
    """Sega AFS archive: 'AFS\\x00' + count + (offset,size) table + data."""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] != b'AFS\x00':
        return None
    n = struct.unpack('<I', data[4:8])[0]
    if n > 10000 or n == 0:
        return None
    entries = []
    for i in range(n):
        off = struct.unpack('<I', data[8 + i*8 : 12 + i*8])[0]
        size = struct.unpack('<I', data[12 + i*8 : 16 + i*8])[0]
        if off == 0 or size == 0 or off + size > len(data):
            continue
        entries.append((i, off, size))
    os.makedirs(out_dir, exist_ok=True)
    extracted = []
    for i, off, size in entries:
        content = data[off:off+size]
        # detect file type by first 4 bytes
        ext = '.bin'
        if content[:4] == b'PVRT' or content[:4] == b'GBIX':
            ext = '.pvr'
        elif content[:4] == b'TXB0':
            ext = '.tex'
        out_path = os.path.join(out_dir, f'file_{i:04d}{ext}')
        with open(out_path, 'wb') as g:
            g.write(content)
        extracted.append((out_path, off, size))
    return extracted


def unpack_pac_or_pvs(path, out_dir):
    """Generic Capcom container: 4-byte magic + 4-byte count + 8-byte entries (offset,size).
    Probes a few common layouts. Returns list of (file, archive_offset, archive_size, header_size)
    or None if format not recognized."""
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 32:
        return None
    # Try layout 1: u32 count at offset 0, then 8-byte (off, size) entries
    for header_off in (0, 4, 8, 16):
        if header_off + 4 > len(data):
            continue
        count = struct.unpack('<I', data[header_off:header_off+4])[0]
        if count < 2 or count > 5000:
            continue
        entries = []
        ok = True
        ent_base = header_off + 4
        for i in range(count):
            ep = ent_base + i * 8
            if ep + 8 > len(data):
                ok = False; break
            off = struct.unpack('<I', data[ep:ep+4])[0]
            size = struct.unpack('<I', data[ep+4:ep+8])[0]
            if off + size > len(data) or off < ent_base + count*8 or size == 0:
                ok = False; break
            entries.append((i, off, size))
        if not ok or not entries:
            continue
        # Verify by checking first few file magic bytes look like recognizable formats
        valid_magic = 0
        for i, off, size in entries[:5]:
            magic = data[off:off+4]
            if magic in (b'PVRT', b'GBIX', b'TXB0') or magic[:3] in (b'AFS',):
                valid_magic += 1
        if valid_magic == 0:
            continue
        # Success
        os.makedirs(out_dir, exist_ok=True)
        extracted = []
        for i, off, size in entries:
            content = data[off:off+size]
            ext = '.bin'
            if content[:4] in (b'PVRT', b'GBIX'): ext = '.pvr'
            elif content[:4] == b'TXB0': ext = '.tex'
            out_path = os.path.join(out_dir, f'file_{i:04d}{ext}')
            open(out_path, 'wb').write(content)
            extracted.append((out_path, off, size))
        return extracted
    return None


def scan_for_pvrs(path, out_dir):
    """Last-resort: scan a binary for embedded PVRT/GBIX signatures and extract
    each into out_dir. Works for any container format we can't otherwise parse."""
    with open(path, 'rb') as f:
        data = f.read()
    os.makedirs(out_dir, exist_ok=True)
    extracted = []
    i = 0
    while i < len(data) - 16:
        if data[i:i+4] == b'GBIX':
            # GBIX prefix: 4 + 4 (len) + gbix_data + PVRT body
            gbix_len = struct.unpack('<I', data[i+4:i+8])[0]
            pvrt_off = i + 8 + gbix_len
            if pvrt_off + 8 > len(data):
                i += 4; continue
            if data[pvrt_off:pvrt_off+4] != b'PVRT':
                i += 4; continue
            body_len = struct.unpack('<I', data[pvrt_off+4:pvrt_off+8])[0]
            total = pvrt_off - i + 8 + body_len
            if i + total > len(data):
                i += 4; continue
            content = data[i:i+total]
            out_path = os.path.join(out_dir, f'embed_{i:08x}.pvr')
            open(out_path, 'wb').write(content)
            extracted.append((out_path, i, total))
            i += total
        elif data[i:i+4] == b'PVRT':
            body_len = struct.unpack('<I', data[i+4:i+8])[0]
            total = 8 + body_len
            if i + total > len(data):
                i += 4; continue
            content = data[i:i+total]
            out_path = os.path.join(out_dir, f'embed_{i:08x}.pvr')
            open(out_path, 'wb').write(content)
            extracted.append((out_path, i, total))
            i += total
        else:
            i += 1
    return extracted


def unpack_pzz(path, out_dir):
    """Capcom PZZ archive (SF III 3rd Strike):
       128-byte header = 16 (offset, size) u32 LE pairs.
       Each non-empty entry is Naomi-LZSS compressed -> PVR (PVRT or GBIX+PVRT).
    """
    if naomi_lzss is None:
        return None
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 128:
        return None
    header = struct.unpack('<32I', data[:128])
    # Validate: first off must be 128, entries must fit, all data must end at file size
    if header[0] != 0x80:
        return None
    # Validate offsets are monotonically non-decreasing and within file
    last_end = 0x80
    valid_pairs = 0
    for i in range(16):
        off, sz = header[i*2], header[i*2+1]
        if sz == 0:
            continue
        if off != last_end or off + sz > len(data):
            return None
        last_end = off + sz
        valid_pairs += 1
    if valid_pairs == 0:
        return None
    os.makedirs(out_dir, exist_ok=True)
    extracted = []
    for i in range(16):
        off, sz = header[i*2], header[i*2+1]
        if sz == 0:
            continue
        compressed = data[off:off+sz]
        try:
            decomp = naomi_lzss.decompress(compressed)
        except Exception:
            decomp = None
        if not decomp:
            continue
        # Determine extension by decompressed magic
        ext = '.bin'
        if decomp[:4] == b'PVRT' or decomp[:4] == b'GBIX':
            ext = '.pvr'
        out_path = os.path.join(out_dir, f'entry_{i:02d}{ext}')
        with open(out_path, 'wb') as g:
            g.write(decomp)
        extracted.append((out_path, off, sz))
    return extracted if extracted else None


def unpack_slw(path, out_dir):
    """Capcom SLW (Net de Tennis): Naomi-LZSS-compressed concatenated raw
    VRAM textures. No magic, no in-file header — file body IS the LZSS
    stream. Decompresses to (a sequence of) raw twiddled texture blobs,
    typically ARGB4444 (pixfmt 0x02). Width/height/format are supplied
    by the game code, not stored in the file.

    This routine writes the decompressed blob as <basename>.raw and, when
    the decompressed length matches a known (w,h,bpp) pairing, also
    writes best-guess PNG renderings using pvr_codec's pixel decoder.

    Returns list of (output_path, src_off, src_size) like other unpackers.
    """
    if naomi_lzss is None:
        return None
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 4:
        return None
    try:
        dec = naomi_lzss.decompress(data)
    except Exception:
        return None
    # Basic sanity: SLW outputs are >= 1KB and length is even (16bpp word stream)
    if len(dec) < 256 or (len(dec) & 1):
        return None
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    raw_path = os.path.join(out_dir, base + '.raw')
    with open(raw_path, 'wb') as g:
        g.write(dec)
    extracted = [(raw_path, 0, len(data))]

    # Best-guess PNG decode for common dims (16bpp = ARGB4444 / ARGB1555 / RGB565)
    candidates = [
        # (w, h, datafmt) - try square-twiddled for w==h, rectangle-twiddled otherwise
        (512, 512), (256, 256), (128, 128), (64, 64), (32, 32),
        (256, 128), (128, 256), (512, 256), (256, 512),
        (1024, 512), (512, 1024), (1024, 256), (256, 1024),
        (1024, 1024), (640, 512), (512, 640),
    ]
    # Try to render each "slot" the data could contain. If dec is much
    # bigger than any one texture, the first part is the primary texture
    # and remainders may be additional ones.
    try:
        from tex_decode import decode_texture
    except Exception:
        return extracted
    rendered = 0
    cursor = 0
    while cursor < len(dec) and rendered < 16:
        slot = dec[cursor:]
        matched = False
        for w, h in candidates:
            need = w * h * 2
            if need > len(slot):
                continue
            df = 0x01 if w == h else 0x0D
            # Save BOTH ARGB4444 and ARGB1555 renderings since the
            # in-file data doesn't encode the pixfmt — the right one
            # is whichever the game's upload code picks. ARGB4444 fits
            # most UI atlases; ARGB1555 fits text-on-color screens
            # (e.g. NETWK_*.SLW agreement / portal text).
            saved_any = False
            for pf in (0x02, 0x00):
                try:
                    img = decode_texture(slot, 0, w, h, pf, df)
                except Exception:
                    img = None
                if img is None:
                    continue
                out = os.path.join(
                    out_dir,
                    f'{base}_slot{rendered:02d}_off{cursor:08x}_'
                    f'{w}x{h}_pf{pf:02x}_df{df:02x}.png')
                img.save(out)
                extracted.append((out, cursor, need))
                saved_any = True
            if saved_any:
                cursor += need
                rendered += 1
                matched = True
                break
        if not matched:
            break
    return extracted


def slw_repack(src_path, slot_specs, out_path, max_size=None):
    """Pack a list of (PIL.Image, pixfmt, datafmt) slot specs into a Naomi-LZSS
    compressed SLW file at ``out_path``.

    Args:
        src_path: original SLW path (for size budget if max_size is None)
        slot_specs: list of dicts with keys:
            - 'image': PIL.Image (will be coerced to RGBA)
            - 'pixfmt': int (0x00 ARGB1555 / 0x01 RGB565 / 0x02 ARGB4444)
            - 'datafmt': int (0x01 SQUARE_TWIDDLED / 0x0D RECTANGLE_TWIDDLED)
        out_path: destination path
        max_size: max compressed file size; defaults to size of src_path
                  (so the SLW fits the disc's pre-allocated LBA budget)

    Returns:
        (ok: bool, message: str, written: int) — written is final byte count
        on success or 0 on failure. ok is True iff compressed body
        fits within the budget.

    The compressed body is identical in structure to what unpack_slw reads:
    a NaomiLZSS stream of raw concatenated twiddled VRAM blobs in slot order.
    """
    if naomi_lzss is None:
        return (False, 'naomi_lzss module unavailable', 0)
    try:
        from tex_encode import encode_image
    except Exception as e:
        return (False, f'tex_encode unavailable: {e}', 0)

    if max_size is None:
        max_size = os.path.getsize(src_path)

    # 1. Encode each slot to raw twiddled VRAM bytes.
    raw_parts = []
    for i, spec in enumerate(slot_specs):
        img = spec['image']
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        try:
            raw = encode_image(img, spec['pixfmt'], spec['datafmt'])
        except Exception as e:
            return (False, f'slot {i} encode error: {e}', 0)
        raw_parts.append(raw)
    raw_blob = b''.join(raw_parts)

    # 2. Compress.
    compressed = naomi_lzss.compress(raw_blob)

    # 3. Verify against budget.
    if len(compressed) > max_size:
        return (False,
                f'compressed {len(compressed)} bytes exceeds budget {max_size}',
                len(compressed))

    # 4. Write (pad with zeros if shorter than budget to preserve LBA size).
    pad = max_size - len(compressed)
    with open(out_path, 'wb') as g:
        g.write(compressed)
        if pad > 0:
            g.write(b'\x00' * pad)
    return (True, f'ok ({len(compressed)} compressed, {pad} pad)', max_size)


def slw_decode_slots(path, slot_layouts):
    """Decompress an SLW file and decode each slot to a PIL Image per the
    supplied layout. Returns list of (PIL.Image, raw_bytes, pixfmt, datafmt,
    w, h, offset_in_blob).

    slot_layouts: list of dicts with keys 'w','h','pixfmt','datafmt'.
                  offsets are computed sequentially.
    """
    if naomi_lzss is None:
        return None
    try:
        from tex_decode import decode_texture
    except Exception:
        return None
    with open(path, 'rb') as f:
        comp = f.read()
    blob = naomi_lzss.decompress(comp)
    out = []
    cursor = 0
    for layout in slot_layouts:
        w, h = layout['w'], layout['h']
        pf, df = layout['pixfmt'], layout['datafmt']
        need = w * h * 2
        if cursor + need > len(blob):
            out.append(None)
            break
        slot_raw = blob[cursor:cursor + need]
        img = decode_texture(slot_raw, 0, w, h, pf, df)
        out.append({
            'image': img, 'raw': slot_raw,
            'w': w, 'h': h, 'pixfmt': pf, 'datafmt': df,
            'blob_offset': cursor,
        })
        cursor += need
    return out


def auto_unpack(path, out_dir):
    """Try AFS, then PAC/PVS, then PZZ, then SLW, then signature-scan.
       Returns (method, extracted_list)."""
    with open(path, 'rb') as f:
        magic = f.read(4)
    if magic == b'AFS\x00':
        r = unpack_afs(path, out_dir)
        if r is not None: return ('AFS', r)
    # PZZ has no magic - try by extension hint or structural test
    if path.lower().endswith('.pzz'):
        r = unpack_pzz(path, out_dir)
        if r is not None: return ('PZZ', r)
    if path.lower().endswith('.slw'):
        r = unpack_slw(path, out_dir)
        if r is not None: return ('SLW', r)
    r = unpack_pac_or_pvs(path, out_dir)
    if r is not None: return ('PAC/PVS', r)
    # Try PZZ even without extension hint (structural test)
    r = unpack_pzz(path, out_dir)
    if r is not None: return ('PZZ', r)
    # Try SLW (Naomi-LZSS body) as a structural fallback
    r = unpack_slw(path, out_dir)
    if r is not None: return ('SLW', r)
    r = scan_for_pvrs(path, out_dir)
    if r:
        return ('SIGNATURE_SCAN', r)
    return (None, [])


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: archive_unpackers.py <archive_file> <output_dir>')
        sys.exit(1)
    method, ex = auto_unpack(sys.argv[1], sys.argv[2])
    print(f'method={method}  files={len(ex)}')
    for p, off, size in ex[:5]:
        print(f'  {p}  @0x{off:x}  {size} bytes')
