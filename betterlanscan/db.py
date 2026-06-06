"""SQLite persistence: device history, notes, favourites, Wi-Fi history, ping log."""
from __future__ import annotations

import ipaddress
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Generator

DB_PATH = Path.home() / "Library" / "Application Support" / "BetterLanScan" / "data.db"


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init() -> None:
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            mac         TEXT PRIMARY KEY,
            ip          TEXT,
            hostname    TEXT DEFAULT '',
            custom_name TEXT DEFAULT '',
            vendor      TEXT DEFAULT '',
            device_type TEXT DEFAULT '',
            os_guess    TEXT DEFAULT '',
            notes       TEXT DEFAULT '',
            is_favourite INTEGER DEFAULT 0,
            first_seen  REAL,
            last_seen   REAL,
            times_seen  INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS scan_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    REAL,
            subnet       TEXT,
            device_count INTEGER
        );
        CREATE TABLE IF NOT EXISTS wifi_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            bssid     TEXT,
            ssid      TEXT,
            rssi      INTEGER,
            channel   INTEGER,
            band      TEXT,
            security  TEXT,
            timestamp REAL
        );
        CREATE TABLE IF NOT EXISTS ping_log (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ip        TEXT,
            timestamp REAL,
            rtt_ms    REAL
        );
        CREATE INDEX IF NOT EXISTS idx_ping_ip    ON ping_log(ip, timestamp);
        CREATE INDEX IF NOT EXISTS idx_wifi_bssid ON wifi_history(bssid, timestamp);
        """)


# ---- device history --------------------------------------------------------

def upsert_device(mac: str, ip: str, hostname: str = "", vendor: str = "",
                  device_type: str = "", os_guess: str = "") -> None:
    if not mac or mac in ("ff:ff:ff:ff:ff:ff", "(incomplete)"):
        return
    now = time.time()
    with _conn() as con:
        row = con.execute("SELECT * FROM devices WHERE mac=?", (mac,)).fetchone()
        if row:
            con.execute("""
                UPDATE devices SET ip=?, hostname=CASE WHEN ?!='' THEN ? ELSE hostname END,
                vendor=CASE WHEN ?!='' THEN ? ELSE vendor END,
                device_type=CASE WHEN ?!='' THEN ? ELSE device_type END,
                os_guess=CASE WHEN ?!='' THEN ? ELSE os_guess END,
                last_seen=?, times_seen=times_seen+1 WHERE mac=?
            """, (ip, hostname, hostname, vendor, vendor, device_type, device_type,
                  os_guess, os_guess, now, mac))
        else:
            con.execute("""
                INSERT INTO devices (mac,ip,hostname,vendor,device_type,os_guess,first_seen,last_seen)
                VALUES (?,?,?,?,?,?,?,?)
            """, (mac, ip, hostname, vendor, device_type, os_guess, now, now))


def get_device(mac: str) -> sqlite3.Row | None:
    with _conn() as con:
        return con.execute("SELECT * FROM devices WHERE mac=?", (mac,)).fetchone()


def get_device_by_ip(ip: str) -> sqlite3.Row | None:
    with _conn() as con:
        return con.execute(
            "SELECT * FROM devices WHERE ip=? ORDER BY last_seen DESC LIMIT 1", (ip,)
        ).fetchone()


def all_devices() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()


def known_macs() -> set[str]:
    with _conn() as con:
        return {r[0] for r in con.execute("SELECT mac FROM devices")}


def set_favourite(mac: str, fav: bool) -> None:
    with _conn() as con:
        con.execute("UPDATE devices SET is_favourite=? WHERE mac=?", (int(fav), mac))


def set_notes(mac: str, notes: str) -> None:
    with _conn() as con:
        con.execute("UPDATE devices SET notes=? WHERE mac=?", (notes, mac))


def set_custom_name(mac: str, name: str) -> None:
    with _conn() as con:
        con.execute("UPDATE devices SET custom_name=? WHERE mac=?", (name, mac))


# ---- scan log --------------------------------------------------------------

def log_scan(subnet: str, device_count: int) -> None:
    with _conn() as con:
        con.execute("INSERT INTO scan_log(timestamp,subnet,device_count) VALUES(?,?,?)",
                    (time.time(), subnet, device_count))


def scan_history(limit: int = 50) -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute(
            "SELECT * FROM scan_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()


# ---- Wi-Fi history ---------------------------------------------------------

def log_wifi(bssid: str, ssid: str, rssi: int, channel: int,
             band: str, security: str) -> None:
    if not bssid:
        return
    with _conn() as con:
        con.execute("""
            INSERT INTO wifi_history(bssid,ssid,rssi,channel,band,security,timestamp)
            VALUES(?,?,?,?,?,?,?)
        """, (bssid, ssid, rssi, channel, band, security, time.time()))
        # keep at most 2000 rows per bssid
        con.execute("""
            DELETE FROM wifi_history WHERE bssid=? AND id NOT IN (
                SELECT id FROM wifi_history WHERE bssid=? ORDER BY timestamp DESC LIMIT 2000
            )
        """, (bssid, bssid))


def wifi_rssi_history(bssid: str, limit: int = 200) -> list[tuple[float, int]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT timestamp, rssi FROM wifi_history WHERE bssid=? ORDER BY timestamp DESC LIMIT ?",
            (bssid, limit)
        ).fetchall()
    return [(r["timestamp"], r["rssi"]) for r in reversed(rows)]


def all_wifi_seen() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("""
            SELECT bssid, ssid, MAX(timestamp) as last_seen,
                   AVG(rssi) as avg_rssi, MIN(rssi) as min_rssi, MAX(rssi) as max_rssi,
                   channel, band, security
            FROM wifi_history GROUP BY bssid ORDER BY last_seen DESC
        """).fetchall()


# ---- ping log --------------------------------------------------------------

def log_ping(ip: str, rtt_ms: float | None) -> None:
    if rtt_ms is None:
        return
    with _conn() as con:
        con.execute("INSERT INTO ping_log(ip,timestamp,rtt_ms) VALUES(?,?,?)",
                    (ip, time.time(), rtt_ms))
        con.execute("""
            DELETE FROM ping_log WHERE ip=? AND id NOT IN (
                SELECT id FROM ping_log WHERE ip=? ORDER BY timestamp DESC LIMIT 500
            )
        """, (ip, ip))


def ping_history(ip: str, limit: int = 60) -> list[tuple[float, float]]:
    with _conn() as con:
        rows = con.execute(
            "SELECT timestamp, rtt_ms FROM ping_log WHERE ip=? ORDER BY timestamp DESC LIMIT ?",
            (ip, limit)
        ).fetchall()
    return [(r["timestamp"], r["rtt_ms"]) for r in reversed(rows)]


if __name__ == "__main__":
    init()
    upsert_device("aa:bb:cc:dd:ee:ff", "192.168.1.5", hostname="test.local",
                  vendor="Apple", device_type="Apple device", os_guess="macOS")
    d = get_device("aa:bb:cc:dd:ee:ff")
    print("device:", dict(d))
    log_wifi("aa:bb:cc:11:22:33", "TestNet", -60, 6, "2.4 GHz", "WPA2 Personal")
    hist = wifi_rssi_history("aa:bb:cc:11:22:33")
    print("wifi hist:", hist)
    log_ping("192.168.1.5", 4.2)
    ph = ping_history("192.168.1.5")
    print("ping hist:", ph)
    print("DB OK:", DB_PATH)
