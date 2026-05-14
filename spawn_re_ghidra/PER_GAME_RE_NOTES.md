# Per-Game Texture Framework — from Ghidra+FIDB batch (May 2026)

Headless Ghidra applied 11 FIDBs (Katana SDK 1.20J/1.30J/1.42J/1.43J/1.55J/
2.00J/R4/R10.1, Kunoichi 2.02, NAOMI 001.002.1, Katana R9) to each game's
1ST_READ.BIN. The named-function recoveries reveal which texture framework
each game uses, which is the prerequisite for writing the right decoder.

## Texture framework by game

| Game | Framework | Evidence |
|---|---|---|
| Spawn | **Kamui** | `_kmSetTexOverflowCallback`, `_kmtex_GetTextureLevel`, `_kmQueryFinishFlushVertexBuffer`, `_displayStrip_tex_sidx`, `_displayTriangle_tex_sidx` |
| Heavy Metal | **Kamui** | `_kmSetTexOverflowCallback`, `_kmtex_GetTextureLevel`, `_kmQueryFinishFlushVertexBuffer` |
| JoJo | **Ninja** | `_njReLoadTexturePartLN`, `_njReLoadTexturePartNum`, `_njCalcTexture`, `_njReLoadTextureLN`, `_njReLoadTextureNum`, `_njReleaseTextureLN`, `_njReleaseTextureNum`, `_njSetCurrentContext` |
| SF III 3rd Strike | **Ninja** | `_njGetTexSurface`, `_njLoadTexturePartLow`, `_njReleaseTextureLow`, full ReLoad family |
| SFZ3 (MS) | **Ninja** | same full Ninja set |
| SPFII (MS) | **Ninja** | same full Ninja set |
| SSFIIX (MS) | **Ninja** | same full Ninja set |
| Taisen Net Gimmick | **Ninja** | `_njReLoadTextureLodLN`, `_njReLoadTextureLodNum`, `_njGetTexSurfaceEx`, `_njReleaseTextureLowEx`, `_njTexMalloc`, `_njTextureNearClip3DP` |
| Tech Romancer (MS) | **Ninja** | `_njGetTexSurface`, `_njLoadTexturePartLow`, `_njReleaseTextureLow`, `_njPtclSpriteStart` |
| Vampire Chronicle (MS) | **Ninja + Capcom NL** | full Ninja set + `_mwRnv2LoadTex` (Capcom wrapper) |
| Project Justice | **Capcom NL renderer** | `_nlRenderTextureSet_Stride`, `_nlkmCreateTextureSurface_stride`, `_nlRenderTextureSet_Sub` |
| Net de Tennis | **NLSPRITE 0.2** | "NLSPRITE Ver 0.2 COPYRIGHT (C) SEGA ENTERPRISES,LTD." string match |
| CvS Pro | **Capcom proprietary** | FIDB found no texture-named functions. File ref strings hint at PL\*\_TBL.BIN per-character containers. |
| MvC2 | **Capcom proprietary** | Same as CvS Pro; FIDB found no texture API. Per-stage STG\*TEX.BIN files (raw-blob containers, 3× 512×512 RGB565 SQUARE_TWIDDLED for STG0CTEX confirmed). |
| Power Stone 2 | **Capcom proprietary** | DM\*\_CONNECT.BIN, PL\*\_CONNECT.BIN containers. |

## What this enables

**8/15 games (Ninja-based) share the same texture-load semantics.** A single
Ninja-aware decoder will unlock all of them simultaneously. Ninja's texture
descriptor table is published in the Katana SDK headers — finding the
descriptor pointer in 1ST_READ.BIN per game is the only remaining work.

**Ninja texture descriptor (TXR record):**
- `void *pixels;` — VRAM pointer
- `unsigned short width, height;`
- `unsigned char pixfmt;`
- `unsigned char datafmt;`
- `unsigned int flags;`

The `_njLoadTexturePartLow(start_addr, byte_size, num_blocks)` call gives us
(pixels, total size, descriptor count). Walk the .data section for a table
of such records and emit per-blob dimensions automatically.

**For Spawn / Heavy Metal (Kamui):** existing pvr_codec already handles
both. No further work needed for the texture decode path itself.

**For Capcom-proprietary (CvS Pro, MvC2, Power Stone 2):** brute-force
raw-blob detection in `core/raw_blob.py` already handles the simple
N-equally-sized-chunks pattern (MvC2 STG0CTEX = 3×512×512). For chunks
that aren't decoding at first hypothesis, the format cycler (next task)
will let the user pick ARGB1555 / ARGB4444 / RECTANGLE_TWIDDLED.

## Dump locations

- `spawn_re_ghidra/ghidra_dumps/<slug>_1ST_READ.bin.json` — per-game JSON
  with named functions + defined strings.
- `spawn_re_ghidra/ghidra_dumps/<slug>.log` — Ghidra analyzeHeadless log.

## Stats per game

| Game | Total funcs | Total strings | Tex-related funcs | Tex-related strings |
|---|---:|---:|---:|---:|
| cvs_pro | 235 | 1,040 | 0 | 343 |
| heavy_metal | 241 | 907 | 3 | 155 |
| jojo | 181 | 301 | 23 | 12 |
| mvc2 | 241 | 1,062 | 0 | 327 |
| net_de_tennis | 230 | 540 | 0 | 5 |
| power_stone_2 | 236 | 1,440 | 0 | 201 |
| project_justice | 233 | 1,044 | 3 | 7 |
| sf3_3rd_strike | 250 | 1,211 | 23 | 30 |
| sfz3_ms | 226 | 961 | 21 | 7 |
| spawn | 317 | 1,379 | 5 | 350 |
| spfii_ms | 280 | 796 | 23 | 20 |
| ssfiix_ms | 261 | 1,205 | 23 | 105 |
| taisen_net_gimmick | 405 | 1,231 | 13 | 17 |
| tech_romancer_ms | 404 | 1,532 | 23 | 26 |
| vampire_chronicle_ms | 372 | 1,005 | 26 | 135 |

## Confidence statement

The framework attribution is high-confidence (FIDB names are SDK-published).
The texture file LAYOUT (which files contain textures + how they're
structured) still requires:
1. Per-game `_nj*` / `_km*` / `_nl*` call-site inspection to find descriptor
   tables.
2. Validating decoded output via emulator boot test.

Until that's done, raw-blob brute force gives us partial coverage:
- MvC2: 274 chunks surfaced (22 decoded at RGB565 default)
- Taisen Net Gimmick: 132 chunks surfaced (14 decoded)
- SF III: 121 chunks surfaced (1 decoded)

Format cycling will improve the decoded count significantly once added.
