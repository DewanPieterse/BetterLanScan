"""Internet speed test — download + upload + latency.

No third-party deps. Uses urllib to download from Cloudflare's speed test
endpoint (1 MB / 10 MB chunks) and measures upload via HTTP POST.
"""
from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass

# Cloudflare speed test files (no tracking, stable, globally CDN'd)
_DL_URLS = [
    "https://speed.cloudflare.com/__down?bytes=10000000",  # 10 MB
    "https://speed.cloudflare.com/__down?bytes=5000000",   # 5 MB fallback
]
_UL_URL = "https://speed.cloudflare.com/__up"
_LATENCY_URL = "https://speed.cloudflare.com/__down?bytes=1"


@dataclass
class SpeedResult:
    latency_ms: float | None = None
    download_mbps: float | None = None
    upload_mbps: float | None = None
    error: str = ""


def _measure_latency(timeout: float = 5.0) -> float | None:
    try:
        t0 = time.perf_counter()
        urllib.request.urlopen(_LATENCY_URL, timeout=timeout)
        return (time.perf_counter() - t0) * 1000
    except Exception:
        return None


def _measure_download(progress_cb=None, timeout: float = 15.0) -> float | None:
    for url in _DL_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BetterLanScan/1.0"})
            t0 = time.perf_counter()
            total = 0
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if progress_cb:
                        progress_cb("download", total)
            elapsed = time.perf_counter() - t0
            if elapsed > 0 and total > 0:
                return (total * 8) / elapsed / 1_000_000  # Mbps
        except Exception:
            continue
    return None


def _measure_upload(progress_cb=None, timeout: float = 15.0) -> float | None:
    # Upload 2 MB of random-ish data
    size = 2 * 1024 * 1024
    data = bytes(range(256)) * (size // 256)
    try:
        req = urllib.request.Request(
            _UL_URL, data=data, method="POST",
            headers={
                "User-Agent": "BetterLanScan/1.0",
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
            }
        )
        t0 = time.perf_counter()
        urllib.request.urlopen(req, timeout=timeout)
        elapsed = time.perf_counter() - t0
        if elapsed > 0:
            return (len(data) * 8) / elapsed / 1_000_000
    except Exception:
        return None


def run(progress_cb=None) -> SpeedResult:
    """Run full speed test. progress_cb(stage, value) called during download."""
    result = SpeedResult()
    try:
        if progress_cb: progress_cb("latency", None)
        result.latency_ms = _measure_latency()

        if progress_cb: progress_cb("download", 0)
        result.download_mbps = _measure_download(progress_cb)

        if progress_cb: progress_cb("upload", 0)
        result.upload_mbps = _measure_upload(progress_cb)
    except Exception as e:
        result.error = str(e)
    return result


if __name__ == "__main__":
    def cb(stage, val):
        if stage == "download" and val:
            print(f"\r  Downloaded: {val/1e6:.1f} MB", end="", flush=True)
        else:
            print(f"\n  Testing {stage}…")
    print("Running speed test…")
    r = run(cb)
    print(f"\nLatency:  {r.latency_ms:.1f} ms" if r.latency_ms else "\nLatency:  —")
    print(f"Download: {r.download_mbps:.1f} Mbps" if r.download_mbps else "Download: —")
    print(f"Upload:   {r.upload_mbps:.1f} Mbps" if r.upload_mbps else "Upload:   —")
    if r.error: print(f"Error:    {r.error}")
