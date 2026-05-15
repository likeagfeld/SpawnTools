"""Texture I/O for the Workbench — thin wrapper around _shared_tools.

The campaign's proven texture pipeline:

  • `.TEX` files = Capcom's TXB0 container. N sub-textures packed together,
    each with its own pixfmt/datafmt header. We decode via
    `_shared_tools/tex_decode.py:parse_tex()` and re-pack via
    `_shared_tools/tex_repack.py:TexFile`. The repack MUST match original
    byte size (boot rule).

  • `.PVR` files = standalone Dreamcast textures. Pixel formats include
    ARGB1555 / RGB565 / ARGB4444 (16bpp) and PAL_4BPP / PAL_8BPP (paletted
    via a sibling `.PVP` file). Data formats include SQUARE_TWIDDLED,
    SQUARE_TWIDDLED_MIPMAP, VQ, VQ_MIPMAP, RECTANGLE, RECTANGLE_TWIDDLED,
    plus JoJo's datafmt 0x12 (ARGB1555 SQUARE_TWIDDLED_MIPMAP, Y-first twiddle).
    `pvr_codec.py` handles them all.

  • Paletted PVRs auto-load their sibling `.PVP`. The DP3 cluster
    (TAG_SU.PVR + 6 siblings) uses BANK01.PVP (NOT BANK00 — that renders
    rainbow).

Hard rule enforced: every re-encode MUST equal the original byte size.
`encode_pvr_inplace` and `tex_repack.save` both already do this. We add a
SECOND guard here that asserts on the file size after write.

Auto-classify Capcom protected atlases that the campaign rule says NEVER
touch (FONT, SOFTKEY, MOJI, MINCHO). The Texture tab filters those out of
the editable list — they're shown but flagged read-only.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from PIL import Image


# Atlases the runtime renderer indexes into — translating them breaks the
# game's text rendering. The skill explicitly enumerates these.
PROTECTED_ATLAS_NAMES = (
    'FONT.PVR', 'FONT0.PVR', 'FONT1.PVR',
    'SOFTKEY', 'MOJI', 'MINCHO_A.PVR', 'MINCHO_B.PVR',
)


@dataclass
class TextureRecord:
    """One sub-texture or one whole PVR — abstracted as a uniform record."""
    file_path: Path
    sub_index: int            # 0..N-1 for TEX; 0 for PVR
    width: int
    height: int
    pixfmt: int               # 0x00..0x06 — see encoding.py
    datafmt: int              # 0x01, 0x03, 0x07, 0x09, 0x0D, 0x12...
    image: Optional[Image.Image]   # decoded RGBA, or None if undecodable

    @property
    def is_paletted(self) -> bool:
        return self.pixfmt in (0x05, 0x06)

    @property
    def is_vq(self) -> bool:
        return self.datafmt in (0x03, 0x04)

    @property
    def is_mipmap(self) -> bool:
        return self.datafmt in (0x02, 0x04, 0x07, 0x12)


def is_protected(file_path: Path) -> bool:
    """True if this file is in the do-NOT-touch list (runtime glyph atlas)."""
    name = file_path.name.upper()
    for pat in PROTECTED_ATLAS_NAMES:
        if pat.upper() in name:
            return True
    return False


def load(path: Path) -> list[TextureRecord]:
    """Decode a `.TEX` or `.PVR` into one or more TextureRecords."""
    suffix = path.suffix.upper()
    out: list[TextureRecord] = []
    if suffix == '.TEX':
        import tex_decode
        recs = tex_decode.parse_tex(str(path))
        for r in recs:
            i, w, h, pf, df, img = r
            # The 0xFF/0xFF sentinel that ends a TEX table — skip
            if pf == 0xFF and df == 0xFF:
                continue
            out.append(TextureRecord(
                file_path=path, sub_index=i, width=w, height=h,
                pixfmt=pf, datafmt=df, image=img,
            ))
    elif suffix == '.PVR':
        import pvr_codec
        img, info = pvr_codec.decode_pvr(str(path))
        if info:
            out.append(TextureRecord(
                file_path=path, sub_index=0,
                width=info.get('width', 0), height=info.get('height', 0),
                pixfmt=info.get('pixfmt', 0), datafmt=info.get('datafmt', 0),
                image=img,
            ))
    return out


def _ensure_codecs_on_path():
    import sys
    codecs_dir = Path(__file__).resolve().parent.parent / 'codecs'
    if str(codecs_dir) not in sys.path:
        sys.path.insert(0, str(codecs_dir))


def load_archive_member(member) -> list[TextureRecord]:
    """Decode the bytes inside an archive member into TextureRecords.

    Handles three shapes:
      - PVRT/GBIX-headered bytes (regular PVR member from AFS/PAC/PVS/PZZ/PVZ)
      - RAW raw-pixel bytes (Capcom proprietary BINs — STG*TEX, EFKYTEX,
        PL*_DAT, etc.) decoded via the stored raw_* hints.
      - SLW raw VRAM blob with no dims — returned empty.
    """
    if member.archive_kind == 'SLW':
        return []  # raw VRAM blob — no usable PVR header

    _ensure_codecs_on_path()
    # RAW: dims/format were determined heuristically at list_members time.
    if member.archive_kind == 'RAW' and member.raw_width and member.raw_height:
        import tex_decode
        try:
            img = tex_decode.decode_texture(
                member.pvr_bytes, 0,
                member.raw_width, member.raw_height,
                member.raw_pixfmt, member.raw_datafmt,
            )
        except Exception:
            img = None
        return [TextureRecord(
            file_path=member.archive_path, sub_index=member.member_id,
            width=member.raw_width, height=member.raw_height,
            pixfmt=member.raw_pixfmt, datafmt=member.raw_datafmt,
            image=img,
        )]

    pvr_bytes = member.pvr_bytes
    if pvr_bytes[:4] not in (b'PVRT', b'GBIX'):
        return []
    # Write to a temp file because the vendored pvr_codec is file-path-driven.
    import tempfile, pvr_codec
    with tempfile.NamedTemporaryFile(suffix='.pvr', delete=False) as tf:
        tf.write(pvr_bytes)
        tmp_path = Path(tf.name)
    try:
        img, info = pvr_codec.decode_pvr(str(tmp_path))
    finally:
        try: tmp_path.unlink()
        except OSError: pass
    if not info:
        return []
    return [TextureRecord(
        file_path=member.archive_path, sub_index=member.member_id,
        width=info.get('width', 0), height=info.get('height', 0),
        pixfmt=info.get('pixfmt', 0), datafmt=info.get('datafmt', 0),
        image=img,
    )]


def import_png_replace_member(member, png_path: Path) -> dict:
    """Re-encode the PNG into a PVR using the member's original pixfmt/datafmt,
    then write back via `archives.replace_member` which preserves archive byte
    size."""
    from . import archives
    import tempfile, pvr_codec
    new = Image.open(png_path).convert('RGBA')

    # Write the original PVR to disk so we can reuse encode_pvr_inplace
    with tempfile.NamedTemporaryFile(suffix='.pvr', delete=False) as tf:
        tf.write(member.pvr_bytes)
        tmp_path = Path(tf.name)
    try:
        info = pvr_codec.parse_pvr(str(tmp_path))
        if not info:
            raise RuntimeError('parse_pvr returned None for archive member.')
        w = info.get('width', 0)
        h = info.get('height', 0)
        resized = False
        if (w, h) != new.size:
            new = new.resize((w, h), Image.LANCZOS)
            resized = True
        ok = pvr_codec.encode_pvr_inplace(str(tmp_path), new, info)
        if ok is False:
            raise RuntimeError('encode_pvr_inplace failed for archive member.')
        new_pvr_bytes = tmp_path.read_bytes()
    finally:
        try: tmp_path.unlink()
        except OSError: pass

    result = archives.replace_member(member, new_pvr_bytes)
    if not result.get('ok'):
        raise RuntimeError(result.get('reason', 'replace_member failed'))
    return {
        'orig_size': len(member.pvr_bytes), 'new_size': result['new_size'],
        'pixfmt': info.get('pixfmt', 0), 'datafmt': info.get('datafmt', 0),
        'paletted': False, 'is_vq': info.get('datafmt', 0) in (0x03, 0x04),
        'resized': resized, 'archive_size': result.get('archive_size'),
    }


def export_png(rec: TextureRecord, out_path: Path) -> None:
    """Save the decoded RGBA image to disk for external editing."""
    if rec.image is None:
        raise RuntimeError(f'sub_{rec.sub_index} undecodable — cannot export')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rec.image.save(out_path)


def import_png_replace(rec: TextureRecord, png_path: Path) -> dict:
    """Read PNG, auto-resize to match the sub-tex dimensions, and write back
    to the on-disk file using the SAME pixfmt/datafmt as the original.

    Hard rule: the re-encoded file MUST equal its original byte size.

    Returns: { 'orig_size': N, 'new_size': M, 'pixfmt': pf, 'datafmt': df,
               'paletted': bool, 'is_vq': bool, 'resized': bool }
    """
    if is_protected(rec.file_path):
        raise RuntimeError(
            f"{rec.file_path.name} is a protected runtime glyph atlas — "
            f"refusing to touch it. (Touching FONT/SOFTKEY/MOJI/MINCHO will "
            f"break the game's text renderer.)"
        )
    new = Image.open(png_path).convert('RGBA')
    resized = False
    if new.size != (rec.width, rec.height):
        new = new.resize((rec.width, rec.height), Image.LANCZOS)
        resized = True

    suffix = rec.file_path.suffix.upper()
    orig_size = rec.file_path.stat().st_size

    if suffix == '.TEX':
        import tex_repack, os
        t = tex_repack.TexFile.load(str(rec.file_path))
        t.replace(rec.sub_index, new)
        tmp = str(rec.file_path) + '.new'
        t.save(tmp)
        new_size = Path(tmp).stat().st_size
        if new_size != orig_size:
            os.remove(tmp)
            raise RuntimeError(
                f"Re-encoded TEX size {new_size} != original {orig_size}. "
                f"This would change track03 byte size — refusing to write."
            )
        os.replace(tmp, str(rec.file_path))
    elif suffix == '.PVR':
        import pvr_codec
        info = pvr_codec.parse_pvr(str(rec.file_path))
        if not info:
            raise RuntimeError('parse_pvr returned None — not a valid PVR?')
        ok = pvr_codec.encode_pvr_inplace(str(rec.file_path), new, info)
        if ok is False:
            raise RuntimeError(
                'encode_pvr_inplace failed (size mismatch, missing palette, '
                'or unsupported pixfmt/datafmt combo).'
            )
        new_size = rec.file_path.stat().st_size
        if new_size != orig_size:
            raise RuntimeError(
                f"PVR size changed ({orig_size} -> {new_size}) after encode."
            )
    else:
        raise RuntimeError(f'Unsupported texture format: {suffix}')

    return {
        'orig_size': orig_size, 'new_size': new_size,
        'pixfmt': rec.pixfmt, 'datafmt': rec.datafmt,
        'paletted': rec.is_paletted, 'is_vq': rec.is_vq, 'resized': resized,
    }


def restore_original(rec: TextureRecord, baseline_path: Path) -> None:
    """Copy the baseline (extracted/) copy over the patches/ copy of the
    file. Used by the Texture tab's 'Restore WHOLE file' button. NOTE:
    this throws away ALL sub-tex edits in a multi-sub-tex container. For
    per-sub-tex revert use restore_subtex_from_baseline()."""
    import shutil
    shutil.copy(baseline_path, rec.file_path)


def restore_subtex_from_baseline(rec: TextureRecord, baseline_path: Path) -> dict:
    """Restore ONE sub-texture inside a .TEX container back to its
    extracted/ baseline pixels, keeping every other sub-texture's
    modifications intact.

    For .PVR files (single-image, no sub-textures) this falls through to
    a whole-file restore.

    Returns: {'kind': 'tex'|'pvr', 'sub_index': N, 'size_unchanged': bool}.
    """
    suffix = rec.file_path.suffix.upper()
    orig_size = rec.file_path.stat().st_size

    if suffix == '.PVR':
        import shutil
        shutil.copy(baseline_path, rec.file_path)
        new_size = rec.file_path.stat().st_size
        return {'kind': 'pvr', 'sub_index': rec.sub_index,
                'size_unchanged': new_size == orig_size}

    if suffix == '.TEX':
        # Byte-slice approach: TXB0 containers have identical record-table
        # layout between extracted/ and patches/ (since the campaign honours
        # shrink-or-equal). For sub_N we look up its pixel-data offset+size
        # in the baseline TXB0 header and copy those exact bytes over the
        # patches/ copy at the same offset. This sidesteps the bundled
        # decoder's RECTANGLE_TWIDDLED weak path (sub-textures with
        # non-square dims + datafmt 0x0d decode to None but their pixel
        # bytes are perfectly valid on disc).
        import struct
        baseline_bytes = baseline_path.read_bytes()
        patches_bytes  = rec.file_path.read_bytes()
        if baseline_bytes[:4] != b'TXB0' or patches_bytes[:4] != b'TXB0':
            raise RuntimeError(f'{rec.file_path.name}: not a TXB0 container')
        if len(baseline_bytes) != len(patches_bytes):
            raise RuntimeError(
                f'Size mismatch: baseline={len(baseline_bytes)} vs '
                f'patches={len(patches_bytes)}. Cannot byte-revert.'
            )
        n_records  = struct.unpack('<I', baseline_bytes[4:8])[0]
        data_start = struct.unpack('<I', baseline_bytes[8:12])[0]
        # Each record is 16 bytes starting at offset 16: u16 w, u16 h,
        # u8 pixfmt, u8 datafmt, u16 pad, u32 offset, u32 pad
        REC_BASE = 16
        REC_SIZE = 16
        # Find this sub_index's pixel region (offset + size). Size = next
        # record's offset minus this one's, or (file_end - this_offset)
        # for the last non-sentinel record.
        my_offset = my_end = None
        last_real_offset = None
        # Build a sorted list of (sub_index, file_offset) of real records.
        real = []
        for i in range(n_records):
            base = REC_BASE + i * REC_SIZE
            w  = struct.unpack('<H', baseline_bytes[base:base+2])[0]
            h  = struct.unpack('<H', baseline_bytes[base+2:base+4])[0]
            pf = baseline_bytes[base+4]
            df = baseline_bytes[base+5]
            off_rel = struct.unpack('<I', baseline_bytes[base+8:base+12])[0]
            if pf == 0xFF and df == 0xFF: continue   # sentinel
            real.append((i, data_start + off_rel))
        real.sort(key=lambda x: x[1])
        # Where does this sub_index live?
        for j, (idx, off) in enumerate(real):
            if idx == rec.sub_index:
                my_offset = off
                # End is the next real record's offset, or end of file.
                if j + 1 < len(real):
                    my_end = real[j + 1][1]
                else:
                    my_end = len(baseline_bytes)
                break
        if my_offset is None:
            raise RuntimeError(
                f'Sub_{rec.sub_index} not found in baseline {baseline_path.name}'
            )
        # Slice the pixel bytes from baseline and overwrite patches.
        block = baseline_bytes[my_offset:my_end]
        new_patches = (patches_bytes[:my_offset] + block +
                       patches_bytes[my_end:])
        if len(new_patches) != orig_size:
            raise RuntimeError(
                f'Byte-slice replace would change file size '
                f'({orig_size} -> {len(new_patches)})'
            )
        rec.file_path.write_bytes(new_patches)
        return {'kind': 'tex', 'sub_index': rec.sub_index,
                'size_unchanged': True,
                'bytes_slice': f'0x{my_offset:x}..0x{my_end:x}'}

    raise RuntimeError(f'Unsupported file kind for sub-tex revert: {suffix}')
