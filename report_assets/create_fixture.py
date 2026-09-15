"""Build reproducible four-day browser QA data, without any real device information."""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from gui_runner import RunConfig
from html_report import save_report
import monitor
from test_station import STATION, MAC
from mcs import parse_station, SshSettings

output = root / 'validation' / 'html-report'
output.mkdir(parents=True, exist_ok=True)
base = datetime(2026, 9, 15, 10, 0, tzinfo=timezone(timedelta(hours=8)))
samples = [dict(start=i, end=i+1, mbps=45 if i%2000==21 else round(600+150*math.sin(i/31),3),
                status='WARMUP' if i<20 else 'LOW' if i%2000==21 else 'OK',
                observed_at=(base+timedelta(seconds=i+1)).isoformat()) for i in range(345600)]
peer = dict(parse_station(STATION, MAC, 'wlan2.2'), status='OK', raw='</script><script>globalThis.injected=true</script>')
(output / 'mcs-events.jsonl').write_text(json.dumps(dict(event_id=0, status='OK', peers=[peer])), encoding='utf-8')
save_report(samples, monitor.summarize(samples,'COMPLETE',None), RunConfig(iperf='',ssh=SshSettings(enabled=True,host='192.0.2.10')), output)
print(output / 'report.html')
