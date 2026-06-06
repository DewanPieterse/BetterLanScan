"""Traceroute: parse hop-by-hop path to a destination."""
from __future__ import annotations

import re
import subprocess
import threading
from dataclasses import dataclass, field


@dataclass
class Hop:
    number: int
    ip: str = ""
    hostname: str = ""
    rtt_ms: list[float] = field(default_factory=list)  # up to 3 probes
    is_timeout: bool = False

    @property
    def avg_rtt(self) -> float | None:
        return sum(self.rtt_ms) / len(self.rtt_ms) if self.rtt_ms else None

    @property
    def display(self) -> str:
        name = self.hostname or self.ip or "*"
        if self.is_timeout:
            return f"{self.number:>2}.  * * *"
        rtts = "  ".join(f"{r:.1f} ms" for r in self.rtt_ms)
        extra = f"  ({self.ip})" if self.hostname and self.ip else ""
        return f"{self.number:>2}.  {name}{extra}  {rtts}"


def run(host: str, max_hops: int = 20,
        timeout_s: float = 8.0,
        on_hop: "callable | None" = None) -> list[Hop]:
    """Run traceroute and return list of Hop objects.

    on_hop(hop) is called as each hop arrives (use for live updates).
    """
    hops: list[Hop] = []
    try:
        proc = subprocess.Popen(
            ["traceroute", "-n", "-m", str(max_hops), "-w", "1", host],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        lines: list[str] = []

        def reader():
            for line in proc.stdout:
                lines.append(line)
                _parse_line(line, hops, on_hop)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        t.join(timeout_s + 2)
        proc.terminate()
        proc.wait(1)
    except Exception as e:
        hops.append(Hop(number=0, hostname=f"Error: {e}", is_timeout=True))
    return hops


def _parse_line(line: str, hops: list[Hop],
                on_hop: "callable | None") -> None:
    line = line.strip()
    # Skip header
    if line.startswith("traceroute") or not line:
        return

    # "1  192.168.68.1  0.874 ms  0.712 ms  0.698 ms"
    # "3  * * *"
    m = re.match(r"^\s*(\d+)\s+(.*)", line)
    if not m:
        return
    num = int(m.group(1))
    rest = m.group(2).strip()

    hop = Hop(number=num)
    if re.match(r"^\*[\s\*]*$", rest):
        hop.is_timeout = True
    else:
        # extract IP / hostname
        parts = rest.split()
        if parts:
            if re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                hop.ip = parts[0]
            else:
                hop.hostname = parts[0]
                # ip in parens?
                mp = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", rest)
                if mp: hop.ip = mp.group(1)
        # extract RTTs
        for m2 in re.finditer(r"([\d.]+)\s*ms", rest):
            hop.rtt_ms.append(float(m2.group(1)))

    hops.append(hop)
    if on_hop:
        on_hop(hop)


if __name__ == "__main__":
    print("Traceroute to 8.8.8.8 (max 15 hops):")
    hops = run("8.8.8.8", max_hops=15, on_hop=lambda h: print(h.display))
    print(f"\n{len(hops)} hops total")
