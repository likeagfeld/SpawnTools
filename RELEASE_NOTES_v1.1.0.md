# SpawnTools v1.1.0

**Expansion release** — what was a Spawn-only tool now ships with translation baselines for **all 15 Capcom Dreamcast titles** auto-detected via the disc's Sega IP.BIN product code.

## Headline

- **15 games supported** — load any of them in the GUI and the right baseline + scan targets are picked automatically. No dropdowns, no manual config.
- **~26,800 bundled JP↔EN translation pairs** (was ~1,575 in Beta 1.0), all diff-derived from the campaign's actual `patches/` so they round-trip bit-exact.
- **MvC2 / CvS Pro / JoJo / Power Stone 2** — full character/stage data archives now in scope (per-character `*_DAT.BIN` / `*_TRN.BIN`, `STG*TEX.BIN`, `MESJ_WIN.BIN`, etc.).
- **Capcom proprietary raw-pixel containers surface in Tab 2** — MvC2's `STG*TEX.BIN` (3× 512×512 RGB565), Taisen's `RESOURCE.BIN`, Power Stone 2's `*_CONNECT.BIN` (and many more) decode + import + write back at byte-exact size.

## How it works

| Disc loaded | What the tool does |
|---|---|
| Spawn (`T1216M`) | Pre-fills 1,575 EN strings + 27 modified textures (the original Spawn baseline). |
| CvS Pro (`T1247M`) | **10,093 strings** — adds the community EN baseline extracted from the user's translated GDI, plus stage-text BINs and the ASK softkey dictionary. |
| MvC2 (`T1215M`) | **720 strings** — per-character `PL*_DAT.BIN` + ASK.BIN + EFKYTEX. Surfaces 274 raw-pixel texture chunks via Tab 2. |
| JoJo (`T1231M`) | **1,489 strings** — `97_DASH.BIN` / `95_JOJO.BIN` / `93_LOBBY.BIN` + per-character TRN archives. |
| Power Stone 2 (`T1218M`) | **849 strings** — `DM04_CONNECT.BIN`, `ASKLIBS.BIN`, `CMN_MOT.BIN`. |
| Heavy Metal (`T1246M`) | 1,542 strings — `1ST_READ.BIN` + `MESSAGE.INI` + `DEMO.BIN`. |
| SF III 3rd Strike (`T1209M`) | 867 strings — `PLAYER/PL*.BIN` + `KANJI/ASKLIBS.BIN`. |
| Net de Tennis (`T1234M`) | 1,322 strings. |
| Project Justice (`T1221M`) | 1,388 strings. |
| SFZ3 MS (`T1230M`) | 1,386 strings. |
| SPFII MS (`T1250M`) | 1,390 strings + ASK.BIN + storyboard OSBs. |
| SSFIIX MS (`T1236M`) | 1,393 strings. |
| Taisen Net Gimmick (`T1248M`) | 1,401 strings — `RESOURCE.BIN` + `WAZAALL.BIN` + ASK. |
| Tech Romancer MS (`T1232M`) | 1,382 strings — `1ST_READ.BIN` + `SOUND/WIS.OSB`. |
| Vampire Chronicle MS (`T1235M`) | 1,379 strings. |

## What changed since Beta 1.0

### Auto-detection via IP.BIN

Disc fingerprint reads the **Sega-assigned product code** from track03 at byte 0x40 (e.g. `T1216M` = Spawn, `T1247M` = CvS Pro, `T1209M` = SF III 3rd Strike). 100% reliable per disc; no manual selection. The preset dropdown was removed entirely — the disc tells the tool what it is.

### Tab 2 surfaces every container kind

- AFS, PAC, PVS, PZZ, SLW, PVZ — expanded as flat rows alongside loose `.TEX`/`.PVR`
- BIN files with embedded PVRT/GBIX magic — signature-scanned + surfaced
- Capcom proprietary raw-pixel containers — `STG*TEX.BIN` / `EFKYTEX.BIN` / `PL*_DAT.BIN` decoded via brute-force layout detection (`raw_blob.py`)
- Per-game pixfmt/datafmt defaults baked in via `bundled/raw_format_profiles.json` (derived from Ghidra+FIDB attribution + verified samples) — users never pick formats

