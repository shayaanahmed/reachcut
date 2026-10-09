from __future__ import annotations

import argparse
import multiprocessing
import sys

import uvicorn


def main() -> None:
    if sys.argv[1:3] == ["-m", "yt_dlp"]:
        from yt_dlp import main as yt_dlp_main

        yt_dlp_main(sys.argv[3:])
        return

    parser = argparse.ArgumentParser(description="ReachCut packaged API")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65_535:
        parser.error("--port must be between 1 and 65535")
    uvicorn.run(
        "clipper.main:app",
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_level="info",
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
