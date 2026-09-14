"""Real loopback SSH protocol, with a simulated read-only DUT (no device required)."""
from contextlib import contextmanager
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

import paramiko
import mcs

PASSWORD = 'test-only&stdin-secret'
PEERS = '2 peer(s) connected:\nEA:8C:B6:92:F0:B2\nAA:BB:CC:DD:EE:FF\n'
RATES = '-1 : MCS index\n0 : MCS index\n11 : MCS index\n'


class FakeDut(paramiko.ServerInterface):
    def __init__(self, sudo_error=False, malformed=False, hang=False):
        self.commands, self.inputs, self.auth = [], [], []
        self.sudo_error, self.malformed, self.hang = sudo_error, malformed, hang
        self.closed = threading.Event()

    def check_auth_password(self, username, password):
        self.auth.append(username)
        return paramiko.AUTH_SUCCESSFUL if password == PASSWORD else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'password'

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        command = command.decode()
        self.commands.append(command)
        def reply():
            try:
                channel.settimeout(3)
                data = b''
                while not data.endswith(b'\n'):
                    part = channel.recv(1024)
                    if not part:
                        break
                    data += part
                self.inputs.append(data)
                if self.hang:
                    self.closed.wait(5)
                    return
                if self.sudo_error:
                    channel.send_stderr(('sudo failed ' + PASSWORD).encode())
                    channel.send_exit_status(1)
                else:
                    output = PEERS if 'peerlist' in command else ('bad output ' + PASSWORD if self.malformed and 'EA:8C:' in command else RATES)
                    channel.sendall(output.encode())
                    channel.send_exit_status(0)
                channel.shutdown_write()
            except (EOFError, OSError):
                pass  # Client cancellation closes this local test channel.
        threading.Thread(target=reply, daemon=True).start()
        return True


@contextmanager
def server(key, **options):
    dut = FakeDut(**options)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(5)
    transports, channels = [], []
    def serve():
        try:
            connection, _ = listener.accept()
            transport = paramiko.Transport(connection)
            transports.append(transport)
            transport.add_server_key(key)
            transport.start_server(server=dut)
            while transport.is_active() and not dut.closed.is_set():
                channel = transport.accept(.1)
                if channel:
                    channels.append(channel)  # Keep channels alive through their replies.
        except (OSError, EOFError, paramiko.SSHException):
            pass  # Unknown/changed-key tests intentionally abort the handshake.
    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1], dut
    finally:
        dut.closed.set()
        for transport in transports:
            transport.close()
        listener.close()
        thread.join(timeout=2)


class SshTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = paramiko.RSAKey.generate(2048)

    def capture(self, port, hosts, **kwargs):
        settings = mcs.SshSettings(enabled=True, host='127.0.0.1', port=port)
        return mcs.capture(settings, PASSWORD, hosts, **kwargs)

    def test_approved_host_all_peers_sudo_stdin_and_reuse(self):
        with tempfile.TemporaryDirectory() as folder, server(self.key) as (port, dut):
            hosts, approvals = Path(folder) / 'hosts', []
            result = self.capture(port, hosts, approve_host=lambda info: approvals.append(info) or True)
            self.assertEqual(result['status'], 'OK', result)
            self.assertEqual([(p['mcs_1'], p['mcs_2']) for p in result['peers']], [(0, 11), (0, 11)])
            self.assertEqual(dut.auth, ['technician'])
            self.assertEqual(dut.inputs, [(PASSWORD + '\n').encode()] * 3)
            self.assertEqual(dut.commands, [mcs.sudo_command('wlan2.2', 'peerlist'),
                mcs.sudo_command('wlan2.2', 'peerratesinfo', 'EA:8C:B6:92:F0:B2'),
                mcs.sudo_command('wlan2.2', 'peerratesinfo', 'AA:BB:CC:DD:EE:FF')])
            self.assertNotIn(PASSWORD, str(result) + str(dut.commands) + hosts.read_text())
            self.assertTrue(approvals[0]['fingerprint'].startswith('SHA256:'))
            self.assertEqual(paramiko.HostKeys(str(hosts)).lookup(f'[127.0.0.1]:{port}')['ssh-rsa'], self.key)

    def test_unknown_and_changed_keys_rejected_before_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            hosts = Path(folder) / 'hosts'
            with server(self.key) as (port, dut):
                result = self.capture(port, hosts)
                self.assertEqual(result['status'], 'ERROR')
                self.assertIn('指紋', result['error'])
                self.assertFalse(dut.auth)
                self.assertFalse(hosts.exists())
            with server(self.key) as (port, dut):
                keys = paramiko.HostKeys()
                keys.add(f'[127.0.0.1]:{port}', 'ssh-rsa', paramiko.RSAKey.generate(2048))
                keys.save(str(hosts))
                approved = []
                result = self.capture(port, hosts, approve_host=lambda info: approved.append(info) or True)
                self.assertEqual(result['status'], 'ERROR')
                self.assertFalse(approved)
                self.assertFalse(dut.auth)

    def test_known_host_sudo_failure_and_malformed_data_are_visible_redacted(self):
        for options in [dict(sudo_error=True), dict(malformed=True)]:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as folder, server(self.key, **options) as (port, dut):
                hosts = Path(folder) / 'hosts'
                keys = paramiko.HostKeys()
                keys.add(f'[127.0.0.1]:{port}', 'ssh-rsa', self.key)
                keys.save(str(hosts))
                result = self.capture(port, hosts)
                self.assertEqual(result['status'], 'ERROR', result)
                self.assertNotIn(PASSWORD, str(result))
                self.assertIn('[REDACTED]', str(result))
                self.assertTrue(dut.auth)
                if options.get('malformed'):
                    self.assertEqual(len(dut.commands), 3, 'A failed peer must not hide another station')
                    self.assertEqual(result['peers'][1]['mcs_2'], 11)

    def test_stop_cancels_inflight_command(self):
        with tempfile.TemporaryDirectory() as folder, server(self.key, hang=True) as (port, dut):
            cancel, results = threading.Event(), []
            thread = threading.Thread(target=lambda: results.append(self.capture(port, Path(folder) / 'hosts',
                                      cancel=cancel, approve_host=lambda _: True)))
            thread.start()
            deadline = time.monotonic() + 5
            while not dut.inputs and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(dut.inputs)
            cancel.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results[0]['status'], 'CANCELLED')


if __name__ == '__main__':
    unittest.main()
