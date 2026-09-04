"""redteam-studio entry point — launches the RedTeam Studio UI server."""
from __future__ import annotations

import argparse


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="redteam-studio",
        description="Hermes RedTeam Studio - web UI for the llm-redteam harness",
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8610)
    args = ap.parse_args()

    # fastapi/uvicorn live in the [studio] extra so the CLI stays a small
    # install; say so plainly rather than surfacing a bare ImportError.
    try:
        import uvicorn
    except ImportError as e:
        raise SystemExit(
            f"the Studio UI needs its extra ({e}); install it with:\n"
            "  uv pip install 'llm-redteam[studio]'   (or '.[studio]' from a clone)"
        ) from e

    uvicorn.run("redteam.ui_server:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
