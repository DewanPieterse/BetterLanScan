"""MAC address -> vendor lookup.

Uses a bundled subset of the IEEE OUI registry covering common consumer
and infrastructure vendors. If a full `oui.txt` (IEEE format) is dropped
next to this file it will be parsed and merged for complete coverage.
"""
from __future__ import annotations

import os
import re

# Curated common OUI prefixes (first 3 octets, upper, no separators).
_BUILTIN: dict[str, str] = {
    "FCFBFB": "Apple", "F0F61C": "Apple", "A4C361": "Apple", "3C0754": "Apple",
    "001451": "Apple", "002608": "Apple", "0023DF": "Apple", "0026BB": "Apple",
    "D0E140": "Apple", "8C8590": "Apple", "F4F15A": "Apple", "ACBC32": "Apple",
    "A85C2C": "Apple", "DC2B2A": "Apple", "F0DBF8": "Apple", "C82A14": "Apple",
    "B8E856": "Apple", "9803D8": "Apple", "5CF938": "Apple", "F86214": "Apple",
    "BCD074": "Apple", "30635B": "Apple", "70700D": "Apple", "F0989D": "Apple",
    "001124": "Apple", "0017F2": "Apple", "001B63": "Apple", "001E52": "Apple",
    "F4D488": "Google", "F88FCA": "Google", "3C5AB4": "Google", "94EB2C": "Google",
    "A47733": "Google", "DA7A23": "Google", "8C593C": "Google", "1C53F9": "Amazon",
    "F0272D": "Amazon", "44650D": "Amazon", "68543D": "Amazon", "FCA667": "Amazon",
    "0CDC91": "Amazon", "B47C9C": "Amazon", "50F5DA": "Amazon", "34D270": "Amazon",
    "001D0F": "TP-Link", "50C7BF": "TP-Link", "1027F5": "TP-Link", "AC84C6": "TP-Link",
    "C006C3": "TP-Link", "60A4B7": "TP-Link", "B0BE76": "TP-Link", "F4F26D": "TP-Link",
    "30B5C2": "TP-Link", "EC086B": "TP-Link", "5C628B": "TP-Link", "9C5322": "TP-Link",
    "001F33": "Netgear", "2C3033": "Netgear", "A040A0": "Netgear", "9C3DCF": "Netgear",
    "204E7F": "Netgear", "C03F0E": "Netgear", "E0469A": "Netgear", "B07FB9": "Netgear",
    "0018E7": "Cameo/Netgear", "00095B": "Netgear", "00146C": "Netgear",
    "002401": "D-Link", "1CBDB9": "D-Link", "340804": "D-Link", "C8BE19": "D-Link",
    "B8A386": "D-Link", "5CD998": "D-Link", "001CF0": "D-Link",
    "F8D111": "TP-Link", "0024A5": "Buffalo", "001601": "Buffalo",
    "0050F2": "Microsoft", "000D3A": "Microsoft", "7C1E52": "Microsoft",
    "C83F26": "Microsoft", "5448109": "Microsoft", "3859F9": "Microsoft",
    "001560": "HP", "002655": "HP", "9C8E99": "HP", "3863BB": "HP", "B05ADA": "HP",
    "C8D3FF": "HP", "10604B": "HP", "ECEBB8": "HP", "94189B": "HP",
    "001372": "Dell", "00188B": "Dell", "001EC9": "Dell", "B8CA3A": "Dell",
    "F8BC12": "Dell", "F8B156": "Dell", "509A4C": "Dell", "D89EF3": "Dell",
    "001A11": "Google/Nest", "00248C": "ASUS", "08606E": "ASUS", "2C56DC": "ASUS",
    "1C872C": "ASUS", "AC220B": "ASUS", "50465D": "ASUS", "04D9F5": "ASUS",
    "D850E6": "ASUS", "B06EBF": "ASUS", "70854D": "ASUS", "9C5C8E": "ASUS",
    "0026B9": "Sony", "FCF152": "Sony", "104FA8": "Sony", "30F9ED": "Sony",
    "001315": "Sony", "001A80": "Sony", "001DBA": "Sony", "00248D": "Sony",
    "B4F1DA": "LG", "001E75": "LG", "001C62": "LG", "0050BA": "LG",
    "C49A02": "LG", "10683F": "LG", "98D6F7": "LG", "A816B2": "LG",
    "0012FB": "Samsung", "0015B9": "Samsung", "001632": "Samsung", "0017C9": "Samsung",
    "001A8A": "Samsung", "002399": "Samsung", "5C0A5B": "Samsung", "8425DB": "Samsung",
    "C8BA94": "Samsung", "E8508B": "Samsung", "F409D8": "Samsung", "BCED09": "Samsung",
    "001CDF": "Belkin", "08863B": "Belkin", "94103E": "Belkin", "B4750E": "Belkin",
    "C05627": "Belkin", "EC1A59": "Belkin",
    "0018F8": "Cisco-Linksys", "001839": "Cisco-Linksys", "002369": "Cisco",
    "00000C": "Cisco", "001121": "Cisco", "0023AB": "Cisco", "F02765": "Cisco",
    "488EEF": "Cisco-Meraki", "E0CB4E": "ASUSTek", "DC4A3E": "Hisense",
    "B827EB": "Raspberry Pi", "DCA632": "Raspberry Pi", "E45F01": "Raspberry Pi",
    "D83ADD": "Raspberry Pi", "2CCF67": "Raspberry Pi", "28CDC1": "Raspberry Pi",
    "B8278F": "Raspberry Pi", "00E04C": "Realtek", "525400": "QEMU/KVM",
    "080027": "VirtualBox", "000C29": "VMware", "005056": "VMware", "001C14": "VMware",
    "001C42": "Parallels", "0003FF": "Microsoft Hyper-V",
    "0024E4": "Withings", "ACCF23": "Hi-Flying", "5CCF7F": "Espressif",
    "240AC4": "Espressif", "A020A6": "Espressif", "2462AB": "Espressif",
    "84F3EB": "Espressif", "807D3A": "Espressif", "DC4F22": "Espressif",
    "EC94CB": "Espressif", "30AEA4": "Espressif", "C8C9A3": "Espressif",
    "0017880": "Philips Hue", "001788": "Philips", "EC1BBD": "Philips",
    "B0F893": "Texas Instruments", "001A22": "eQ-3/Homematic",
    "00040E": "AVM (Fritz!Box)", "3810D5": "AVM", "C0C1C0": "Cisco",
    "E091F5": "Netgear", "744401": "Netgear", "6CB0CE": "Netgear",
    "FCECDA": "Ubiquiti", "F09FC2": "Ubiquiti", "DC9FDB": "Ubiquiti",
    "788A20": "Ubiquiti", "245A4C": "Ubiquiti", "B4FBE4": "Ubiquiti",
    "687251": "Ubiquiti", "44D9E7": "Ubiquiti", "E063DA": "Ubiquiti",
    "0418D6": "Ubiquiti", "802AA8": "Ubiquiti", "FCC233": "Espressif",
    "186472": "Aruba", "6CF37F": "Aruba", "9C1C12": "Aruba",
    "001A1E": "Aruba", "000B86": "Aruba", "ACA31E": "Aruba",
    "001F5B": "Apple", "002500": "Apple", "0021E9": "Apple", "002332": "Apple",
    "60FACD": "Apple", "98F0AB": "Apple", "A4B197": "Apple", "C0E862": "Apple",
    "001B98": "Samsung", "0023D6": "Samsung", "30CDA7": "Samsung",
    "5440AD": "Samsung", "78471D": "Samsung", "B0DF3A": "Samsung",
    "001A79": "UPC", "44E137": "Liteon", "0019D2": "Intel", "001B21": "Intel",
    "001E64": "Intel", "0024D7": "Intel", "3C970E": "Intel", "7C7A91": "Intel",
    "A0A8CD": "Intel", "DC5360": "Intel", "F8633F": "Intel", "9CB6D0": "Intel",
    "001E2A": "Netgear", "44A56E": "Netgear", "C40415": "Netgear",
}

_full: dict[str, str] | None = None


def _normalize(mac: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", mac).upper()[:6]


def _load_full() -> dict[str, str]:
    global _full
    if _full is not None:
        return _full
    _full = {}
    path = os.path.join(os.path.dirname(__file__), "oui.txt")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    m = re.match(r"\s*([0-9A-Fa-f]{2}-[0-9A-Fa-f]{2}-[0-9A-Fa-f]{2})\s+\(hex\)\s+(.+)", line)
                    if m:
                        _full[_normalize(m.group(1))] = m.group(2).strip()
        except Exception:
            pass
    return _full


def lookup(mac: str) -> str:
    if not mac:
        return ""
    prefix = _normalize(mac)
    if len(prefix) < 6:
        return ""
    # locally administered / multicast hint
    full = _load_full()
    if prefix in full:
        return full[prefix]
    if prefix in _BUILTIN:
        return _BUILTIN[prefix]
    try:
        second = int(prefix[1], 16)
        if second & 0x2:
            return "Locally administered"
    except Exception:
        pass
    return "Unknown"


if __name__ == "__main__":
    for t in ("e2:a1:ad:a5:cb:3b", "b8:27:eb:11:22:33", "fc:fb:fb:00:00:00"):
        print(t, "->", lookup(t))
