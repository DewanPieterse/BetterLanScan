"""macOS user notifications for new device discovery.

Uses pyobjc UserNotifications framework (macOS 10.14+).
Falls back to osascript if unavailable.
"""
from __future__ import annotations

_enabled = True


def _send_objc(title: str, body: str) -> bool:
    try:
        import UserNotifications  # type: ignore
        center = UserNotifications.UNUserNotificationCenter.currentNotificationCenter()
        content = UserNotifications.UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(body)
        content.setSound_(UserNotifications.UNNotificationSound.defaultSound())
        req = UserNotifications.UNNotificationRequest.requestWithIdentifier_content_trigger_(
            f"bls-{title[:20]}", content, None
        )
        center.addNotificationRequest_withCompletionHandler_(req, None)
        return True
    except Exception:
        return False


def _send_osascript(title: str, body: str) -> bool:
    import subprocess
    try:
        script = f'display notification "{body}" with title "{title}" sound name "Ping"'
        subprocess.run(["osascript", "-e", script],
                       capture_output=True, timeout=3)
        return True
    except Exception:
        return False


def send(title: str, body: str) -> None:
    if not _enabled:
        return
    if not _send_objc(title, body):
        _send_osascript(title, body)


def new_device(ip: str, mac: str, vendor: str = "", hostname: str = "") -> None:
    name = hostname or vendor or mac
    send("New device on network", f"{ip}  ·  {name}")


def arp_conflict(ip: str, mac1: str, mac2: str) -> None:
    send("⚠️ ARP conflict detected",
         f"{ip} claimed by {mac1} and {mac2}")


if __name__ == "__main__":
    send("BetterLanScan test", "Notifications are working ✓")
    print("Notification sent (check notification centre)")
