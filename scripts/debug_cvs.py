import sys
sys.path.insert(0, 'D:/DC_CapcomTranslationTools')
sys.path.insert(0, 'D:/DC_CapcomTranslationTools/spawntools/codecs')
from pathlib import Path
from spawntools.core import archives, textures
import tex_decode

cvs = Path(r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated/Capcom vs. SNK - Millennium Fight 2000 Pro (JP)/patches")
for p in sorted(cvs.rglob("*.BIN"))[:6]:
    nm = p.name
    if nm.startswith("ADX_") or nm == "2_DP.BIN":
        continue
    try:
        kind, members = archives.list_members(p)
    except Exception as e:
        print(f"{nm}  ERR: {e}", flush=True)
        continue
    if not members:
        continue
    m0 = members[0]
    print(f"{nm}  kind={kind}  n={len(members)}", flush=True)
    print(f"  m0: raw_size={m0.raw_size} dims={m0.raw_width}x{m0.raw_height} pf={hex(m0.raw_pixfmt)} df={hex(m0.raw_datafmt)} pvr_bytes_len={len(m0.pvr_bytes)}", flush=True)
    try:
        img = tex_decode.decode_texture(m0.pvr_bytes, 0, m0.raw_width, m0.raw_height, m0.raw_pixfmt, m0.raw_datafmt)
        print(f"  decode -> {img}", flush=True)
    except Exception as e:
        print(f"  decode EXC: {e}", flush=True)
