# Repeat Measurement Schedule

**Goal:** Allow finite-duration rounds to repeat after a wait, bounded by total elapsed minutes. Duration zero disables scheduling.

**Accepted timing:** Wait starts after the previous measurement worker completes, not from the previous round's start. Total elapsed time includes measurement, waiting and file generation. A final partial round is saved when the total deadline arrives.

**Implementation:** `repeat_schedule.py` isolates monotonic timing. `RunConfig` persists `repeat_minutes` / `total_minutes`; total zero preserves a single run for old configs. The GUI locks parameters throughout a schedule, shows countdowns, uses a shared schedule output directory, and starts a new round only after SSH/HTML completion. The collector enforces the deadline independently of Tk. LOW continues; measurement/export errors stop further rounds.

**Verification:** Pure timing/config tests, a silent child killed at deadline with partial data retained, Tk tests for controls/repetition/cancel/report ordering, regression tests, independent review, and a packaged real iperf3 loopback repeat schedule. No external server or SSH device is needed for validation.
