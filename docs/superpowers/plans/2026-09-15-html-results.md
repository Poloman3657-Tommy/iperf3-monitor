# Offline HTML Results Implementation Plan

**Goal:** Save a portable, interactive report after every desktop test, including stopped tests.
**Architecture:** A Python exporter embeds authoritative samples, summary and completed SSH records in a standalone HTML/CSS/Canvas viewer. The GUI waits for its diagnostic worker, then writes the report on a separate thread before enabling the next run or closing.
**Tech stack:** Python standard library, browser Canvas and plain JavaScript. No runtime network or CDN.

- [x] Add exporter tests for full data, hostile remote text escaping, latest SSH record, missing data and atomic-save failure.
- [x] Implement `html_report.py` and `report_assets/` with time units, bounded smooth curves, wheel zoom, pointer pan, horizontal scrollbar and event focus.
- [x] Test navigation mathematically in Node, including multi-day extrema and boundary clamping; verify real browser interactions offline.
- [x] Integrate asynchronous final report generation and an Open HTML button in `gui.py`; verify late SSH completion and close/save ordering with native Tk tests.
- [x] Include assets in the Windows bundle and source manifest; update user/developer documentation.
- [x] Run relevant regressions, independent review, packaged relocation check, and publish versioned Windows ZIP/SHA only.

Success means the single copied HTML opens without Python or network, preserves every sample and event, shows the same raw-data statistics and dates, and lets the user zoom/pan/focus fail intervals and inspect Station details. Export failures are visible; no report is silently treated as complete while SSH is still pending. The existing retired standalone measurement HTML is not regenerated.
