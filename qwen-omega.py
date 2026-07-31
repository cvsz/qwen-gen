#!/usr/bin/env python3
"""Backward-compatibility shim — delegates to qwen_omega module.

The canonical module is qwen_omega.py (underscore).
This file (qwen-omega.py) is kept so existing scripts that call
  python qwen-omega.py ...
continue to work without modification.
"""

import sys
from pathlib import Path

# Add parent dir so qwen_omega is importable even from an arbitrary cwd
sys.path.insert(0, str(Path(__file__).parent))

from qwen_omega import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
