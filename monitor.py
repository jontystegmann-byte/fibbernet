#!/usr/bin/env python3
"""Local macOS broadband evidence collector. Python standard library only."""
import argparse
import csv
import fcntl
import html
import io
import json
import math
import os
from pathlib import Path
import plistlib
import smtplib
import sqlite3
import ssl
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import mail_templates
import report_style

SOURCE_ROOT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('INTERNET_MONITOR_HOME', SOURCE_ROOT))
RUNNER = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(SOURCE_ROOT / 'monitor.py')]
LABEL = "local.internet-monitor"
FIELDS = ["timestamp_utc", "status", "download_mbps", "upload_mbps", "latency_ms", "interface", "error", "raw_file", "notes"]


def now():
    return datetime.now(timezone.utc)


def config():
    c = json.loads((ROOT / "config.json").read_text())
    return validate_config(c)


def validate_config(c):
    for name in ("plan_mbps", "threshold_mbps", "average_hours", "minimum_samples", "report_days"):
        if isinstance(c[name], bool) or not isinstance(c[name], (int, float)) or not math.isfinite(c[name]) or c[name] <= 0:
            raise ValueError(f"{name} must be positive")
    if not c["hours"] or any(type(h) is not int or not 0 <= h <= 23 for h in c["hours"]):
        raise ValueError("hours must contain local hours from 0 to 23")
    if type(c['minimum_samples']) is not int or type(c['report_days']) is not int:
        raise ValueError('Minimum samples and report days must be whole numbers')
    e = c['email']
    if type(e['enabled']) is not bool or type(e['port']) is not int or not 1 <= e['port'] <= 65535:
        raise ValueError('Invalid email enabled flag or SMTP port')
    if e['security'] not in ('ssl', 'starttls'):
        raise ValueError('Choose SSL or STARTTLS for email security')
    if not isinstance(e['cooldown_hours'], (int, float)) or not math.isfinite(e['cooldown_hours']) or e['cooldown_hours'] < 1:
        raise ValueError('Email cooldown must be at least one hour')
    if not isinstance(e['to'], list) or any(not isinstance(x, str) for x in e['to']):
        raise ValueError('Email recipients must be a list of addresses')
    addresses = [e['from'], *e['to'], *[c.get('profile', {}).get(k, '') for k in ('user_email', 'provider_email')]]
    for addr in addresses:
        if not isinstance(addr, str) or '\r' in addr or '\n' in addr or (addr and (addr.count('@') != 1 or any(ch.isspace() for ch in addr) or not all(addr.split('@')))):
            raise ValueError('Enter valid email addresses, without names or spaces')
    if e['enabled'] and not all((e['from'], e['to'], all(e['to']), e['host'], e['username'])):
        raise ValueError('Complete sender, recipient and SMTP settings before enabling email')
    rendered = mail_templates.draft(c, [])
    if '\n' in rendered['subject'] or '\r' in rendered['subject']:
        raise ValueError('Email subject must be a single line')
    return c


class DatabaseConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def database():
    (ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ROOT / "data" / "measurements.sqlite3", factory=DatabaseConnection)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS measurements (timestamp_utc TEXT, status TEXT, download_mbps REAL, upload_mbps REAL, latency_ms REAL, interface TEXT, error TEXT, raw_file TEXT, notes TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)")
    db.commit()
    return db


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid measurement: {value!r}")
    return float(value)


def parse_result(raw):
    # macOS 14 networkQuality emits *_throughput in bits/s. Its bundled
    # manual incorrectly labels these bytes/s. Verified against human output.
    def mbps(prefix):
        if prefix + "_capacity" in raw:
            return numeric(raw[prefix + "_capacity"]) / 1_000_000
        return numeric(raw[prefix + "_throughput"]) / 1_000_000
    if raw.get("error_code", 0) or raw.get("error_domain"):
        raise ValueError(f"networkQuality error: {raw.get('error_domain')} {raw.get('error_code')}")
    return mbps("dl"), mbps("ul"), numeric(raw["base_rtt"]) if "base_rtt" in raw else None


def collect(db, c):
    timestamp = now().isoformat()
    raw_path = ROOT / "data" / "raw" / f"{now():%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.json"
    cmd = ["/usr/bin/networkQuality", "-c", "-s"]
    if c.get("interface"):
        cmd += ["-I", c["interface"]]
    record = dict.fromkeys(FIELDS)
    record.update(timestamp_utc=timestamp, status="failed", interface=c.get("interface", ""), notes=c.get("connection_notes", ""), raw_file=str(raw_path.relative_to(ROOT)))
    evidence = {"started_utc": timestamp, "command": cmd}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        evidence.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        if result.returncode:
            raise ValueError(f"networkQuality exited {result.returncode}: {result.stderr.strip()[:1000]}")
        raw = json.loads(result.stdout)
        evidence["result"] = raw
        record["download_mbps"], record["upload_mbps"], record["latency_ms"] = parse_result(raw)
        record.update(status="ok", interface=raw.get("interface_name", c.get("interface", "")), error="")
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        record["error"] = str(exc)
        evidence["failure"] = str(exc)
    evidence["completed_utc"] = now().isoformat()
    raw_path.write_text(json.dumps(evidence, indent=2))
    db.execute(f"INSERT INTO measurements VALUES ({','.join('?' for _ in FIELDS)})", [record[k] for k in FIELDS])
    db.commit()
    return record


