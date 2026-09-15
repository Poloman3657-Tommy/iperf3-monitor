"""Bounded, read-only SSH station capture; passwords are never part of saved settings."""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
import threading
import time

MAC = r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}'


@dataclass(frozen=True)
class SshSettings:
    enabled: bool = False
    host: str = ''
    port: int = 22
    username: str = 'technician'
    vap: str = 'wlan2.2'

    @property
    def active(self):
        return self.enabled and bool(self.host)

    def validated(self):
        if type(self.enabled) is not bool or type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('SSH enabled 必須是布林值，port 必須是 1–65535。')
        if not all(isinstance(v, str) for v in (self.host, self.username, self.vap)):
            raise ValueError('SSH IP、帳號與 VAP 必須是文字。')
        host, username, vap = self.host.strip(), self.username.strip(), self.vap.strip()
        if host:
            try:
                ipaddress.ip_address(host)
            except ValueError as exc:
                raise ValueError('SSH IP 不合法；留空表示不連線。') from exc
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', username):
            raise ValueError('SSH 帳號格式不合法。')
        if not re.fullmatch(r'wlan\d+(?:\.\d+)?', vap):
            raise ValueError('VAP 格式應為 wlan2.2 或 wlan2。')
        return replace(self, host=host, username=username, vap=vap)


def coerce_settings(value):
    if isinstance(value, SshSettings):
        return value.validated()
    if isinstance(value, dict):
        unknown = value.keys() - SshSettings.__dataclass_fields__.keys()
        if unknown:
            raise ValueError('未知 SSH 設定欄位：' + ', '.join(sorted(unknown)))
        return SshSettings(**value).validated()
    raise ValueError('ssh 設定必須是 JSON object。')


def parse_peers(text):
    peers = list(dict.fromkeys(m.upper() for m in re.findall(r'^\s*(' + MAC + r')\s*$', text, re.MULTILINE)))
    count = re.search(r'(\d+)\s+peer\(s\)\s+connected', text)
    if count is None or int(count[1]) != len(peers):
        raise ValueError('peerlist 的 peer 數量與 MAC 列表不一致。')
    return peers


STATION_FIELDS = {'inactive time': 'inactive_time', 'signal': 'signal', 'signal avg': 'signal_avg',
                  'tx bitrate': 'tx_bitrate', 'rx bitrate': 'rx_bitrate'}


