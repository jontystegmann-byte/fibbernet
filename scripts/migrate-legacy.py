"""Copy an existing CLI monitor into Linewatch; leave the original as a backup."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3

os.umask(0o077)

source = Path.home() / 'internet-monitor'
target = Path.home() / 'Library/Application Support/Linewatch'
example = Path(__file__).resolve().parents[1] / 'config.example.json'
if not (source / 'data/measurements.sqlite3').exists():
    raise SystemExit('No legacy monitor database found; nothing to import.')
if (target / 'data/measurements.sqlite3').exists():
    raise SystemExit('Linewatch already has a database. No files were overwritten.')
with (source / '.monitor.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.chmod(0o700)
    defaults = json.loads(example.read_text())
    old = json.loads((source / 'config.json').read_text())
    defaults.update({k: v for k, v in old.items() if k != 'email'})
    defaults['email'].update(old.get('email', {}))
    (target / 'config.json').write_text(json.dumps(defaults, indent=2))
    (target / 'data').mkdir(exist_ok=True, mode=0o700)
    src = sqlite3.connect(source / 'data/measurements.sqlite3')
    dst = sqlite3.connect(target / 'data/measurements.sqlite3')
    try:
        src.backup(dst)
    finally:
        src.close(); dst.close()
    for folder in ('raw', 'commissioning'):
        if (source / 'data' / folder).exists():
            shutil.copytree(source / 'data' / folder, target / 'data' / folder, dirs_exist_ok=True)
    print('Imported settings, measurements and raw evidence. Original files retained.')
