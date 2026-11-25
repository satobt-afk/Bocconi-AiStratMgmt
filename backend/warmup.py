"""Load both AI models into memory before a demo, so the first question isn't slow.

    python -m backend.warmup

Loading takes ~30 s in total. Afterwards the first coach question takes ~13 s
instead of ~21 s, because the long system prompt is already cached.
A NEW receipt photo still takes ~15 s on an M1 with 8 GB (reading the image is
the slow part, not loading). Only a photo already read is fast (~3 s, cached).
Run this about 10 minutes before presenting, with the Ollama app open.
"""

import base64
import struct
import sys
import time
import zlib

from backend.agent import run_agent
from backend.db import create_user
from backend.model_client import ModelUnavailable, get_model_client
from backend.transactions import connect


def _white_png(size: int = 64) -> str:
    """A small plain white PNG (no transparency), base64-encoded, just to load the vision model."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = b"".join(b"\x00" + b"\xff" * 3 * size for _ in range(size))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows))
           + chunk(b"IEND", b""))
    return base64.b64encode(png).decode()


def main() -> int:
    client = get_model_client()
    try:
        started = time.time()
        # A real (throwaway) coach question: the model reads the long system prompt and
        # tool list once and caches it, so the first question in the demo is faster.
        scratch = connect(":memory:")  # throwaway database and user: no real data involved
        run_agent(scratch, create_user(scratch), client, [], "Can I afford a 10 € cinema ticket?")
        print(f"Coach model ready ({time.time() - started:.0f} s)")
        started = time.time()
        client.read_image("Is this image blank? Answer in JSON.", _white_png(),
                          {"type": "object", "properties": {"blank": {"type": "boolean"}}})
        print(f"Receipt model ready ({time.time() - started:.0f} s)")
    except ModelUnavailable as error:
        print(f"Ollama is not reachable: open the Ollama app first.\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
