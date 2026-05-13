# SpawnTools — Beta 1.0

The first public Beta of SpawnTools — a GUI for translating **Spawn: In the Demon's Hand** (Capcom, 2000, Dreamcast).

Built on the codec library used to make the existing Spawn patch. The Spawn baseline ships with the tool: open the disc, click **Load Spawn Baseline**, and the spreadsheet fills with 1,575 pre-translated English strings derived directly from the existing patches.

## Just want the Spawn patch?

If you don't need the tool — just the English patch itself — download:

- **`Spawn-T-En-Farkus-V0.2.dcp`** (~588 KB) — Dreamcast patch file (zip-format). Apply with any DCP-compatible tool against the original JP Spawn disc. T-En patch by **Farkus**, version **V0.2**, KDDI Online (Japan) build.

Otherwise download `SpawnTools-v1.0.0-beta1.zip` below for the GUI.

## How to run

- **Windows:** double-click `spawntools.bat`
- **Linux / macOS:** `./spawntools.sh`

The launcher auto-detects Python 3.10+, installs Pillow + numpy on first run, and starts the GUI. Codecs and the Spawn baseline are bundled — no external path config required.

## Four tabs

1. **Workspace & QA** — Open a Dreamcast `.gdi`. Auto-detects existing campaign workspaces so your `patches/` becomes the baseline you edit on top of. Integrity audit, backups, reset-to-stock.
2. **Texture Workbench** — Side-by-side Original vs Translated preview for every `.TEX` / `.PVR`. Color-coded list shows `●` modified vs `○` stock at a glance, with All / Modified / Stock filter. Per-file campaign notes. Export PNG, Import & Auto-Convert (re-encodes with the original pixfmt/datafmt header), Revert to JP.
3. **Text & Pointer Grid** — Spreadsheet of every JP string in `1ST_READ.BIN` and `MESSAGE.INI`. Click **Load Spawn Baseline** once and the grid fills with the campaign's English translations. Edit any row, revert any row to JP, accept dictionary suggestions one-click. Byte-budget meter prevents oversize commits.
4. **Master Build** — Pre-flight integrity check → in-place track03 patch → md5-verified disc-vs-patches sync → sidecar `.gdi`.

## What's bundled

- **`spawntools/codecs/`** — vendored copy of the canonical codec library (process_game, pvr_codec, tex_decode/encode/repack, naomi_lzss, archive_unpackers, redraw_engine). 10 modules, ~145 KB.
- **`spawntools/bundled/spawn_preset/`** — 796-entry JP→EN dictionary, per-file campaign notes, file inventory with md5s.
- **`spawntools/`** — the GUI: config + 4 tabs + core modules (disc, encoding, strings, textures, pointers, afs, preset).

## Hard rules enforced

- Track03 byte size invariant after every patch
- Every replaced file ≤ original byte size, no exceptions
- FONT/SOFTKEY/MOJI/MINCHO PVRs flagged as protected (runtime glyph atlases — editing them breaks the renderer)
- 2_DP.BIN / GAME.BIN / GGAM.BIN / MEMDEF.BIN excluded from the JP scanner (they contain CJK bytes as data, not strings)
- Pointer relocation is dry-run-only by default (Spawn v20 bricked memory-card boot doing aggressive byte writes)

## Tested against

The real Spawn campaign workspace: `Spawn — In the Demon's Hand (JP)`. Loading the baseline against the campaign's existing `patches/` derives **1,575 EN translations** + **56 dictionary hints** in seconds. Integrity audit reports 27 modified files, 0 oversize, 0 orphans, safe to build.

## Known limitations / "Beta" caveats

- AFS archive support exists but Spawn doesn't use AFS — it's there for future games (e.g., Project Justice has 167 JP/EN pairs in AFS).
- Pointer relocation engine is **dry-run only** by default. The toggle to enable it is in Settings, but Spawn v20 demonstrated this is risky territory.
- The bundled dictionary is Spawn-validated; using SpawnTools against other DC titles may need additional dictionary entries.
- Texture preview canvas does not yet show the in-game render coordinates / quad layout — you see the atlas as decoded, not how it composes on screen.

## Spec deviations (documented)

If you read the original spec for this tool: it asked for an AFS engine, an external `mkisofs.exe` / `texconv.exe` / `vqenc.exe` subprocess pipeline, a generic `.tbl` table-based encoder, and a pointer-relocation engine. SpawnTools corrects each where they're wrong for Spawn specifically (Spawn has no AFS files; mkisofs would destroy DC LBA layout; Spawn's text is native cp932; aggressive pointer growth bricked v20). Full reconciliation in `spawntools/README.md`.

## License

MIT.
