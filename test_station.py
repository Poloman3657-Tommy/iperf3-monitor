"""Station details preserve radio information and never attribute another peer's data."""
import unittest
import mcs

MAC = 'EA:8C:B6:92:F0:B2'
TX = '960.7 MBit/s 80MHz HE-MCS 9 HE-NSS 2 HE-GI 0 HE-DCM 0'
RX = '1080.6 MBit/s 80MHz HE-MCS 10 HE-NSS 2 HE-GI 0 HE-DCM 0'
STATION = f'''Station {MAC.lower()} (on wlan2.2)
    inactive time: 0 ms
    rx bytes: 12345
    signal: -56 [-58] dBm
    signal avg: -56 dBm
    tx bitrate: {TX}
    rx bitrate: {RX}
'''


class StationTests(unittest.TestCase):
    def parse(self, text):
        self.assertTrue(callable(getattr(mcs, 'parse_station', None)), 'Station parser must be implemented')
        return mcs.parse_station(text, MAC, 'wlan2.2')

    def test_full_bitrates_and_chain_signals_survive_parsing_and_display(self):
        peer = self.parse(STATION)
        self.assertEqual(peer['inactive_time'], '0 ms')
        self.assertEqual(peer['signal'], '-56 [-58] dBm')
        self.assertEqual(peer['signal_avg'], '-56 dBm')
        self.assertEqual(peer['tx_bitrate'], TX)
        self.assertEqual(peer['rx_bitrate'], RX)
        self.assertEqual(peer['missing_fields'], [])
        text = mcs.format_capture(dict(status='OK', peers=[dict(peer, status='OK')]))
        for expected in [f'Station {MAC}', 'inactive time: 0 ms', f'tx bitrate: {TX}', f'rx bitrate: {RX}']:
            self.assertIn(expected, text)
        self.assertNotIn('rx bytes', text)

    def test_accepts_values_on_following_lines(self):
        wrapped = STATION.replace(': ', ':\n\n')
        self.assertEqual(self.parse(wrapped), self.parse(STATION))

    def test_missing_optional_fields_are_explicit_and_legacy_rates_are_valid(self):
        peer = self.parse(f'Station {MAC} (on wlan2.2)\n signal: -50 dBm\n tx bitrate: 6.0 MBit/s\n')
        self.assertIsNone(peer['rx_bitrate'])
        self.assertIn('rx_bitrate', peer['missing_fields'])
        text = mcs.format_capture(dict(status='OK', peers=[peer]))
        self.assertIn('rx bitrate: 未提供', text)
        self.assertEqual(peer['tx_bitrate'], '6.0 MBit/s')

    def test_rejects_other_station_vap_and_empty_command_output(self):
        for raw in ['', 'command failed', f'Station {MAC} (on wlan2.2)',
                    STATION.replace(MAC.lower(), 'aa:bb:cc:dd:ee:ff'), STATION.replace('wlan2.2', 'wlan0.1')]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.parse(raw)

    def test_station_command_is_fixed_and_quoted(self):
        try:
            command = mcs.sudo_command('wlan2.2', 'station', MAC)
        except ValueError:
            self.fail('Command allowlist must support iw station get')
        self.assertEqual(command, "sudo -S -p '' -- sh -lc 'iw dev wlan2.2 station get " + MAC + "'")
        for operation, mac in [('station', MAC + '; reboot'), ('peerratesinfo', MAC), ('reboot', None)]:
            with self.assertRaises(ValueError):
                mcs.sudo_command('wlan2.2', operation, mac)


if __name__ == '__main__':
    unittest.main()
