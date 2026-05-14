"""Backward-compat alias — delegates to the generalized builder."""
from __future__ import annotations
from .build_preset import main


if __name__ == '__main__':
    main('spawn')
