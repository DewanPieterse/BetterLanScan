"""Wi-Fi scanning via Apple CoreWLAN.

Note: on macOS Sonoma+ an active scan that returns SSID/BSSID requires the
host app to hold Location Services authorization. When run from a plain
terminal those fields may be empty; the rest (channel, RSSI, security)
still populates. Run the built .app bundle and grant Location to get names.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WifiNetwork:
    ssid: str = ""
    bssid: str = ""
    rssi: int = 0           # dBm
    noise: int = 0          # dBm
    channel: int = 0
    band: str = ""          # "2.4 GHz" / "5 GHz" / "6 GHz"
    width_mhz: int = 0
    security: str = ""
    is_current: bool = False
    country: str = ""

    @property
    def snr(self) -> int:
        return self.rssi - self.noise if self.noise else 0

    @property
    def quality(self) -> int:
        """0-100 signal quality from RSSI."""
        r = self.rssi
        if r >= -50:
            return 100
        if r <= -100:
            return 0
        return int(2 * (r + 100))


@dataclass
class WifiStatus:
    available: bool = False
    powered_on: bool = False
    interface: str = ""
    current_ssid: str = ""
    current_bssid: str = ""
    rssi: int = 0
    noise: int = 0
    tx_rate: float = 0.0
    channel: int = 0
    band: str = ""
    security: str = ""
    networks: list[WifiNetwork] = field(default_factory=list)
    error: str = ""


_BAND_MAP = {1: "2.4 GHz", 2: "5 GHz", 3: "6 GHz"}


def _band_for_channel(num: int, band_enum: int | None) -> str:
    if band_enum in _BAND_MAP:
        return _BAND_MAP[band_enum]
    if num <= 0:
        return ""
    if num <= 14:
        return "2.4 GHz"
    if num >= 32 and num <= 68:  # 6E low channels overlap; rough
        return "6 GHz"
    return "5 GHz"


def _security_string(net) -> str:
    try:
        import CoreWLAN
        checks = [
            ("Open", CoreWLAN.kCWSecurityNone),
            ("WEP", CoreWLAN.kCWSecurityWEP),
            ("WPA Personal", CoreWLAN.kCWSecurityWPAPersonal),
            ("WPA2 Personal", CoreWLAN.kCWSecurityWPA2Personal),
            ("WPA Enterprise", CoreWLAN.kCWSecurityWPAEnterprise),
            ("WPA2 Enterprise", CoreWLAN.kCWSecurityWPA2Enterprise),
            ("WPA3 Personal", CoreWLAN.kCWSecurityWPA3Personal),
            ("WPA3 Enterprise", CoreWLAN.kCWSecurityWPA3Enterprise),
        ]
        for label, const in checks:
            try:
                if net.supportsSecurity_(const):
                    return label
            except Exception:
                continue
    except Exception:
        pass
    return "Unknown"


def get_status(active_scan: bool = True) -> WifiStatus:
    st = WifiStatus()
    try:
        import CoreWLAN
    except Exception as e:  # pragma: no cover
        st.error = f"CoreWLAN unavailable: {e}"
        return st

    client = CoreWLAN.CWWiFiClient.sharedWiFiClient()
    iface = client.interface()
    if iface is None:
        st.error = "No Wi-Fi interface found."
        return st

    st.available = True
    st.interface = iface.interfaceName() or ""
    try:
        st.powered_on = bool(iface.powerOn())
    except Exception:
        st.powered_on = True
    st.current_ssid = iface.ssid() or ""
    st.current_bssid = iface.bssid() or ""
    try:
        st.rssi = int(iface.rssiValue())
        st.noise = int(iface.noiseMeasurement())
        st.tx_rate = float(iface.transmitRate())
        ch = iface.wlanChannel()
        if ch is not None:
            st.channel = int(ch.channelNumber())
            st.band = _band_for_channel(st.channel, _safe_band(ch))
    except Exception:
        pass

    if not active_scan:
        return st

    try:
        networks, err = iface.scanForNetworksWithName_error_(None, None)
        if err is not None:
            st.error = str(err)
        if networks:
            for n in networks:
                st.networks.append(_to_network(n, st.current_bssid))
    except Exception as e:
        st.error = f"Scan failed: {e}"

    st.networks.sort(key=lambda w: w.rssi, reverse=True)
    return st


def _safe_band(channel_obj) -> int | None:
    try:
        return int(channel_obj.channelBand())
    except Exception:
        return None


def _to_network(n, current_bssid: str) -> WifiNetwork:
    w = WifiNetwork()
    w.ssid = n.ssid() or "(hidden)"
    w.bssid = n.bssid() or ""
    try:
        w.rssi = int(n.rssiValue())
    except Exception:
        pass
    try:
        w.noise = int(n.noiseMeasurement())
    except Exception:
        pass
    try:
        ch = n.wlanChannel()
        if ch is not None:
            w.channel = int(ch.channelNumber())
            w.band = _band_for_channel(w.channel, _safe_band(ch))
            try:
                # channelWidth enum: 0=20,1=40,2=80,3=160
                width_map = {0: 20, 1: 40, 2: 80, 3: 160}
                w.width_mhz = width_map.get(int(ch.channelWidth()), 0)
            except Exception:
                pass
    except Exception:
        pass
    try:
        w.country = n.countryCode() or ""
    except Exception:
        pass
    w.security = _security_string(n)
    w.is_current = bool(current_bssid) and (w.bssid == current_bssid)
    return w


if __name__ == "__main__":
    st = get_status()
    print(f"iface={st.interface} powered={st.powered_on} ssid={st.current_ssid!r} "
          f"rssi={st.rssi} ch={st.channel} {st.band}")
    if st.error:
        print("note:", st.error)
    print(f"found {len(st.networks)} networks")
    for w in st.networks:
        print(f"  {w.ssid:<24}{w.bssid:<18}ch{w.channel:<4}{w.band:<8}"
              f"{w.rssi:>4}dBm  q{w.quality:>3}%  {w.security}")
