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
    file. Used by the Texture tab's 'Restore Original' button."""
    import shutil
    shutil.copy(baseline_path, rec.file_path)
