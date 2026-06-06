# 🛰 BetterLanScan

A native macOS network & Wi-Fi scanner — a free, modern take on **LanScan Pro**,
**Advanced IP Scanner** and **WiFi Scanner**. Discovers every device on your
local network and surveys the Wi-Fi airspace around you, in one clean app.

![tabs: LAN Devices · Wi-Fi Networks · Network Info](assets/AppIcon.icns)

## Features

### LAN device discovery
- **Auto-detects your subnet** from the active interface (no config needed).
- **Concurrent ICMP sweep** of the whole range (up to 128 parallel probes).
- **MAC addresses** resolved from the system ARP cache.
- **Vendor identification** via the IEEE OUI registry (bundled common-vendor
  table; drop a full `oui.txt` into `betterlanscan/` for complete coverage).
- **Hostname** via reverse DNS.
- **Open-port scan** of ~22 common services per host.
- **Device-type fingerprinting** (Router, Printer, iPhone/iPad, Smart TV,
  IoT, Computer, Media server, …) from vendor + open ports.
- **Round-trip latency**, live results, sortable columns, instant **filter**,
  and **CSV export**.
- Your machine and the gateway are highlighted.

### Wi-Fi networks (CoreWLAN)
- Lists nearby networks with **SSID, BSSID, signal meter, RSSI, channel,
  band (2.4/5/6 GHz), channel width and security** (Open/WEP/WPA/WPA2/WPA3).
- **Current-connection card**: SSID, channel, band, RSSI, Tx rate, security.
- Open networks flagged in red. Optional **5-second auto-refresh**.

### Network info
- Interface, your IPv4, MAC, subnet mask, CIDR, gateway, broadcast, DNS.

## Install

### Homebrew (easiest)
```bash
brew install --cask dewanpieterse/betterlanscan/betterlanscan
```
The app is ad-hoc signed, not notarized, so on first launch macOS shows an
"unidentified developer" prompt — **right-click the app ▸ Open**, or System
Settings ▸ Privacy & Security ▸ *Open Anyway*. To skip the prompt entirely:
```bash
brew install --cask --no-quarantine dewanpieterse/betterlanscan/betterlanscan
```

### Download
Grab `BetterLanScan-x.y.z.zip` from
[Releases](https://github.com/DewanPieterse/BetterLanScan/releases), unzip,
drag to `/Applications`, then right-click ▸ Open.

## Build & run from source

```bash
cd BetterLanScan
./setup.sh                       # installs runtime + builds the .app
open "dist/BetterLanScan.app"    # or double-click it in Finder
```

Then **grant Location access** when prompted — macOS requires it for Wi-Fi
scan results to include network names (signal/channel/security work either
way). System Settings ▸ Privacy & Security ▸ Location Services.

### Run from source (dev)
```bash
./run.sh
```

## Why a runtime in Application Support?
The project lives under `~/Documents`, which macOS protects with TCC — a
GUI-launched app can't read a Python venv stored there. So `setup.sh` installs
the interpreter + dependencies to
`~/Library/Application Support/BetterLanScan/venv`, and the `.app` bundle (which
contains only the small Python source) points at it. This also keeps the Qt
framework code signatures intact, which the macOS `cocoa` platform plugin
requires.

## Publishing — notarized DMG (direct distribution)

This ships a Developer-ID-signed, **notarized** `.dmg` that opens on any Mac
with no Gatekeeper warning. It is *not* sandboxed (the LAN scanner needs
`ping`/`arp` and raw sockets), so it does **not** go through the Mac App Store.

**One-time prerequisites (paid Apple Developer account, $99/yr):**
1. Create a **Developer ID Application** certificate — Xcode ▸ Settings ▸
   Accounts ▸ Manage Certificates, or developer.apple.com. Confirm it:
   ```bash
   security find-identity -v -p codesigning
   ```
2. Store a notarization credential profile once:
   ```bash
   xcrun notarytool store-credentials BLS-NOTARY \
     --apple-id "you@example.com" --team-id "TEAMID" \
     --password "app-specific-password"   # appleid.apple.com ▸ Sign-In & Security ▸ App-Specific Passwords
   ```

**Build + sign + notarize (three steps):**
```bash
./setup.sh                          # runtime venv (once)
packaging/build_dist.sh             # → dist_standalone/BetterLanScan.app (self-contained, ~99 MB)
export DEV_ID="Developer ID Application: Your Name (TEAMID)"
export NOTARY_PROFILE="BLS-NOTARY"
packaging/sign_and_notarize.sh      # → dist_standalone/BetterLanScan-1.0.0.dmg (notarized + stapled)
```
Ship `BetterLanScan-1.0.0.dmg`. Verify on a clean Mac:
```bash
spctl -a -vvv --type open --context context:primary-signature BetterLanScan-1.0.0.dmg
```

> The sign script copies the app into a `/tmp` workspace before signing,
> because this project sits in iCloud-synced `~/Documents` and the sync daemon
> keeps re-adding `com.apple.FinderInfo` xattrs that codesign rejects.

> **Mac App Store** is a separate, harder path: it mandates the App Sandbox,
> which forbids `ping`/`arp`/`ifconfig` subprocesses and raw sockets — the LAN
> engine would need a sandbox-compliant rewrite (and may still be rejected).
> The notarized DMG above is the standard route for network-scanner apps.

## Architecture
| Module | Role |
|--------|------|
| `netinfo.py`  | Interface / subnet / gateway / DNS detection |
| `scanner.py`  | Concurrent ping sweep, ARP, ports, device typing |
| `oui.py`      | MAC → vendor lookup |
| `wifi.py`     | CoreWLAN scan + current status |
| `location.py` | Location Services authorization (for SSIDs) |
| `ui.py` / `widgets.py` / `style.py` | PySide6 UI |

## Requirements
- macOS 11+ and Python 3.11–3.13 (`brew install python@3.13`).
- Wi-Fi names need Location permission; everything else runs unprivileged.

## Notes
- Devices that don't answer ICMP (firewalled) may not appear; they'll still be
  picked up if they're in the ARP cache after the sweep.
- No root required. No data leaves your machine.
