"""Disposable private loopback service for browser acceptance, never touches lab state."""

import os
import tempfile
from pathlib import Path

from minicore_mcp.__main__ import main

with tempfile.TemporaryDirectory(prefix="minicore-browser-") as temp:
    os.environ.pop("MINICORE_SSH_DIR", None)
    os.environ.update(
        {
            "MINICORE_ROOT": str(Path(__file__).resolve().parents[1]),
            "MINICORE_HOST": "127.0.0.1",
            "MINICORE_PORT": "19123",
            "MINICORE_EXPOSURE_PROFILE": "private",
            "MINICORE_TOKEN_FILE": temp + "/tokens.json",
            "MINICORE_OBSERVATIONS": temp + "/observations.json",
            "MINICORE_ALLOWED_ORIGINS": "http://127.0.0.1:19123",
        }
    )
    main()
