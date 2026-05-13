"""Pointer auditor — DRY-RUN ONLY by default.

The original spec asked for a "Relocation Engine" that would:
  1. Find null-padding regions in 1ST_READ.BIN
  2. Write a longer string into that padding
  3. Update the pointer at the original site to reference the new location

This is HIGHLY UNSAFE in Spawn (and probably in any Capcom DC binary). The
campaign's hard rules:

  • NEVER grow a patched file beyond its original byte size
  • Spawn v20 bricked memory-card boot doing aggressive single-CJK-byte-pair
    replacements; the fix (v22) is shrink-or-equal with strict null-bounded
    context checks
  • SH-4 binaries contain naturally-occurring CJK byte sequences inside code
    and packed data tables, not just strings — so any pattern-matching of
    pointers risks false positives

What this module DOES do:

  • Find SH-4 little-endian 32-bit values in `1ST_READ.BIN` that point into
    the data region (range 0x8C010000..end_of_binary RAM addresses).
  • Cross-reference against the JP string offsets the scanner found.
  • Identify candidate null-padding regions (>= 32 bytes of `\\x00` between
    known-used data).
  • Compute the would-be safety status if we WERE to relocate.
  • Emit a report — never WRITES.

The Workbench's Text Grid tab uses this to populate the "Byte Status" column
with hints like:
    OK 12/20   — fits with shrink
    !! 25/20   — oversize, would need relocation (manual only)
    PTR ?       — pointer-relocation NOT enabled in config
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Spawn's 1ST_READ.BIN loads at this RAM address (cached alias).
# All 32-bit pointer values inside the binary that reference data ought to
# land in this range (binary start + binary size).
SPAWN_LOAD_ADDR = 0x8C010000


@dataclass
class PointerHit:
    """One 4-byte aligned slot in the binary whose value looks like a
    pointer into the data segment."""
    site_offset: int          # where the pointer LIVES in the file
    target_offset: int        # where it POINTS (file offset)
    target_ram_addr: int      # the value in the binary (RAM address)


@dataclass
class PaddingRegion:
    """A run of null bytes >= min_size, used to find code-cave space."""
    file_offset: int
    size: int


def find_data_pointers(binary: bytes,
                       load_addr: int = SPAWN_LOAD_ADDR,
                       min_target: int = 0x1000) -> list[PointerHit]:
    """Scan 4-byte-aligned slots for SH-4 LE u32 values that fall inside the
    binary's own data range. Heuristic — not all hits are real pointers.

    `min_target` filters out small values (which are usually integers, not
    addresses). Default 0x1000 skips most fake matches.
    """
    end_ram = load_addr + len(binary)
    out: list[PointerHit] = []
    for i in range(0, len(binary) - 4, 4):
        val = (binary[i] | (binary[i+1] << 8) | (binary[i+2] << 16) | (binary[i+3] << 24))
        if load_addr + min_target <= val < end_ram:
            target_off = val - load_addr
            out.append(PointerHit(
                site_offset=i, target_offset=target_off, target_ram_addr=val,
            ))
    return out


def find_padding_regions(binary: bytes, min_size: int = 32) -> list[PaddingRegion]:
    """Return runs of >= min_size null bytes. These are candidate slots for
    string growth — but we do NOT write to them by default."""
    out: list[PaddingRegion] = []
    i, L = 0, len(binary)
    while i < L:
        if binary[i] != 0:
            i += 1
            continue
        start = i
        while i < L and binary[i] == 0:
            i += 1
        if i - start >= min_size:
            out.append(PaddingRegion(file_offset=start, size=i - start))
    return out


def pointers_referencing(binary: bytes, target_offset: int,
                          load_addr: int = SPAWN_LOAD_ADDR) -> list[int]:
    """Find every 4-byte-aligned pointer in `binary` whose value equals
    `target_offset + load_addr`. Returns list of site_offsets.

    Lets the Text Grid show 'this string is referenced by N pointers' so
    the user knows whether a translation needs to preserve all of them."""
    target_ram = load_addr + target_offset
    sig = bytes([
        target_ram & 0xFF,
        (target_ram >> 8) & 0xFF,
        (target_ram >> 16) & 0xFF,
        (target_ram >> 24) & 0xFF,
    ])
    hits: list[int] = []
    start = 0
    while True:
        i = binary.find(sig, start)
        if i < 0: break
        if i % 4 == 0:
            hits.append(i)
        start = i + 1
    return hits


@dataclass
class RelocationCandidate:
    """A would-be string relocation. NOT executed by default — `allow_growth`
    config flag must be True for the Master Build tab to actually write it."""
    string_id: int
    source_file: str
    original_offset: int
    original_budget: int
    needed_bytes: int           # cp932 length of the desired EN string
    proposed_landing_offset: Optional[int] = None  # if a padding region was found
    pointer_sites: list[int] = None
    risk_notes: list[str] = None


def audit_oversize_translations(binary: bytes, oversize_entries: list) -> list[RelocationCandidate]:
    """For each oversize translation, look for a padding region big enough
    and the pointer sites we'd need to rewrite.

    DOES NOT EXECUTE. The Workbench's Text Grid surfaces this as a hint to
    the user, who must manually intervene (typically by SHORTENING the
    English instead — that's the campaign's reliable path)."""
    pads = find_padding_regions(binary, min_size=32)
    out: list[RelocationCandidate] = []
    for entry in oversize_entries:
        # Find pointers referencing the original string
        sites = pointers_referencing(binary, entry.byte_offset)
        # Find a padding region with enough room
        landing = None
        for pad in pads:
            if pad.size >= entry.needed_bytes + 1:    # +1 for the null terminator
                landing = pad.file_offset
                break
        notes = []
        if not sites:
            notes.append('NO pointer references found — string may be inline-encoded')
        if not landing:
            notes.append(f'NO padding region with {entry.needed_bytes}+ bytes available')
        # We deliberately do NOT auto-fix — the campaign's rule is shrink the
        # EN. Pointer relocation is gated on user opt-in.
        notes.append('Pointer relocation is DISABLED in this Workbench by default')
        out.append(RelocationCandidate(
            string_id=entry.id, source_file=entry.source_file,
            original_offset=entry.byte_offset, original_budget=entry.byte_budget,
            needed_bytes=entry.needed_bytes,
            proposed_landing_offset=landing, pointer_sites=sites, risk_notes=notes,
        ))
    return out
