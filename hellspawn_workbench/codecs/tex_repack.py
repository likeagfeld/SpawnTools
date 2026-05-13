"""Repack a TXB0 .TEX after replacing some sub-textures.

Usage:
    from tex_repack import TexFile
    t = TexFile.load('LOBBY38.TEX')
    t.replace(3, new_pil_image)   # swap sub-texture index 3
    t.save('LOBBY38_NEW.TEX')

Preserves the original TXB0 header, record layout, pixel format & data
format of each entry, and the offsets table.
"""
import struct
from PIL import Image
from tex_encode import encode_image


class TexFile:
    def __init__(self, raw: bytes):
        if raw[:4] != b'TXB0':
            raise ValueError("not a TXB0 file")
        self.raw = bytearray(raw)
        self.n = struct.unpack_from('<I', raw, 4)[0]
        self.data_off = struct.unpack_from('<I', raw, 8)[0]
        self.records = []
        for i in range(self.n):
            r = raw[16 + i*16: 16 + (i+1)*16]
            self.records.append({
                'w': struct.unpack_from('<H', r, 0)[0],
                'h': struct.unpack_from('<H', r, 2)[0],
                'pixfmt': r[4],
                'datafmt': r[5],
                'offset': struct.unpack_from('<I', r, 8)[0],
                'pad1': struct.unpack_from('<H', r, 6)[0],
                'pad2': struct.unpack_from('<I', r, 12)[0],
            })

    @classmethod
    def load(cls, path: str) -> 'TexFile':
        with open(path, 'rb') as f:
            return cls(f.read())

    def get_raw_pixels(self, idx: int) -> bytes:
        """Return raw pixel bytes for sub-texture idx."""
        rec = self.records[idx]
        start = self.data_off + rec['offset']
        # length = next record's offset - this one's, or end of file
        if idx + 1 < self.n and self.records[idx+1]['offset'] > rec['offset']:
            end = self.data_off + self.records[idx+1]['offset']
        else:
            end = len(self.raw)
        return bytes(self.raw[start:end])

    def replace(self, idx: int, new_img: Image.Image):
        rec = self.records[idx]
        if (new_img.size[0], new_img.size[1]) != (rec['w'], rec['h']):
            raise ValueError(
                f"size mismatch: tex {idx} is {rec['w']}x{rec['h']} but image is {new_img.size}"
            )
        new_raw = encode_image(new_img, rec['pixfmt'], rec['datafmt'])
        old_raw = self.get_raw_pixels(idx)
        if len(new_raw) != len(old_raw):
            raise ValueError(
                f"encoded size {len(new_raw)} != original {len(old_raw)} for tex {idx}"
            )
        start = self.data_off + rec['offset']
        self.raw[start:start + len(new_raw)] = new_raw

    def save(self, path: str):
        with open(path, 'wb') as f:
            f.write(bytes(self.raw))

    def info(self):
        print(f"TXB0: {self.n} sub-textures, data starts @0x{self.data_off:x}")
        for i, r in enumerate(self.records):
            print(f"  [{i:2d}] {r['w']:4d}x{r['h']:<4d}  pf=0x{r['pixfmt']:02x} df=0x{r['datafmt']:02x}  @0x{r['offset']:08x}")
