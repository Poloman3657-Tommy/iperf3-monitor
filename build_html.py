"""Build the portable offline HTML; no third-party build dependencies."""
from pathlib import Path

root = Path(__file__).resolve().parent
page = (root / 'html-src' / 'page.html').read_text(encoding='utf-8')
core = (root / 'html-src' / 'core.js').read_text(encoding='utf-8')
if page.count('/* CORE_SCRIPT */') != 1 or '</script' in core.lower():
    raise ValueError('Unsafe or missing script embedding marker')
output = root / 'portable' / 'iperf-monitor.html'
output.parent.mkdir(exist_ok=True)
output.write_text(page.replace('/* CORE_SCRIPT */', core), encoding='utf-8')
print(output)
