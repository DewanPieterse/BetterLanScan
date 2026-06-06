"""Vulnerability hints from open ports + service banners.

Heuristic matching only — not a CVE scanner. Flags well-known issues:
outdated software versions, dangerous default services, weak configs.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VulnHint:
    severity: str    # "critical" / "high" / "medium" / "info"
    title: str
    detail: str
    ref: str = ""    # CVE or advisory URL if known


_SEVERITY_COLOR = {
    "critical": "#ff4444",
    "high":     "#ff8c00",
    "medium":   "#ffc24c",
    "info":     "#7fd1a8",
}


def color_for(severity: str) -> str:
    return _SEVERITY_COLOR.get(severity, "#8b93a7")


# (port, banner_fragment_lower) → hint
_PORT_RULES: list[tuple[int | None, str | None, str, str, str, str]] = [
    # port  banner_frag              sev        title                                    detail                                   ref
    (23,    None,           "critical", "Telnet open",
     "Telnet transmits credentials in cleartext. Replace with SSH.", ""),
    (21,    None,           "high",     "FTP open",
     "FTP transmits credentials in cleartext. Use SFTP/FTPS instead.", ""),
    (161,   None,           "medium",   "SNMP open",
     "SNMP v1/v2c uses community strings in cleartext. Check for default 'public'.", ""),
    (1900,  None,           "medium",   "UPnP exposed",
     "UPnP should not be reachable from other hosts. Can allow port-forward hijacking.", ""),
    (5900,  None,           "high",     "VNC exposed",
     "VNC without a VPN is a significant risk. Ensure strong password is set.", ""),
    (3389,  None,           "medium",   "RDP exposed",
     "RDP directly on LAN. Ensure NLA is required and patch level is current.", ""),
    (27017, None,           "critical", "MongoDB unauthenticated",
     "Default MongoDB has no authentication. Verify access control is enabled.", "CVE-2017-4596"),
    (6379,  None,           "critical", "Redis exposed",
     "Redis with no auth or bind 0.0.0.0 is trivially exploitable.", "CVE-2015-4335"),
    (9200,  None,           "high",     "Elasticsearch exposed",
     "Elasticsearch open to network — check auth is enabled (≥8.0 enforces by default).", ""),
    (2375,  None,           "critical", "Docker daemon exposed (no TLS)",
     "Unauthenticated Docker API gives root-equivalent access.", ""),
    (2379,  None,           "high",     "etcd exposed",
     "etcd stores cluster secrets. Should only be accessible to trusted hosts.", ""),
    (4848,  None,           "high",     "GlassFish Admin Console",
     "Default credentials admin/admin are common.", ""),
    (8069,  None,           "medium",   "Odoo exposed",
     "Ensure default admin credentials have been changed.", ""),
    (5432,  None,           "info",     "PostgreSQL exposed",
     "Ensure pg_hba.conf restricts access; disable trust auth.", ""),
    (3306,  None,           "info",     "MySQL / MariaDB exposed",
     "Ensure remote root login is disabled.", ""),
    (1433,  None,           "info",     "MSSQL exposed",
     "Ensure sa account is disabled or has a strong password.", ""),
]

# banner substring → hint
_BANNER_RULES: list[tuple[str, str, str, str, str]] = [
    # banner_substr        sev        title                              detail                                          ref
    ("openssh_7.",  "high",     "Outdated OpenSSH (7.x)",
     "OpenSSH 7.x has known vulnerabilities. Upgrade to ≥9.x.", ""),
    ("openssh_8.0", "medium",   "Outdated OpenSSH (8.0)",
     "OpenSSH 8.0 has known vulnerabilities. Upgrade to ≥9.x.", ""),
    ("openssh_8.1", "medium",   "Outdated OpenSSH (8.1)",
     "OpenSSH 8.1 has known vulnerabilities. Upgrade to ≥9.x.", ""),
    ("apache/2.2",  "high",     "Outdated Apache (2.2)",
     "Apache 2.2 reached EOL in 2017. Upgrade to 2.4.x.", ""),
    ("apache/2.4.4","medium",   "Potentially outdated Apache",
     "Apache 2.4.4x — check exact patch level for CVEs.", ""),
    ("nginx/1.1",   "high",     "Outdated nginx (1.1x)",
     "nginx 1.1x is very old. Upgrade to current stable.", ""),
    ("php/5.",      "critical", "PHP 5 (EOL)",
     "PHP 5 reached EOL in 2018 and has numerous unpatched CVEs.", ""),
    ("php/7.0",     "high",     "PHP 7.0 (EOL)",
     "PHP 7.0 EOL since 2019.", ""),
    ("php/7.1",     "high",     "PHP 7.1 (EOL)",
     "PHP 7.1 EOL since 2019.", ""),
    ("php/7.2",     "high",     "PHP 7.2 (EOL)",
     "PHP 7.2 EOL since 2020.", ""),
    ("python/2.",   "high",     "Python 2 (EOL)",
     "Python 2 EOL since 2020. Upgrade to Python 3.", ""),
    ("ssl/2",       "critical", "SSLv2 in use",
     "SSLv2 is cryptographically broken.", "CVE-2011-3389"),
    ("ssl/3",       "critical", "SSLv3 in use",
     "SSLv3 vulnerable to POODLE attack.", "CVE-2014-3566"),
    ("tls/1.0",     "high",     "TLS 1.0 in use",
     "TLS 1.0 is deprecated (PCI-DSS non-compliant).", ""),
    ("tls/1.1",     "high",     "TLS 1.1 in use",
     "TLS 1.1 is deprecated. Use TLS 1.2+.", ""),
    ("vsftpd 2.3.4","critical", "vsftpd 2.3.4 backdoor",
     "This version contains a backdoor on port 6200.", "CVE-2011-2523"),
    ("proftpd 1.3.3","critical","ProFTPD 1.3.3 RCE",
     "Known remote code execution vulnerability.", "CVE-2010-4221"),
    ("default password","high", "Default credentials hint",
     "Banner or title mentions 'default password'. Change immediately.", ""),
    ("admin/admin", "critical", "Default credentials in banner",
     "Credentials admin/admin visible in response.", ""),
]


def scan(open_ports: list[int], banners: list[str],
         http_title: str = "") -> list[VulnHint]:
    hints: list[VulnHint] = []
    seen: set[str] = set()
    ports = set(open_ports)
    all_banners = [b.lower() for b in banners] + [http_title.lower()]

    for port, banner_frag, sev, title, detail, ref in _PORT_RULES:
        if port is not None and port not in ports:
            continue
        if banner_frag and not any(banner_frag in b for b in all_banners):
            continue
        if title not in seen:
            hints.append(VulnHint(sev, title, detail, ref))
            seen.add(title)

    for frag, sev, title, detail, ref in _BANNER_RULES:
        if any(frag in b for b in all_banners):
            if title not in seen:
                hints.append(VulnHint(sev, title, detail, ref))
                seen.add(title)

    # sort by severity
    order = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    hints.sort(key=lambda h: order.get(h.severity, 9))
    return hints


if __name__ == "__main__":
    hints = scan(
        [22, 21, 23, 3306, 6379],
        ["SSH-2.0-OpenSSH_7.9p1 Debian", "220 ProFTPD 1.3.3c Server"],
        http_title="MySQL Admin",
    )
    for h in hints:
        print(f"[{h.severity.upper():<8}] {h.title}")
        print(f"           {h.detail}")
        if h.ref: print(f"           Ref: {h.ref}")
