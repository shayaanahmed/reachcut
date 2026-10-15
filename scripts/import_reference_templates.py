"""Save and classify the complete reference catalogue through the running local API.

Run with Python 3; only the standard library is required. Re-running skips completed
clips. Progress survives interruptions in data/reference-template-batch.json.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--download-workers", type=int, choices=range(1, 9), default=4)
    args = parser.parse_args()
    base = args.api_url.rstrip("/") + "/video-generation/template-library"
    args.data_dir.mkdir(parents=True, exist_ok=True)
    progress_path = args.data_dir / "reference-template-batch.json"
    lock = threading.Lock()
    state: dict[str, object] = {
        "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
        "total": 0, "saved": 0, "classified": 0, "current": None, "failures": {},
    }
    failures: dict[str, str] = {}
    work: Queue[dict[str, object] | None] = Queue()

    def checkpoint() -> None:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        state["failures"] = dict(failures)
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2) + "\n")
        temporary.replace(progress_path)

    def request(path: str = "", body: dict[str, object] | None = None,
                *, post: bool = False) -> object:
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
            method="POST" if post else "GET",
        )
        with urllib.request.urlopen(req, timeout=1300 if "/classify" in path else 90) as response:
            return json.load(response)

    def error_message(error: Exception) -> str:
        if isinstance(error, urllib.error.HTTPError):
            try:
                return str(json.loads(error.read())["detail"])
            except (ValueError, KeyError):
                pass
        return f"{type(error).__name__}: {error}"

    items = request()
    if not isinstance(items, list):
        raise RuntimeError("The API returned an invalid template catalogue")
    state["total"] = len(items)
    state["saved"] = sum(bool(item.get("video_url")) for item in items)
    state["classified"] = sum(item["status"] == "ready" for item in items)
    checkpoint()
    print(f"Starting: {state['saved']}/{len(items)} saved, "
          f"{state['classified']}/{len(items)} classified", flush=True)

    def save(item: dict[str, object]) -> dict[str, object] | None:
        if item.get("video_url"):
            return item
        for attempt in range(3):
            try:
                result = request("/import", {"url": item["source_url"], "name": item["name"]},
                                 post=True)
                if not isinstance(result, dict):
                    raise ValueError("Invalid import response")
                with lock:
                    state["saved"] = int(state["saved"]) + 1  # type: ignore[call-overload]
                    failures.pop(str(item["id"]), None)
                    checkpoint()
                    if int(state["saved"]) % 10 == 0:  # type: ignore[call-overload]
                        print(f"Saved: {state['saved']}/{state['total']}", flush=True)
                return result
            except Exception as error:
                if attempt == 2:
                    with lock:
                        failures[str(item["id"])] = error_message(error)
                        checkpoint()
                    print(f"Import failed: {item['name']}: {failures[str(item['id'])]}", flush=True)
                else:
                    time.sleep(2)
        return None

    def classify() -> None:
        while True:
            item = work.get()
            if item is None:
                return
            if item["status"] == "ready":
                continue
            with lock:
                state["current"] = item["name"]
                checkpoint()
            for attempt in range(3):
                try:
                    result = request(f"/{item['id']}/classify", post=True)
                    if not isinstance(result, dict) or result.get("status") != "ready":
                        detail = result.get("error") if isinstance(result, dict) else result
                        raise ValueError(str(detail))
                    with lock:
                        state["classified"] = int(state["classified"]) + 1  # type: ignore[call-overload]
                        failures.pop(str(item["id"]), None)
                        checkpoint()
                    print(f"Classified: {state['classified']}/{state['total']} — {result['name']}",
                          flush=True)
                    break
                except Exception as error:
                    if attempt == 2:
                        with lock:
                            failures[str(item["id"])] = error_message(error)
                            checkpoint()
                        print(f"Classification failed: {item['name']}: "
                              f"{failures[str(item['id'])]}", flush=True)
                    else:
                        time.sleep(2)

    worker = threading.Thread(target=classify, name="reference-template-classifier")
    worker.start()
    try:
        with ThreadPoolExecutor(max_workers=args.download_workers) as pool:
            futures = [pool.submit(save, item) for item in items]
            for future in as_completed(futures):
                item = future.result()
                if item is not None:
                    work.put(item)
    finally:
        work.put(None)
        worker.join()
    final = request()
    if not isinstance(final, list):
        raise RuntimeError("Could not verify the final template library")
    state["saved"] = sum(bool(item.get("video_url")) for item in final)
    state["classified"] = sum(item["status"] == "ready" for item in final)
    state["status"] = "complete" if state["classified"] == state["total"] else "needs_attention"
    state["current"] = None
    checkpoint()
    print(json.dumps(state, indent=2), flush=True)


if __name__ == "__main__":
    main()
