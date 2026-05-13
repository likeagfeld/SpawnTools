"""Bundled Dreamcast codec library — a frozen copy of `_shared_tools/`.

This package vendors the 10 canonical codec modules that ship with the
Spawn translation campaign. The Workbench inserts this directory onto
sys.path automatically (see `config.Config.ensure_shared_tools`) so users
don't have to install anything separately or point at an external path.

Bundled modules:
  process_game        unified disc extract + in-place patch pipeline
  pvr_codec           PVR decode/encode (incl. paletted + VQ + datafmt 0x12)
  tex_decode/encode   TXB0 container codec
  tex_repack          TXB0 in-place sub-tex replace, preserves byte size
  naomi_lzss          16-bit-word-oriented LZSS (PZZ/PVZ/3SYS/SLW)
  archive_unpackers   AFS, PAC, PVS, PZZ, SLW
  pj_texture          Project Justice 3SYS codec
  redraw_engine       Sprite-overlay engine (apply_sprites, render_label)
  jp_en_dict          ~796-entry Spawn-validated JP→EN dictionary

If you ever want to upgrade these to a newer campaign version, copy the
matching .py files into this directory; nothing in the Workbench needs to
change.
"""
__all__ = []
