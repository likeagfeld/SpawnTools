# Continuing the Spawn translation

If you've landed in this repo because you want to keep the Spawn translation moving forward, here's everything that's actually here and what it's for. **Nothing else is required.**

## What's in this repo

```
SpawnTools/
├── README.md                              you are here, kind of
├── CONTINUING.md                          this file
├── spawntools.bat / spawntools.sh         double-click launchers (Windows / Linux+macOS)
├── requirements.txt                       Pillow + numpy (auto-installed on first run)
│
├── patches/
│   └── Spawn-T-En-Farkus-V0.2.dcp        latest English patch (Farkus V0.2)
│
├── assets/screenshots/                    3 GUI screenshots (used in README)
│
└── spawntools/                            ← the GUI package
    ├── codecs/                            vendored codec library — 10 .py files, ~145 KB
    │   ├── process_game.py                disc extract + in-place patch
    │   ├── pvr_codec.py                   PVR decode/encode (every variant)
    │   ├── tex_decode/encode/repack.py    TXB0 container
    │   ├── naomi_lzss.py                  16-bit LZSS for PZZ/PVZ/3SYS/SLW
    │   ├── archive_unpackers.py           AFS/PAC/PVS/PZZ/SLW
    │   ├── pj_texture.py                  Project Justice 3SYS
    │   ├── redraw_engine.py               sprite-overlay engine
    │   └── jp_en_dict.py                  796-entry JP→EN dictionary
    │
    ├── bundled/spawn_preset/              the actual translation data
    │   ├── preset.json                    file inventory + md5s of 27 modified files
    │   ├── jp_en_dict.json                796 JP→EN entries as JSON
    │   ├── translations.json              ← 1,575 actual EN translations, ready to edit
    │   ├── texture_notes.json             per-modified-texture explanations
    │   └── binary_notes.json              per-modified-binary explanations
    │
    ├── core/                              business logic (disc, encoding, strings, textures, …)
    ├── views/                             4-tab GUI (Workspace, Texture, TextGrid, Build)
    └── widgets/                           reusable Tk widgets
```

## What you don't need to install

- **No `_shared_tools` path** — the codec library is bundled inside `spawntools/codecs/`.
- **No mkisofs / texconv / vqenc** — every operation is pure Python.
- **No xdelta3** — the in-place patch pipeline doesn't need it.

You just need **Python 3.10 or newer**. The launcher auto-installs Pillow + numpy.

## What you DO need (legally we can't ship)

- The original JP Spawn disc image (`disc.gdi` + tracks). You have to source this yourself.

Once you have the disc, three options:

### Option A — start from the existing English patch

1. Apply `patches/Spawn-T-En-Farkus-V0.2.dcp` to your JP disc using any DCP-compatible tool. This produces a patched track03.
2. Drop the patched disc image in a folder with the canonical `disc/`, `extracted/`, `patches/` layout (the campaign convention).
3. Open the disc in SpawnTools (Tab 1 → Browse → pick the `.gdi`). It auto-detects the campaign workspace.
4. Click **Load Spawn Baseline**. Tab 3 fills with all 1,575 English strings ready to edit.

### Option B — start from the bundled translations.json (no patched disc needed)

If you don't want to apply the .dcp first, SpawnTools will still pre-fill the Text Grid from `translations.json`. You'll see + edit Gary's 1,575 EN translations directly. You'll need the JP disc when you eventually click Build (the in-place patch pipeline writes new files into your local `patches/` mirror and bakes them into a new track03).

### Option C — start from scratch from the JP disc

If you want to throw out everything and translate fresh:

1. Open the disc in SpawnTools, let it extract.
2. Tab 1 → **Reset Patches → Stock JP** (wipes `patches/` back to baseline).
3. Tab 3 → scan 1ST_READ.BIN → translate row by row.

## What lives where, by use case

| You want to… | Look at |
|---|---|
| Read the campaign's translation choices | `spawntools/bundled/spawn_preset/translations.json` |
| See the JP→EN dictionary | `spawntools/bundled/spawn_preset/jp_en_dict.json` |
| Know what each modified file's purpose is | `spawntools/bundled/spawn_preset/{texture,binary}_notes.json` |
| Verify the campaign's files haven't been tampered | `spawntools/bundled/spawn_preset/preset.json` (md5s) |
| Apply the patch without using the tool | `patches/Spawn-T-En-Farkus-V0.2.dcp` |
| Understand the codec internals | `spawntools/codecs/` source files (they're heavily commented) |
| Add new translations to the dictionary | edit `spawntools/codecs/jp_en_dict.py` and run `python -m spawntools.bundled.build_spawn_preset` |
| Rebuild the bundled preset after editing | `python -m spawntools.bundled.build_spawn_preset` |
| Boot-test a patched disc | Tab 4 → Build → load the output `.gdi` in Flycast or Redream |

## Hard rules you'll see the tool enforce

These come straight from the campaign's lessons-learned. Don't fight them.

- **Track03 byte size must stay identical** after a patch. The tool refuses to ship a disc image of the wrong size.
- **Every replaced file must be ≤ original**. Pad shorter EN with nulls; never grow.
- **FONT*.PVR, SOFTKEY*.PVR, MOJI*.PVR, MINCHO*.PVR are runtime glyph atlases** — editing them breaks the renderer. The tool flags them as protected.
- **2_DP.BIN, GAME.BIN, GGAM.BIN, MEMDEF.BIN** are deny-listed from the JP scanner. They contain CJK byte sequences as DATA, not strings, and bulk-editing them bricked the disc once (Spawn v20).
- **Pointer relocation** is dry-run-only by default. Same v20 lesson.

## When something doesn't work

- The launcher fails to install dependencies → run `pip install -r requirements.txt` manually
- "Load Spawn Baseline" shows 0 translations → check Tab 1 log; you probably opened a fresh disc with no campaign `patches/` alongside, so the diff found nothing. The bundled `translations.json` fallback will seed them automatically. If it doesn't, the bundled file is corrupted — re-download.
- Build button errors with "track03 size changed" → some file in your `patches/` grew bigger than its baseline. Tab 1 → Validate Integrity to find the culprit.
- Texture preview is black → the file is paletted and the sibling .PVP is missing. Most DPTEX entries need `BANK01.PVP` (not BANK00 — that renders rainbow).

## Reach me

I'm Gary (likeagfeld on GitHub). The Spawn EN patch is by **Farkus** — V0.2 is what ships here.
