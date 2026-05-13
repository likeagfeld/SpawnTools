"""Workbench configuration.

A single Config dataclass holds every external-path setting the suite
needs at runtime. Persisted to ~/.hellspawn_workbench/config.json so
the user only points at _shared_tools once.

Capcom-specific note: we DO NOT shell out to mkisofs/texconv/vqenc.
The entire pipeline runs through `_shared_tools/` Python codecs.
The `xdelta_path` field is optional and only used for delta-patch
generation (not for the in-place track03 patch — that's pure Python).
"""
from __future__ import annotations
import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / '.hellspawn_workbench'
CONFIG_PATH = CONFIG_DIR / 'config.json'

# The Workbench ships its own copy of the codec library at
# `hellspawn_workbench/codecs/`. This is the default sys.path entry.
# Users on a clean install get the codecs out of the box.
BUNDLED_CODECS = Path(__file__).resolve().parent / 'codecs'

# Legacy fallback — only used if BUNDLED_CODECS is missing AND the user has
# pointed at their own `_shared_tools/` copy via Settings.
DEFAULT_SHARED_TOOLS = Path(
    r"D:/Capcom Dreamcast  Games - Joe Patched/RC2 Translated/_shared_tools"
)


@dataclass
class Config:
    """Single source of truth for every path the Workbench needs."""

    # Optional override for the codec library. Empty string means "use
    # the bundled `hellspawn_workbench/codecs/` directory" (the default).
    # Users who want to point at an external _shared_tools/ copy (e.g.,
    # a newer dev version) can set this from Settings.
    shared_tools_path: str = ''

    # Optional: external tools. The Workbench does NOT require these —
    # the spec asked for them but every core operation has a Python equivalent.
    # Kept here for future use cases (e.g., generating .xdelta patches for distribution).
    xdelta_path: str = ''
    tesseract_path: str = ''        # only for OCR-assist (NEVER for sprite text!)

    # Game-specific defaults — pre-filled for Spawn since that's the focus
    last_disc_path: str = ''
    last_project_dir: str = ''

    # Safety toggles
    # The spec asked for "Pointer Relocation Engine". This is OFF by default
    # because the campaign's hard rule is no-grow. Users can flip it on at their
    # own risk to enable string growth via null-padding-relocation.
    allow_pointer_growth: bool = False

    # Window prefs
    window_geometry: str = '1500x920'
    theme: str = 'clam'

    # Recent files — for the open-recent menu
    recent_projects: list[str] = field(default_factory=list)

    # ---------- persistence ----------

    @classmethod
    def load(cls) -> 'Config':
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
                # Filter to known fields so an older config doesn't crash on a newer
                # field rename.
                known = {f for f in cls.__dataclass_fields__}
                return cls(**{k: v for k, v in data.items() if k in known})
            except (json.JSONDecodeError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

    def add_recent(self, path: str) -> None:
        recent = [p for p in self.recent_projects if p != path]
        recent.insert(0, path)
        self.recent_projects = recent[:10]
        self.save()

    # ---------- _shared_tools bootstrap ----------

    def ensure_shared_tools(self) -> bool:
        """Add the codec library to sys.path and verify importability.

        Tries, in order:
          1. User-configured `shared_tools_path` (if set in Settings)
          2. Bundled `hellspawn_workbench/codecs/` (always works on a clean install)
          3. The legacy default path (for old dev machines)

        Returns True if process_game / pvr_codec / tex_decode all import.
        """
        candidates: list[Path] = []
        if self.shared_tools_path:
            candidates.append(Path(self.shared_tools_path))
        candidates.append(BUNDLED_CODECS)
        candidates.append(DEFAULT_SHARED_TOOLS)
        for p in candidates:
            if not p.is_dir():
                continue
            if str(p) not in sys.path:
                sys.path.insert(0, str(p))
            try:
                import process_game  # noqa: F401
                import pvr_codec      # noqa: F401
                import tex_decode     # noqa: F401
                return True
            except ImportError:
                # Pull the failed candidate back off the path so the next
                # one gets a clean shot
                if str(p) in sys.path:
                    sys.path.remove(str(p))
        return False