def rows_since(db, hours):
    cutoff = (now() - timedelta(hours=hours)).isoformat()
    return [dict(r) for r in db.execute("SELECT * FROM measurements WHERE timestamp_utc >= ? ORDER BY timestamp_utc", (cutoff,))]


def average(rows):
    values = [r["download_mbps"] for r in rows if r["status"] == "ok"]
    return statistics.mean(values) if values else None


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def report(db, c):
    rows = rows_since(db, c["report_days"] * 24)
    good = [r for r in rows if r["status"] == "ok"]
    recent = rows_since(db, c["average_hours"])
    avg = average(rows)
    recent_avg = average(recent)
    fmt = lambda v: f"{v:.1f}" if v is not None else "No data"
    summary = [
        "Broadband speed evidence report",
        f"Generated: {now().isoformat()} | Display timezone: UTC",
        f"Plan: {c['plan_mbps']} Mbps download | Alert threshold: {c['threshold_mbps']} Mbps",
        f"Report window: last {c['report_days']} days",
        f"Successful tests: {len(good)} | Failed tests: {len(rows) - len(good)}",
        f"Average download: {fmt(avg)} Mbps",
        f"Plan delivered: {avg / c['plan_mbps'] * 100:.1f}%" if avg is not None else "Plan delivered: No data",
        f"Minimum / maximum download: {fmt(min((r['download_mbps'] for r in good), default=None))} / {fmt(max((r['download_mbps'] for r in good), default=None))} Mbps",
        f"Tests below threshold: {sum(r['download_mbps'] < c['threshold_mbps'] for r in good)} / {len(good)}",
        f"Last {c['average_hours']}h download average: {fmt(recent_avg)} Mbps ({sum(r['status'] == 'ok' for r in recent)} successful tests)",
        f"Scheduled local hours: {', '.join(f'{h:02}:00' for h in c['hours'])}",
        "Method: macOS networkQuality; sequential download and upload; decimal Mbps.",
        "Averages are arithmetic means of successful sampled tests, not continuous monitoring. Failures are listed separately, never counted as zero.",
        "No measurements occur while this Mac is asleep, off, or logged out. Missed calendar events may coalesce on waking; gaps are not evidence of an outage.",
        "Measurements reflect the device-to-test-server path, including Wi-Fi, VPNs and other traffic. Use Ethernet to the router and record connection conditions for supplier evidence.",
        f"Current connection notes: {c.get('connection_notes', '')}",
    ]
    daily = {}
    for r in rows:
        daily.setdefault(r["timestamp_utc"][:10], []).append(r)
    summary += ["", "Daily averages (UTC):"]
    summary += [f"{day}: {fmt(average(group))} Mbps; {sum(r['status'] == 'ok' for r in group)} successful, {sum(r['status'] != 'ok' for r in group)} failed" for day, group in daily.items()]
    text = "\n".join(summary) + "\n"
    esc = lambda v: html.escape(str(v if v is not None else ""))
    table = "".join("<tr>" + "".join(f"<td>{esc(round(r[k], 2) if isinstance(r[k], float) else r[k])}</td>" for k in FIELDS) + "</tr>" for r in rows)
    document = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Linewatch — Broadband evidence report</title><style>' + report_style.css() + '</style><p class="toolbar">Print this report or use Print → Save as PDF to share it with your supplier.</p><main class="page"><header><div><div class="brand">LINE<span>watch</span></div><p class="eyebrow">BROADBAND MONITOR / MEASUREMENT EVIDENCE</p></div><h1>REPORT<span>.</span></h1></header><pre>' + esc(text) + '</pre><h2>Measurements</h2><table><thead><tr>' + "".join(f"<th>{esc(k.replace('_', ' '))}</th>" for k in FIELDS) + "</tr></thead><tbody>" + table + "</tbody></table></main></html>"
    dest = ROOT / "reports"
    dest.mkdir(exist_ok=True)
    for stem in ("latest", f"report-{now():%Y-%m-%d}"):
        for suffix, content in (("txt", text), ("csv", csv_text(rows)), ("html", document)):
            target = dest / f"{stem}.{suffix}"
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(content)
            tmp.replace(target)
    return text