def parse_station(text, mac, vap):
    """Preserve iw's units and PHY details; unavailable driver fields remain explicit."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headers = [re.fullmatch(r'Station (' + MAC + r') \(on ([^)]+)\)', line) for line in lines]
    headers = [header for header in headers if header]
    if len(headers) != 1 or headers[0][1].upper() != mac.upper() or headers[0][2] != vap:
        raise ValueError('iw station 回傳的 Station MAC／VAP 不符或缺少標頭。')
    station = dict(mac=mac.upper(), vap=vap, **dict.fromkeys(STATION_FIELDS.values()))
    for index, line in enumerate(lines):
        label, separator, value = line.partition(':')
        if not separator or label not in STATION_FIELDS:
            continue
        value = value.strip()
        # Also tolerate copied output with the value on the following line.
        if not value and index + 1 < len(lines):
            candidate = lines[index + 1]
            if ':' not in candidate and not candidate.startswith('Station '):
                value = candidate
        key = STATION_FIELDS[label]
        if station[key] is not None:
            raise ValueError(f'iw station 欄位重複：{label}')
        station[key] = value or None
    station['missing_fields'] = [key for key in STATION_FIELDS.values() if station[key] is None]
    if len(station['missing_fields']) == len(STATION_FIELDS):
        raise ValueError('iw station 未回傳 signal／bitrate 等指定欄位。')
    return station


def sudo_command(vap, operation, mac=None):
    if not re.fullmatch(r'wlan\d+(?:\.\d+)?', vap):
        raise ValueError('Invalid VAP')
    if operation == 'station' and mac and re.fullmatch(MAC, mac):
        args = ['iw', 'dev', vap, 'station', 'get', mac]
    elif operation == 'peerlist' and mac is None:
        args = ['dwpal_cli', vap, 'peerlist']
    else:
        raise ValueError('Only dwpal peerlist and iw station get commands are allowed')
    return "sudo -S -p '' -- sh -lc " + shlex.quote(shlex.join(args))


class LowEventGate:
    def __init__(self):
        self.low = False
        self.next_id = 0
        self.previous_end = None

    def observe(self, status, start=None, end=None):
        # Match monitor.summarize: a gap also begins a separate low event.
        contiguous = start is None or self.previous_end is None or abs(self.previous_end - start) < .011
        first = status == 'LOW' and (not self.low or not contiguous)
        self.low = status == 'LOW'
        self.previous_end = end
        if first:
            event_id = self.next_id
            self.next_id += 1
            return event_id
        return None


def _timestamp():
    return datetime.now().astimezone().isoformat()


def _redact(text, password):
    return text.replace(password, '[REDACTED]') if password else text


def _sudo(client, command, password, cancel, deadline):
    if cancel.is_set():
        raise InterruptedError('SSH capture cancelled')
    if time.monotonic() >= deadline:
        raise TimeoutError('SSH command timed out')
    channel = client.get_transport().open_session(timeout=5)
    done = threading.Event()
    def watch_channel():
        # Paramiko exec_request acknowledgements do not use the socket read timeout.
        while not done.wait(.05):
            if cancel.is_set() or time.monotonic() >= deadline:
                channel.close()
                return
    threading.Thread(target=watch_channel, daemon=True).start()
    try:
        channel.settimeout(1)
        channel.exec_command(command)
        # No PTY: the password sent on stdin cannot be echoed as terminal input.
        channel.sendall((password + '\n').encode('utf-8'))
        channel.shutdown_write()
        out, err, size = [], [], 0
        while True:
            if cancel.is_set():
                raise InterruptedError('SSH capture cancelled')
            if time.monotonic() >= deadline:
                raise TimeoutError('SSH command timed out')
            for ready, receive, chunks in [(channel.recv_ready, channel.recv, out),
                                            (channel.recv_stderr_ready, channel.recv_stderr, err)]:
                while ready():
                    data = receive(32768)
                    if not data:
                        break
                    size += len(data)
                    if size > 2 * 1024 * 1024:
                        raise ValueError('SSH command output exceeded 2 MiB')
                    if cancel.is_set() or time.monotonic() >= deadline:
                        raise TimeoutError('SSH command interrupted or timed out')
                    chunks.append(data)
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                code = channel.recv_exit_status()
                break
            time.sleep(.02)
        stdout, stderr = (b''.join(parts).decode('utf-8', errors='replace') for parts in (out, err))
        if code != 0:
            raise RuntimeError(f'sudo/command exit {code}: {_redact((stderr or stdout).strip(), password)[:500]}')
        return stdout
    except Exception as exc:
        if cancel.is_set():
            raise InterruptedError('SSH capture cancelled') from exc
        if time.monotonic() >= deadline:
            raise TimeoutError('SSH command timed out') from exc
        raise
    finally:
        done.set()
        channel.close()


def _save_host_keys(client, path):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.ssh-hosts-', delete=False) as handle:
            temporary = Path(handle.name)
        client.save_host_keys(str(temporary))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture(settings, password, known_hosts, cancel=None, approve_host=None):
    """Return iw station details for all peers, with bounded execution time."""
    settings = coerce_settings(settings)
    result = {'status': 'DISABLED', 'source': 'iw_station', 'host': settings.host, 'port': settings.port,
              'vap': settings.vap, 'started_at': _timestamp(), 'peers': []}
    if not settings.active:
        return result  # Blank IP never opens a socket or requires Paramiko/password.
    cancel = cancel or threading.Event()
    client = None
    done = threading.Event()
    try:
        if not password or any(c in password for c in ('\r', '\n', '\0')):
            raise ValueError('請輸入本次 SSH/sudo 密碼，密碼不可包含換行。')
        import paramiko
        known_hosts = Path(known_hosts)
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        if known_hosts.exists():
            client.load_host_keys(str(known_hosts))

        class ConfirmNewHost(paramiko.MissingHostKeyPolicy):
            def missing_host_key(self, ssh, hostname, key):
                fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
                info = {'host': hostname, 'type': key.get_name(), 'fingerprint': fingerprint}
                if cancel.is_set() or approve_host is None or not approve_host(info):
                    raise paramiko.SSHException(f'主機指紋尚未確認：{hostname} {fingerprint}；請先使用「測試 SSH/Station」。')
                ssh.get_host_keys().add(hostname, key.get_name(), key)
                _save_host_keys(ssh, known_hosts)

        client.set_missing_host_key_policy(ConfirmNewHost())

        def watch_cancel():
            while not done.wait(.1):
                if cancel.is_set():
                    client.close()

        threading.Thread(target=watch_cancel, daemon=True).start()
        if cancel.is_set():
            raise InterruptedError('SSH capture cancelled')
        client.connect(settings.host, port=settings.port, username=settings.username, password=password,
                       timeout=7, banner_timeout=7, auth_timeout=7, channel_timeout=7,
                       allow_agent=False, look_for_keys=False)
        deadline = time.monotonic() + 25
        raw = _sudo(client, sudo_command(settings.vap, 'peerlist'), password, cancel, deadline)
        result['peerlist'] = _redact(raw, password)
        peers = parse_peers(raw)
        for mac in peers:
            if cancel.is_set():
                raise InterruptedError('SSH capture cancelled')
            peer = {'mac': mac}
            result['peers'].append(peer)
            try:
                raw = _sudo(client, sudo_command(settings.vap, 'station', mac), password, cancel, deadline)
                peer['raw'] = _redact(raw, password)
                peer.update(parse_station(peer['raw'], mac, settings.vap), status='OK')
            except Exception as exc:
                peer.update(status='ERROR', error=_redact(str(exc), password))
                if cancel.is_set() or time.monotonic() >= deadline:
                    raise
        result['status'] = 'OK' if peers else 'NO_PEERS'
        failed = sum(p['status'] == 'ERROR' for p in result['peers'])
        if failed:
            result.update(status='ERROR', error=f'{failed}/{len(peers)} 個 peer 查詢失敗，請查看 peers 錯誤明細。')
    except Exception as exc:
        result['status'] = 'CANCELLED' if cancel.is_set() else 'ERROR'
        result['error'] = _redact(str(exc), password)
    finally:
        done.set()
        if client is not None:
            client.close()
        result['finished_at'] = _timestamp()
    return result


class McsDispatcher:
    """One background capture at a time. Busy events are explicitly recorded, never hidden."""
    def __init__(self, settings, password, output, events, known_hosts):
        self.settings, self.password = coerce_settings(settings), password
        self.output, self.events, self.known_hosts = Path(output), events, known_hosts
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.closed = False

    @property
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def _emit(self, result):
        with self.lock:
            try:
                with (self.output / 'mcs-events.jsonl').open('a', encoding='utf-8') as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + '\n')
            except OSError as exc:
                result = {**result, 'status': 'ERROR', 'error': f'Station 紀錄儲存失敗：{exc}'}
        self.events.put(('mcs', result))

    def submit(self, event_id, sample):
        if not self.settings.active:
            return
        trigger = {'event_id': event_id, 'triggered_at': _timestamp(),
                   'detected_at': sample.get('observed_at', ''),
                   'interval_start': sample['start'], 'interval_end': sample['end'], 'mbps': sample['mbps']}
        if self.closed:
            self._emit({**trigger, 'status': 'CANCELLED', 'error': '測試已停止。'})
        elif self.busy:
            self._emit({**trigger, 'status': 'SKIPPED_BUSY', 'error': '前一個 Station 查詢尚未結束。'})
        else:
            self._emit({**trigger, 'status': 'RUNNING'})
            def work():
                try:
                    result = capture(self.settings, self.password, self.known_hosts, self.cancel)
                except Exception as exc:
                    result = {'status': 'ERROR', 'error': _redact(str(exc), self.password)}
                self._emit({**trigger, **result})
            self.thread = threading.Thread(target=work, daemon=True)
            self.thread.start()

    def close(self, timeout=0):
        self.closed = True
        self.cancel.set()
        if self.thread is not None:
            self.thread.join(timeout=timeout)


def result_label(result):
    """Compact table text; the detail panel and JSONL retain full evidence."""
    if not result:
        return '未啟用'
    if result['status'] == 'OK':
        return '; '.join(f"{p['mac']}: TX {(p.get('tx_bitrate') or '未提供').split(' MBit/s')[0]} / RX {(p.get('rx_bitrate') or '未提供').split(' MBit/s')[0]}" for p in result['peers'])
    return {'RUNNING': '查詢中', 'NO_PEERS': '無連線 peer', 'ERROR': '查詢錯誤',
            'CANCELLED': '已取消', 'SKIPPED_BUSY': '略過：前次查詢中',
            'DISABLED': '未啟用'}.get(result['status'], result['status'])


def format_capture(result):
    """Readable station fields, plus capture context and explicit per-peer failures."""
    lines = [f"狀態：{result['status']}"]
    labels = {'event_id': '事件編號（從 1 起）', 'detected_at': 'Fail 偵測日期時間（本機）',
              'host': 'SSH IP', 'vap': 'VAP', 'triggered_at': 'SSH 觸發時間',
              'started_at': 'SSH 查詢開始', 'finished_at': 'SSH 查詢結束', 'error': '錯誤'}
    for key, label in labels.items():
        if key in result:
            value = result[key] + 1 if key == 'event_id' else str(result[key]).replace('T', ' ') if key.endswith('_at') else result[key]
            lines.append(f'{label}: {value or "未提供"}')
    for peer in result.get('peers', []):
        lines.extend(['', f"Station {peer['mac']} (on {peer.get('vap', result.get('vap', '—'))})"])
        if peer.get('error'):
            lines.append(f"錯誤：{peer['error']}")
        for label, key in STATION_FIELDS.items():
            lines.append(f"{label}: {peer.get(key) or '未提供'}")
    return '\n'.join(lines)
