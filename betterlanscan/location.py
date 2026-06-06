"""Request macOS Location Services authorization.

CoreWLAN only returns SSID/BSSID for scanned networks when the running app
holds Location authorization (macOS Sonoma+). Calling this early triggers the
system prompt; results take effect on subsequent Wi-Fi scans.
"""
from __future__ import annotations

_manager = None  # keep a strong reference so it isn't GC'd


def request_authorization() -> str:
    """Ask for 'when in use' location access. Returns current status string."""
    global _manager
    try:
        import CoreLocation
    except Exception as e:
        return f"unavailable: {e}"
    try:
        if not CoreLocation.CLLocationManager.locationServicesEnabled():
            return "location services disabled system-wide"
        _manager = CoreLocation.CLLocationManager.alloc().init()
        _manager.requestWhenInUseAuthorization()
        try:
            _manager.startUpdatingLocation()
        except Exception:
            pass
        return status_string()
    except Exception as e:
        return f"error: {e}"


def status_string() -> str:
    try:
        import CoreLocation
        s = CoreLocation.CLLocationManager.authorizationStatus()
        return {
            0: "not determined",
            1: "restricted",
            2: "denied",
            3: "authorized (always)",
            4: "authorized (when in use)",
        }.get(int(s), f"unknown ({s})")
    except Exception as e:
        return f"unknown: {e}"
