# SpawnTools v1.2.0

**Texture baseline + .dcp pipeline + Spawn icon.** Build on v1.1.0's 15-game expansion with the missing pieces users hit immediately.

## Headline

- **Tab 2 finally shows ● modified textures after Load Baseline** — Spawn's 22 pre-built EN textures (`LOBBY37/38/40.TEX`, `CFGJP/CFGUS.TEX`, `COCKPITJP.TEX`, all `DPTEX/*.PVR`, `SELSPR2JP/VMTEXJP/VSJP/WARNING.TEX`, `GGAM.BIN`) ship inside the release zip and get copied into your `patches/` automatically.
- **Two `.dcp` buttons on Tab 1**: `Fetch latest from GitHub` (downloads the canonical EN patch for the auto-detected game) and `Browse local .dcp…` (apply any .dcp you have).
- **.dcp apply auto-chains Load Baseline** so Tab 3 immediately shows the EN strings the patch just wrote into `patches/`.
- **Per-sub-texture revert** — undo a single sub-tex inside a multi-sub-tex `.TEX` container without losing other modifications.
- **Spawn icon** wired as the window/taskbar/dock icon everywhere Tk allows.

## What was broken in v1.1.0

| Symptom | Cause | Fix |
|---|---|---|
| Tab 2 said 0 modified on fresh project | Bundled translations were string-only; no modified-texture bytes shipped | `bundled/spawn_preset/modified_files/` ships 22 raw EN textures (9.2 MB); Load Baseline copies them into `patches/` |
| Tab 3 said 0 done rows after Load Baseline | `apply_preset` INSERT-then-ignore swallowed every bundled translation at the UNIQUE constraint | Upsert: on conflict, UPDATE existing row's `en_text` + `status='done'` |
| `Restore Original` / `Revert this file` reverted the **whole** `.TEX` | No per-sub-tex code path | New `restore_subtex_from_baseline()` byte-slices a single sub-tex from baseline TXB0 |
| Integrity audit flagged our own safety-backup files as orphans | No skip list | `.bak`, `.pre_*_revert`, `.tmp`, `.new`, `.swp`, `.DS_Store`, `Thumbs.db` skipped |

## What's new functionally

### .dcp apply pipeline (`spawntools/core/dcp.py`)

- `apply_dcp_from_file(path, extracted, patches, log)` — reads a Dreamcast Patcher `.dcp` (zip of `<rel>.xdelta` files), applies each via `pyxdelta`, writes patched output to `patches/<rel>`.
- `fetch_and_apply_latest(slug, extracted, patches, log)` — downloads from a per-game URL registered in `DCP_URLS` (Spawn ships pointing at the SpawnTools release asset), then applies.
- Tab 1 buttons schedule `_on_load_preset()` after apply so Tab 3 sees the EN strings.

### Bundled modified-textures pipeline (`scripts/bundle_modified_files.py`)

Build-time script: applies a game's `.dcp` via `pyxdelta` against `extracted/` and stages every modified file (filtered for `.TEX`/`.PVR`/`.INI` — skips multi-MB executables like `GAME.BIN`/`MEMDEF.BIN`) into `bundled/<slug>_preset/modified_files/`.

End users don't need `pyxdelta` to see these — they're already plain bytes inside the release zip. `pyxdelta` is only required at runtime if the user wants to apply a different `.dcp` via the Tab 1 buttons.

### Per-sub-texture revert (`core/textures.restore_subtex_from_baseline`)

Walks the TXB0 record table in `extracted/<file>`, finds sub_N's pixel-byte slice, and copies that byte range over the same offset in `patches/<file>`. Sidesteps the bundled decoder so it works on the non-square `RECTANGLE_TWIDDLED` sub-textures (`datafmt 0x0d`) where decode would return `None`.

Verified end-to-end on `LOBBY38.TEX` sub_12 (128×32 RECTANGLE_TWIDDLED): file size 956,672 unchanged; md5 changes only at the byte slice; other 14 sub-textures untouched.

### Tab 2 right-pane redesign

```
Export to PNG          Export Original (JP baseline) · Export Modified (current patches/)
Edit this sub-tex      Import & Auto-Convert (this sub-tex) · Revert this sub-tex → JP baseline
Whole-file actions     Restore WHOLE file → baseline · Revert WHOLE file → JP baseline
```

### Spawn icon

`assets/icons/spawn.ico` (multi-size 16/32/48/64/128/256) + PNG variants. App sets it via `iconbitmap(default=...)` (covers every top-level window) and `iconphoto(True, ...)` (Linux/macOS dock fallback).

## What's NOT in v1.2.0

Honest scope:

- Only Spawn has bundled modified-texture bytes (the only game with a publicly redistributable validated EN patch). For the other 14 games, `Load Baseline` writes EN strings into `patches/` but does NOT bundle texture work.
- For non-Spawn games, you can still use the `Browse local .dcp…` button if you have an EN .dcp from elsewhere.
- The `Fetch latest from GitHub` URL is currently registered only for Spawn (`DCP_URLS['spawn']`). Add per-game entries to `core/dcp.py` as community patches publish.

## Assets

- `SpawnTools-v1.2.0.zip` — 4.4 MB (was 2.5 MB in v1.1.0; the extra 1.9 MB is the bundled Spawn textures)
- `Spawn-T-En-Farkus-V0.2.dcp` — unchanged

## License

MIT.
