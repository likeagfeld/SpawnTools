"""Naomi LZSS codec, ported from modnao's TypeScript implementation
(https://github.com/rob2d/modnao/tree/main/src/utils/data).

Word-oriented LZSS used by Capcom Naomi/Dreamcast games (MvC2, CvS2, Spawn,
and Tech Romancer PVZ files — entire PVZ file is a stream that decompresses
to a regular PVR; no separate header/prefix bytes).

Format:
- Operates on 16-bit little-endian words.
- Every 16 ops are preceded by a single 16-bit BITMASK word.
- Each bit in the bitmask (MSB-first) indicates whether the next word is a
  back-reference (1) or a literal (0).
- A back-reference word:
    - If word's upper 5 bits are non-zero: 5-bit length / 11-bit offset.
    - If word equals its lower-11-bits (5 MSBs zero): 32-bit form — this word
      is the offset (>= 2047), followed by a second word for the length.
- Stream terminator: a back-ref word == 0.
"""
import struct

WORD = 2
COMPRESSION_FLAG = 0x8000
BITS11 = 0x7FF
MAX_LOOKBACK_16 = BITS11  # 0x7FF == 2047


def decompress(buf: bytes) -> bytes:
    """Decompress a NaomiLZSS-compressed byte buffer."""
    out = []  # list of 16-bit values
    apply_bitmask = True
    bitmask = 0
    chunk = 0
    nwords = len(buf) // WORD
    i = 0
    while i < nwords:
        word = struct.unpack_from('<H', buf, i * WORD)[0]

        if apply_bitmask:
            bitmask = word
            apply_bitmask = False
            i += 1
            continue

        is_compressed = bitmask & (COMPRESSION_FLAG >> chunk)
        extra = 0

        if not is_compressed:
            out.append(word)
        elif word == 0:
            break
        else:
            is_32 = (word & BITS11) == word   # upper 5 bits all zero
            if not is_32:
                grab = (word >> 11) & 0x1F
                back = word & BITS11
            else:
                back = word
                i += 1
                grab = struct.unpack_from('<H', buf, i * WORD)[0]

            if back < grab:
                extra = grab - back
                grab = back

            seq = out[len(out) - back: len(out) - back + grab]
            for j in range(grab + extra):
                out.append(seq[j % len(seq)] if seq else 0)

        chunk += 1
        i += 1
        if chunk == 0x10:
            chunk = 0
            apply_bitmask = True

    return b''.join(struct.pack('<H', v) for v in out)


def compress(buf: bytes) -> bytes:
    """Compress a byte buffer to NaomiLZSS format.

    Uses 2-word hashed positions for fast longest-match search within the
    2047-word lookback window. Overlapping (RLE) matches are permitted.
    Round-trip lossless versus decompress().
    """
    if len(buf) % WORD:
        buf = buf + b'\x00'
    nwords = len(buf) // WORD

    # Pre-extract all words as a list (faster than repeated unpack_from).
    words = list(struct.unpack(f'<{nwords}H', buf))

    # Position chain keyed by (words[i], words[i+1]) -- much more
    # selective than single-word keys, so each lookup needs fewer
    # extensions to find the longest match.
    pair_at_pos = {}

    # Max positions to consider per pair lookup. 4096 is effectively
    # unlimited (longer than the 2047-word lookback window) but bounds
    # runtime on pathologically dense pair chains.
    MAX_CANDIDATES = 4096

    def find_match(i):
        """Find the longest match starting at words[i]. Returns
        (best_back, best_len) with best_len=0 if no match >=2 found."""
        if i + 1 >= nwords:
            return 0, 0
        key = (words[i], words[i + 1])
        positions = pair_at_pos.get(key)
        if not positions:
            return 0, 0
        best_back = 0
        best_len = 0
        min_pos = i - MAX_LOOKBACK_16
        visits = 0
        for idx in range(len(positions) - 1, -1, -1):
            prev = positions[idx]
            if prev < min_pos:
                break
            visits += 1
            if visits > MAX_CANDIDATES:
                break
            back = i - prev
            max_len = min(0xFFFF, nwords - i)
            if max_len <= best_len:
                continue
            L = 2  # guaranteed by pair-key
            while L < max_len and words[prev + L] == words[i + L]:
                L += 1
            if L > best_len:
                best_len = L
                best_back = back
                if L == max_len:
                    break
        return best_back, best_len

    values = []     # int (literal) or (back, length)
    bitmasks = []
    bitmask = 0
    chunk = 0
    i = 0
    while i < nwords:
        w = words[i]
        # Find best match at i. Then register current pair so future
        # positions can reference us. We register AFTER find_match so
        # back=0 (matching ourselves) is impossible.
        best_back, best_len = find_match(i)
        if i + 1 < nwords:
            pair_at_pos.setdefault((w, words[i + 1]), []).append(i)

        if best_len < 2:
            values.append(w)
            i += 1
        else:
            bitmask |= (COMPRESSION_FLAG >> chunk)
            values.append((best_back, best_len))
            # Register every consumed position so future searches can use
            # the words covered by this match.
            for k in range(1, best_len):
                if i + k + 1 < nwords:
                    pair_at_pos.setdefault(
                        (words[i + k], words[i + k + 1]), []).append(i + k)
            i += best_len

        chunk += 1
        if chunk == 16:
            bitmasks.append(bitmask)
            bitmask = 0
            chunk = 0

    # Terminator: mark the next slot in the current bitmask as compressed
    # and emit a zero back-ref word so the decoder terminates exactly when
    # it consumes it.
    bitmask |= (COMPRESSION_FLAG >> chunk)
    bitmasks.append(bitmask)
    values.append((0, 0))  # sentinel - serializer emits a 0 word for this

    # Serialize.
    out = bytearray(len(buf) * 2 + 64)
    pos = 0
    chunk = 0
    bm_i = 0
    for v in values:
        if chunk == 0:
            struct.pack_into('<H', out, pos, bitmasks[bm_i]); pos += 2
            bm_i += 1
        if isinstance(v, int):
            struct.pack_into('<H', out, pos, v); pos += 2
        else:
            back, length = v
            if back == 0 and length == 0:
                # Terminator sentinel.
                struct.pack_into('<H', out, pos, 0); pos += 2
            elif back < MAX_LOOKBACK_16 and length <= 31:
                # Short form: 1 word, upper 5 bits = length (>=2 -> non-zero).
                struct.pack_into('<H', out, pos, (length << 11) | back)
                pos += 2
            else:
                # Long form: 2 words. Decoder triggers long form when
                # (word & 0x7FF) == word -- forced for back >= 2048,
                # also valid (and used) for back < 2048 with length > 31.
                struct.pack_into('<H', out, pos, back); pos += 2
                struct.pack_into('<H', out, pos, length); pos += 2
        chunk = (chunk + 1) % 16

    return bytes(out[:pos])


if __name__ == '__main__':
    import sys
    # quick round-trip sanity test on caller-provided file
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'rb') as f:
            raw = f.read()
        dec = decompress(raw)
        print(f"decompressed: {len(raw)} -> {len(dec)} bytes")
        re_compressed = compress(dec)
        re_dec = decompress(re_compressed)
        print(f"round-trip: {len(re_compressed)} -> {len(re_dec)} bytes")
        match = (re_dec[:len(dec)] == dec)
        print(f"round-trip lossless: {match}")
