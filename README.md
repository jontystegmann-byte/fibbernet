# Linewatch

**Your connection. On record.** A Mac app that measures broadband speed, keeps the evidence and helps you ask your supplier to fix it.

Styled to match the invoice and Blik Plan design system: Inter, JetBrains Mono, bold headings, paper surfaces and red accents. Both fonts are bundled for offline use.

## Install

Download the app for your Mac from [Releases](https://github.com/jontystegmann-byte/broadband-monitor/releases), unzip it and move **Linewatch.app** to Applications before enabling its schedule. The app includes its Python runtime; no separate Python installation is needed. The app is ad-hoc signed, not Apple notarized. macOS may require you to approve it in System Settings → Privacy & Security before its first launch.

Requires macOS 14 or later. `x86_64` downloads are for Intel Macs; `arm64` downloads are for Apple Silicon. Builds are architecture-specific.

## Use it

1. Open **Connection & schedule**. Enter your provider, account reference, plan speed and connection conditions.
2. Select test hours and click **Enable automatic tests**. The initial schedule is **03:00, 08:00, 11:00, 14:00, 17:00 and 20:00**, daily, in your Mac's local timezone.
3. Run your first test from **Overview**. See the rolling average, plan percentage, chart and measurement history.
4. Open the printable report to print or save a PDF. **Open CSV exports** shows timestamped spreadsheet exports in Finder.
5. Use **Email & complaints** to add your name, your email, sender email and provider support email. Edit the subject and complaint, then open a populated draft in your email app. Opening a draft does not send it. Attach a report in your email app if needed.

The Mac must be awake and logged in to take measurements, including at 03:00. Closing Linewatch leaves scheduled tests enabled. The app does not wake the Mac or keep it awake. Missed tests may coalesce on waking; gaps do not prove an internet outage.

## Menu bar and background monitoring

Linewatch lives in the Mac menu bar as a four-bar speed icon. Close the dashboard with its red close button to leave the menu bar app running. Click the menu bar icon to reopen the dashboard, check the download average, run a speed test, open the latest report, or pause/resume scheduled tests. The Dock icon hides while the dashboard is closed and returns when you reopen it.

**Start at Login** is an optional menu toggle using macOS Login Items. macOS may require approval in System Settings; **Login Item Settings…** opens that panel. When launched as a login item, Linewatch starts in the menu bar without opening the dashboard. Start at Login is not enabled automatically.

**Quit Linewatch** removes the menu bar icon and closes the local UI service. The independent scheduled tests keep running. Use **Pause Scheduled Tests** if you want monitoring to stop. Both the menu bar and scheduler require this user to be logged in; measurements also require the Mac to be awake. Closing the app does not allow testing during sleep or while the Mac is powered off.

## Automatic email

Alerts default to **off**. Configure your SMTP server, username, sender, security and port. Store your provider's SMTP app password with **Save password to Keychain**. Use STARTTLS/587 or SSL/465 as specified by your email provider. OAuth-only accounts require a supported SMTP/app-password setup.

Choose whether automatic emails go to **your email** or **your provider support email**, and whether to use a simple speed alert or your editable complaint template. Check the destination carefully before enabling automatic email.

Defaults: average below **700 Mbps** over **24 hours**, at least **3 successful tests**, and at least **24 hours between emails**. Automatic emails include a measurement CSV. Failed sends do not advance the cooldown and are retried on a later test. macOS may ask permission to allow Keychain access.

Template fields: `{provider}`, `{account_reference}`, `{customer_name}`, `{user_email}`, `{plan_mbps}`, `{threshold_mbps}`, `{average_mbps}`, `{window_hours}`, `{sample_count}`, `{below_count}`, `{connection_notes}`. Only these named fields are supported; unknown fields are rejected when saving.

## Measurement method

Linewatch uses Apple's built-in `networkQuality -c -s` to measure download and upload sequentially. It records throughput, idle latency, interface, timestamp, conditions, failures and the original output. Averages are arithmetic means of successful samples; failed attempts are never converted to zero speed. Dashboard times are local; report times are UTC. The dashboard shows up to 2,000 recent measurements, a chart of up to 100 successful tests and a table of the last 50 attempts; reports include every attempt in the selected report window, and the database retains the complete history.

Speeds are **Mbps**, not MB/s: 1 Gbps = 1,000 Mbps; 700 Mbps = 87.5 MB/s. Connect the Mac by Ethernet to a gigabit-capable router port for stronger supplier evidence. Wi-Fi, VPNs, other users, adapter limits and the test server can affect results. A speed test alone does not identify the cause or establish a contractual breach. Tests can transfer gigabytes and temporarily use available bandwidth.

## Data and privacy

Data stays in `~/Library/Application Support/Linewatch/`:

- `config.json`: settings, addresses and templates; no SMTP password.
- `data/measurements.sqlite3`: measurement history and last email time.
- `data/raw/`: original JSON/stdout/stderr for each test.
- `reports/`: self-contained printable HTML, plain text and CSV, plus daily snapshots.
- `logs/`: test, app and email diagnostic logs.

SMTP passwords are stored in macOS Keychain, under service `internet-monitor-smtp`. The desktop UI connects to a session-authenticated HTTP service bound only to `127.0.0.1`. The app uses no analytics or hosted database. Speed tests contact Apple's testing infrastructure; enabled automatic email uses your chosen SMTP server.

Source control and release packages exclude settings, personal addresses, passwords, logs, reports and measurements. Back up the Application Support folder to preserve your history. Data is retained until you remove it.

The schedule is `~/Library/LaunchAgents/local.internet-monitor.plist`. Pause it in the app before uninstalling. If you move or replace the app, open it from its final location and re-enable the schedule so the scheduler points to the installed copy.

## Develop and build

Requires Python 3.13, Node (for the JavaScript syntax check), Xcode Command Line Tools and macOS.

```sh
python3 -m unittest -v
node --check assets/app.js
python3 engine.py serve
```

The development service prints a session URL. Open that URL in your browser. To isolate development data, set `INTERNET_MONITOR_HOME` to an empty folder before starting it. Do not install a development schedule against your production data.

```sh
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
bash scripts/build-macos.sh
```

The build produces `dist/Linewatch.app` and an architecture-labelled ZIP. The script builds the Swift/AppKit window and WebKit UI, bundles the Python engine, includes font/runtime notices and verifies its ad-hoc signature. The GitHub Actions workflow tests and builds both Intel and Apple Silicon packages; version tags attach packages to a draft release.

For the original standalone monitor commands, copy `config.example.json` to `config.json` and see [CLI instructions](docs/CLI.md). To import a previous `~/internet-monitor` setup into a fresh Linewatch profile, run `python3 scripts/migrate-legacy.py`, then enable the schedule from the installed app. The import retains the originals and refuses to overwrite an existing Linewatch database.

See [third-party notices](THIRD_PARTY_NOTICES.md) for bundled font and runtime licences.