def email_alert(db, c):
    e = c["email"]
    if not e["enabled"]:
        return "Email alerts disabled"
    rows = rows_since(db, c["average_hours"])
    good = [r for r in rows if r["status"] == "ok"]
    avg = average(rows)
    if len(good) < c["minimum_samples"] or avg >= c["threshold_mbps"]:
        return "No alert: insufficient samples or average above threshold"
    last = db.execute("SELECT value FROM state WHERE key='last_email_utc'").fetchone()
    if last and now() - datetime.fromisoformat(last[0]) < timedelta(hours=e["cooldown_hours"]):
        return "Alert suppressed by cooldown"
    if not e["host"] or not e["to"] or not e["from"] or not e["username"]:
        raise ValueError("Email enabled but SMTP host, username, from or recipients missing")
    if e["security"] not in ("ssl", "starttls"):
        raise ValueError("Email security must be ssl or starttls")
    password = os.environ.get("INTERNET_MONITOR_SMTP_PASSWORD")
    if not password:
        secret = subprocess.run(["/usr/bin/security", "find-generic-password", "-a", e["username"], "-s", e["keychain_service"], "-w"], capture_output=True, text=True, timeout=15)
        if secret.returncode:
            raise ValueError("SMTP password not available in Keychain or environment")
        password = secret.stdout.rstrip("\n")
    message = EmailMessage()
    message["From"], message["To"] = e["from"], ", ".join(e["to"])
    if e.get('use_complaint_template', False):
        drafted = mail_templates.draft(c, rows)
        message['Subject'] = drafted['subject']
        message.set_content(drafted['body'] + '\n\nThe measurement CSV is attached.\n')
    else:
        message["Subject"] = f"Broadband alert: {avg:.1f} Mbps average, below {c['threshold_mbps']} Mbps"
        message.set_content(f"The last {c['average_hours']} hours averaged {avg:.1f} Mbps across {len(good)} successful tests. Plan: {c['plan_mbps']} Mbps.\n\n" + (ROOT / "reports/latest.txt").read_text())
    message.add_attachment(csv_text(rows).encode(), maintype="text", subtype="csv", filename="speed-measurements.csv")
    context = ssl.create_default_context()
    if e["security"] == "ssl":
        client = smtplib.SMTP_SSL(e["host"], e["port"], timeout=30, context=context)
    else:
        client = smtplib.SMTP(e["host"], e["port"], timeout=30)
    with client:
        if e["security"] == "starttls":
            client.starttls(context=context)
        client.login(e["username"], password)
        refused = client.send_message(message)
        if refused:
            raise ValueError("SMTP refused one or more recipients")
    db.execute("INSERT OR REPLACE INTO state VALUES ('last_email_utc', ?)", (now().isoformat(),))
    db.commit()
    return "Email alert sent"


def schedule(c, remove=False):
    path = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    domain = f"gui/{os.getuid()}"
    if remove:
        subprocess.run(["launchctl", "bootout", domain, str(path)], capture_output=True)
        path.unlink(missing_ok=True)
        return "Schedule removed; recorded data retained"
    (ROOT / "logs").mkdir(exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"Label": LABEL, "ProgramArguments": RUNNER + ["run", "--scheduled"], "WorkingDirectory": str(ROOT), "StartCalendarInterval": [{"Hour": h, "Minute": 0} for h in sorted(set(c["hours"]))], "StandardOutPath": str(ROOT / "logs/monitor.log"), "StandardErrorPath": str(ROOT / "logs/error.log"), "ProcessType": "Background"}
    if path.exists():
        subprocess.run(["launchctl", "bootout", domain, str(path)], capture_output=True)
    path.write_bytes(plistlib.dumps(payload))
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    return f"Schedule installed: {path}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "report", "status", "install", "uninstall"])
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    c = config()
    with (ROOT / ".monitor.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another monitor operation is running")
            return
        if args.command in ("install", "uninstall"):
            print(schedule(c, args.command == "uninstall"))
            return
        with database() as db:
            if args.command == "run":
                # launchd can run a missed event after wake; respect the configured window.
                if args.scheduled and not min(c["hours"]) <= datetime.now().hour <= max(c["hours"]):
                    print("Outside configured testing window; skipped")
                    return
                r = collect(db, c)
                print(json.dumps(r))
                report(db, c)
                try:
                    print(email_alert(db, c))
                except Exception as exc:
                    print(f"Email failed; measurements retained: {exc}", file=sys.stderr)
                    sys.exit(1)
                if r["status"] != "ok":
                    sys.exit(1)
            else:
                print(report(db, c))
                if args.command == "status":
                    subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], check=False)


if __name__ == "__main__":
    main()
