"""Shared live/export plot; presentation never changes measurement or alarm values."""
import math

TIME_FACTORS = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
TIME_UNITS = ('auto', *TIME_FACTORS)


def resolve_time_unit(selection, elapsed):
    if selection not in TIME_UNITS or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('Invalid chart time unit or elapsed time')
    if selection != 'auto':
        return selection
    return next((name for name, limit in [('seconds', 60), ('minutes', 3600), ('hours', 86400)]
                 if elapsed < limit), 'days')


def format_time_tick(seconds, unit):
    return f'{seconds / TIME_FACTORS[unit]:g}'


def curve_points(samples):
    """Smoothstep interpolation through interval midpoints, with no overshoot.

    Each segment is a convex combination of its two actual sample values. Missing
    intervals break the curve. Dense, long runs reduce subdivisions, retaining all
    actual samples while avoiding unbounded interpolation expansion.
    """
    import numpy as np

    if not samples:
        return np.array([]), np.array([])
    groups = [[]]
    for sample in samples:
        start, end, rate = sample['start'], sample['end'], sample['mbps']
        if not all(math.isfinite(v) for v in (start, end, rate)) or start < 0 or end <= start or rate < 0:
            raise ValueError('Invalid chart sample')
        if groups[-1] and abs(start - groups[-1][-1]['end']) > 0.011:
            groups.append([])
        groups[-1].append(sample)
    xs, ys = [], []
    subdivisions = max(1, min(12, 6000 // max(1, len(samples) - 1)))
    u = np.arange(subdivisions, dtype=float) / subdivisions
    weight = u * u * (3 - 2 * u)
    for group in groups:
        x = np.array([(s['start'] + s['end']) / 2 for s in group])
        y = np.array([s['mbps'] for s in group])
        if len(x) > 1 and np.any(np.diff(x) <= 0):
            raise ValueError('Chart samples must be in time order')
        if xs:
            xs.append(np.array([np.nan])); ys.append(np.array([np.nan]))
        # Horizontal half-intervals keep the first/last measured intervals visible.
        xs.append(np.array([group[0]['start']]))
        ys.append(y[:1])
        if len(x) > 1:
            xs.append((x[:-1, None] + np.diff(x)[:, None] * u).ravel())
            values = y[:-1, None] * (1 - weight) + y[1:, None] * weight
            values = np.clip(values, np.minimum(y[:-1], y[1:])[:, None], np.maximum(y[:-1], y[1:])[:, None])
            ys.append(values.ravel())
        xs.append(np.array([x[-1], group[-1]['end']]))
        ys.append(np.array([y[-1], y[-1]]))
    return np.concatenate(xs), np.concatenate(ys)


def draw_throughput(ax, samples, warmup, threshold, time_unit='auto'):
    """Keep coordinates in seconds; convert tick labels only, including saved PNGs."""
    from matplotlib.ticker import FuncFormatter, Locator, MaxNLocator

    ax.clear()
    end = max(warmup + 1, samples[-1]['end'] if samples else 60)
    unit = resolve_time_unit(time_unit, end)
    ax.axvspan(0, warmup, color='#94a3b8', alpha=0.22, label='Warm-up (ignored)')
    ax.axhline(threshold, color='#c6373e', linestyle='--', linewidth=1, label=f'{threshold:g} Mbps threshold')
    if samples:
        x, y = curve_points(samples)
        ax.plot(x, y, color='#2466d6', linewidth=1.5, label='Throughput curve')
        ax.scatter([(s['start'] + s['end']) / 2 for s in samples], [s['mbps'] for s in samples],
                   color='#2466d6', s=7, alpha=0.55, zorder=3, label='Interval samples')
        lows = [s for s in samples if s['status'] == 'LOW']
        if lows:
            ax.scatter([(s['start'] + s['end']) / 2 for s in lows], [s['mbps'] for s in lows],
                       color='#c6373e', s=20, zorder=4, label='Below threshold')
        spans = []
        previous_low = False
        for sample in samples:
            if sample['status'] == 'LOW':
                if previous_low and abs(spans[-1][1] - sample['start']) < 0.011:
                    spans[-1][1] = sample['end']
                else:
                    spans.append([sample['start'], sample['end']])
                previous_low = True
            else:
                previous_low = False
        if spans:
            # One collection keeps redraw cost low even for thousands of low-rate events.
            ax.broken_barh([(start, finish - start) for start, finish in spans], (0, 1),
                           transform=ax.get_xaxis_transform(), facecolors='#ef4444', alpha=0.1)
    else:
        ax.text(0.5, 0.5, 'Waiting for throughput samples', transform=ax.transAxes, ha='center', color='#607487')
    ax.set_xlim(0, end)
    ax.set_ylim(0, max(threshold, max((s['mbps'] for s in samples), default=100)) * 1.18)
    class TimeLocator(Locator):
        def __call__(self):
            left, right = self.axis.get_view_interval()
            factor = TIME_FACTORS[unit]
            return MaxNLocator(nbins=6, min_n_ticks=3).tick_values(left / factor, right / factor) * factor

    ax.xaxis.set_major_locator(TimeLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: format_time_tick(value, unit)))
    ax.set_xlabel(f'Time since traffic started ({unit})')
    ax.set_ylabel('Throughput (Mbps)')
    ax.grid(alpha=0.2)
    ax.legend(loc='upper right', fontsize=8)