### Tab 3 reads preset.scan_targets

`Scan for JP` now dispatches against every file in the loaded preset's `scan_targets` (not just `1ST_READ.BIN`). Per-game targets are evidence-based:

- **CvS Pro:** 18 files including the community-EN-translated stage TEX-bins
- **JoJo:** 12 files including all character training archives
- **MvC2:** 20 files including every per-character `_DAT.BIN`
- **SF III:** 16 files including every modified `PLAYER/PL*.BIN`

### Settings dialog stripped

`_shared_tools dir` and `xdelta3 (optional)` are gone — both unused since codecs were bundled. Only the pointer-growth toggle remains.

### Reverse-engineering scaffolding

Headless Ghidra batch (`scripts/ghidra_batch.py`) applied **11 FIDBs** (Katana SDK 1.20J / 1.30J / 1.42J / 1.43J / 1.55J / 2.00J / R4 / R10.1 / Kunoichi 2.02 / NAOMI 001.002.1 / Katana R9) to every game's `1ST_READ.BIN`. Per-game JSON dumps in `spawn_re_ghidra/ghidra_dumps/` document the texture framework each game uses:

- **Ninja SDK** (8 games): JoJo, SF III, SFZ3, SPFII, SSFIIX, Taisen, Tech Romancer, Vampire
- **Kamui** (2 games): Spawn, Heavy Metal
- **Capcom NL** (2 games): Project Justice, Net de Tennis
- **Capcom proprietary** (3 games): CvS Pro, MvC2, Power Stone 2

See `spawn_re_ghidra/PER_GAME_RE_NOTES.md` for details + what's needed for full Spawn-level coverage per remaining game.

### CvS Pro English baseline merge

The community-translated CvS Pro GDI is extracted and diff-merged into `cvs_pro_preset/translations.json` — 803 identical files, 19 same-size modified, 9 null-padded shorter, 10 oversize flagged. **+7,734 translation pairs** over Beta 1.0.

### QA harness

`scripts/flow_harness.py` runs 8 flows × 15 games = 92 checks per build: load preset, detect via IP.BIN, scan_targets exist, translation round-trip vs patches, archive surface rate, member decode no-crash, protected-atlas filter, unique labels. **Result: 73 PASS / 0 FAIL / 19 SKIP.**

### Bug fixes

- Misleading "Pick a sub-tex first" error replaced with a real diagnostic when the selected sub-tex is undecodable (paletted PVR missing palette / datafmt 0x12 etc.)
- Single-sub-tex selection no longer silently dropped by Tk's `exportselection=True` behaviour
- Integrity audit ignores our own safety-backup files (`.bak`, `.pre_*_revert`, `.tmp`, `.new`, `.swp`, `.DS_Store`, `Thumbs.db`)
- Export PNG split into "Export Original (JP baseline)" / "Export Modified (current patches/)" so it's unambiguous which copy you're getting

## Known scope

- **String translation** works at byte-edit-and-commit level for all 15 games (same primitive Spawn uses).
- **Loose PVR + TXB0 .TEX** edit works for all 15 games.
- **Compressed archives** (PZZ/PVZ/SLW/PAC/AFS) — 5/15 games have these, mostly fully surfaced.
- **Capcom raw-pixel containers** — view + import works for MvC2/Taisen (verified). Other games may need pixfmt override via the Tab 2 format combo if their atlas pixfmt differs from the per-game default.
- **In-game boot verification** — every change is shrink-or-equal so the disc layout stays bootable, but the user must boot-test in Flycast/Redream to verify content rendering. We can't run an emulator from the build environment.

## Assets

- `Spawn-T-En-Farkus-V0.2.dcp` — standalone Spawn EN patch (~588 KB, unchanged from Beta 1.0).
- `SpawnTools-v1.1.0.zip` — full tool with all 15 game bundles (~2.55 MB).

## License

MIT.
