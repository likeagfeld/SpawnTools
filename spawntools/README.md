# SpawnTools

Production translation suite for **Spawn — In the Demon's Hand (JP, Capcom 2000)**, built on the proven `_shared_tools/` codecs used to translate.

```
   python -m spawntools
```

## What this is

A four-tab Tkinter IDE that wraps the canonical translation pipeline:

1. **Workspace & QA** — Open `disc.gdi`, build `backups/`, run integrity checks (disc-vs-patches md5 sync, byte-budget audit, broken-pointer detector).
2. **Texture Workbench** — Original vs Translated preview, Export PNG, Import & Auto-Convert (re-encode with the original pixfmt/datafmt header), Restore Original.
3. **Text & Pointer Grid** — Scan 1ST_READ.BIN for JP strings, view the spreadsheet (Offset | Pointer | Raw Hex | Translated String | Byte Status), edit one row at a time, apply with null-bounded safety.
4. **Master Build** — Console log of the patched-track03 re-pack and `.gdi` generation.

## Deviations from the original spec — and why

The user-supplied spec contained four assumptions that are **wrong for Spawn specifically** and are flagged as hard rules in the `dreamcast-translator` skill. SpawnTools corrects each rather than implementing them as requested:

### 1. No AFS engine for Spawn (Project Justice uses AFS, Spawn does not)

The spec asks for AFS Table-of-Contents management with 2048-byte sector alignment. Spawn ships **zero `.AFS` files**. The 167-pair AFS hot-swap pattern belongs to Project Justice (`HUM_TC.AFS`, etc).

**What we do**: `core/afs.py` auto-detects AFS files in the extracted dir; if none are found, the AFS tab control is hidden in the GUI. Project Justice (or other games dropped in) gets AFS support automatically.

### 2. Pointer relocation is dry-run-only

The spec asks for a "Relocation Engine" that finds null padding, writes a longer string there, and updates the pointer at the original site. **The campaign rule (hard rule, top of skill): "NEVER grow a patched file beyond its original byte size."**

Why: Spawn v20 bricked the disc by doing aggressive single-CJK-byte-pair replacements. The fix (v22) requires per-occurrence context checks and shrink-only mode. Pointer relocation in a packed SH-4 binary risks overlapping with code, naturally-occurring data bytes, or another pointer table. We've seen this fail.

**What we do**: `core/pointers.py` ships a `PointerAuditor` that reports candidate null-padding regions and would-be-overlap warnings, but the write path is gated behind a config flag (`config.allow_pointer_growth = False` by default). The Text Grid's "Byte Status" column shows pointer-overflow risk, but Save only commits shrink-or-equal-length replacements with null padding.

### 3. No external `mkisofs.exe` / `texconv.exe` / `vqenc.exe`

The spec asks for these as subprocess dependencies. We use the proven Python implementations in `_shared_tools/`:

- **Texture decode/encode** — `pvr_codec.py` (handles ARGB1555, RGB565, ARGB4444, PAL_4BPP, PAL_8BPP, twiddling, VQ, mipmap chains, the JoJo datafmt 0x12 variant, rectangle-twiddled non-square)
- **TEX repack** — `tex_repack.py` (TXB0 container, sentinel handling)
- **Disc patch** — `process_game.patch_iso` (in-place track03 writer that preserves LBA layout)
- **GDI sidecar** — `gdi_builder.generate_gdi` (mirrors source GDI track entries, swaps track03 filename)

mkisofs **would destroy Dreamcast LBA layout** (it rebuilds ISO9660 from scratch with new extents). The mandate is in-place patching: every file rewritten at its original LBA so track03.iso byte size stays identical. `process_game.patch_iso` does exactly that — it's the pipeline that built the existing Spawn patch.

### 4. Encoding engine is cp932 + Capcom helpers, not generic .tbl

Spawn's text is **already cp932 (Shift-JIS)**. There's no game-specific custom encoding that needs a .tbl mapper. What we *do* need is the well-known set of Capcom-specific tokens:

- Full-width Latin (`Ｉ Ｄ ０－９ Ｃ Ｏ Ｍ ＋`) — separate codepoints from ASCII, the dict must include both
- Control bytes for color (`$0`..`$9`) and button glyphs (A/B/X/Y icons)
- Line-break auto-calc based on the renderer's pixel-width metrics

`core/encoding.py` implements these on top of cp932. A `.tbl` loader is also supported for any future game that uses a custom encoding, but Spawn doesn't.

## Hard rules enforced (from the skill)

- Track03.iso byte size must remain unchanged after re-patch → enforced in `core/disc.py:patch_and_verify()`
- Every replaced file must be `≤` original byte size → enforced in `core/textures.py:save_subtex()` and `core/strings.py:commit_translation()`
- FONT/SOFTKEY/MOJI/MINCHO PVRs are auto-excluded from the Texture tab listing
- No Tesseract OCR anywhere — the Texture tab requires the user to type the English; no auto-recognition
- Backups directory created on every disc open

## Project layout

```
spawntools/
├── __init__.py
├── __main__.py            # python -m spawntools
├── app.py                 # 4-tab Tk root
├── config.py              # Config class (shared_tools path, optional ext-tool paths)
├── core/
│   ├── disc.py            # GDI load, integrity, patch+verify, GDI sidecar
│   ├── encoding.py        # cp932 + full-width Latin + Capcom control codes + line-break calc
│   ├── strings.py         # JP scanner, null-bounded safe replace
│   ├── textures.py        # PVR / TEX wrapper around _shared_tools/pvr_codec + tex_decode/repack
│   ├── pointers.py        # Pointer auditor (dry-run-only by default)
│   └── afs.py             # AFS support (no-op when zero AFS files in extracted dir)
├── views/
│   ├── workspace.py       # Tab 1: open GDI, integrity, backups
│   ├── textures.py        # Tab 2: side-by-side preview, import/export
│   ├── text_grid.py       # Tab 3: spreadsheet view of every translatable string
│   └── master_build.py    # Tab 4: console log, GENERATE PATCHED GDI
└── widgets/
    ├── log_console.py     # the tk.Text console widget used by Tab 4 + Tab 1 integrity
    └── tooltip.py         # hover tooltip
```

## Required dependencies

- Python 3.10+
- Pillow, numpy
- The `_shared_tools/` codec library — set its path in Settings on first launch
