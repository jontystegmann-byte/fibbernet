# Internet speed monitor

This Mac records download and upload speeds using Apple's built-in `networkQuality` tool. No Python packages or paid services are required. It runs locally on the connection used by this Mac, rather than in the cloud.

## Defaults

- Tests at **03:00, 08:00, 11:00, 14:00, 17:00 and 20:00**, every day, in this Mac's local timezone.
- Plan: **1,000 Mbps download**. Alert threshold: **700 Mbps**.
- Rolling average: last **24 hours**, requiring **3 successful tests** before an alert.
- Reports cover the last **30 days** and include daily averages, minimum, maximum, plan percentage, failed attempts and individual measurements.
- Data is retained indefinitely. Email is disabled until configured.

Speeds are decimal megabits per second: 1 Gbps = 1,000 Mbps; 700 Mbps = 87.5 megabytes per second. If the original '70' reading was in MB/s, that equals 560 Mbps.

## Open or export a report

Double-click `Open Report.command` to refresh and open the printable report. Use the browser's Print → Save as PDF to make a PDF for your supplier. The `reports` folder contains:

- `latest.html`: printable report with all measurements in the reporting window.
- `latest.csv`: spreadsheet export of those measurements.
- `latest.txt`: plain-text summary, suitable for an email.
- `report-YYYY-MM-DD.*`: daily snapshots, refreshed each test that day.

The database is `data/measurements.sqlite3`. Original test output and stderr are retained in `data/raw/`, referenced by filename in the exports. Setup diagnostics are stored separately under `data/commissioning/` when applicable.

## Commands

```sh
cd /path/to/broadband-monitor
python3 monitor.py run        # Take a test, save data, refresh reports, evaluate email
python3 monitor.py report     # Refresh reports without taking a test or sending email
python3 monitor.py status     # Report plus macOS scheduler status
python3 monitor.py install    # Install/update the automatic schedule
python3 monitor.py uninstall  # Stop automatic testing, retain all data
python3 -m unittest -v        # Isolated tests; never send real emails
```

`Take Speed Test.command` runs a manual test. Once email is enabled, manual tests also evaluate the alert rule.

Edit `config.json` to adjust thresholds, reporting window or test hours. For a five-hour daytime cadence, use `"hours": [8, 13, 18]`. After changing hours, run `python3 monitor.py install` to update the macOS schedule. Other settings are picked up on the next run.

## Email alerts (future-ready; currently disabled)

Configure the `email` object in `config.json` with your SMTP provider's host, username, sender and recipient addresses. `to` is a list, for example `["you@example.com"]`. Set `security` to `"starttls"` with port 587, or `"ssl"` with port 465, as specified by your provider. OAuth-only providers require an adapter; this implementation supports SMTP password/app-password login.

Store the SMTP app password using **Keychain Access** on this Mac: create a password item named `internet-monitor-smtp`, with Account matching `email.username`. Keep the password out of `config.json`. macOS may ask you to permit the scheduled Python process to access that item. For a foreground run only, the `INTERNET_MONITOR_SMTP_PASSWORD` environment variable is also supported.

After configuring the provider and recipients, set `email.enabled` to `true`. The next test sends an alert if the last 24 hours average below 700 Mbps, with at least 3 successful samples. The email includes the summary and a CSV attachment. At most one alert is sent per 24 hours while the condition persists. Failed sends do not advance the cooldown and retry on a later test. No email has been sent during setup.

## Running and interpreting the measurements

The LaunchAgent is `~/Library/LaunchAgents/local.internet-monitor.plist`. It runs while this user is logged in and the Mac is awake, including for the 03:00 test. It restarts its schedule after login. It does not keep the Mac awake or wake it for tests. macOS may coalesce missed runs on waking; the script skips a delayed run outside the window from the earliest to latest configured hour. A sleeping laptop cannot provide continuous coverage. Use an always-on Mac on this same internet connection for more consistent sampling.

Tests temporarily use available download/upload capacity and can transfer gigabytes at gigabit speeds. They run sequentially to avoid the upload portion competing with the download portion. Tests cannot overlap other instances of this monitor.

Use a wired Ethernet connection to the router for supplier evidence, confirm the adapter/router ports support gigabit, and note VPN use and other traffic in `connection_notes`. Set `interface` (for example `en0`) if you want to pin a network interface; otherwise the system default is used. Historical rows preserve the connection notes used at the time. Tests measure the complete device-to-server path and cannot alone locate the cause of a slowdown or establish a contractual breach.

Report times are UTC; scheduled hours use the Mac's local timezone. Averages are arithmetic means of successful samples, not time-weighted continuous speeds. Failed attempts never count as zero Mbps and gaps do not prove outages. The native tool's human output and JSON throughput fields on this macOS version use bits per second, despite the bundled manual describing the JSON fields as bytes per second.

Logs: `logs/monitor.log` and `logs/error.log`. Measurements, raw output, reports and logs are private local files; email attachments contain interface names and test conditions. New data files are created with owner-only permissions. Back up the project folder to preserve your history. Moving the folder or changing the Python installation requires reinstalling the schedule from its new location.
