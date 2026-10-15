"""Execute and authenticate the native canopy attachment verifier."""
from pathlib import Path
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
report_path = root / 'yellowstone_midway/work/canopy-attachments-final/report.json'
if report_path.exists():
    raise SystemExit('Fresh evidence output required')
command = ['/opt/homebrew/bin/godot', '--path', str(root / 'yellowstone_midway'), '--script', 'res://tools/validate_canopy_attachments.gd', '--', '--out=res://work/canopy-attachments-final']
result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
print(result.stdout, end='')
if result.returncode or 'SCRIPT ERROR:' in result.stdout or '\nERROR:' in result.stdout:
    raise SystemExit(result.returncode or 1)
report = json.loads(report_path.read_text())
if not (report.get('ok') is True and report.get('native_render_verified') is True and report.get('mode') == 'native_source_geometry_and_visibility' and len(report.get('native_views', [])) == 17 and not report.get('failures')):
    raise SystemExit('Native report scope or assertions failed')
print('CANOPY_EVIDENCE verified mode, 17 captures, error-free log and positive result')
