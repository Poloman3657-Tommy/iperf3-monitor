"""Shared live/export plot; presentation never changes measurement or alarm values."""
import math
from bisect import bisect_left, bisect_right

TIME_FACTORS = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400}
TIME_UNITS = ('auto', *TIME_FACTORS)
MAX_DISPLAY_SAMPLES = 4000


def resolve_time_unit(selection, elapsed):
    if selection not in TIME_UNITS or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('Invalid chart time unit or elapsed time')
    if selection != 'auto':
        return selection
    return next((name for name, limit in [('seconds', 60), ('minutes', 3600), ('hours', 86400)]
                 if elapsed < limit), 'days')


def format_time_tick(seconds, unit):
    return f'{seconds / TIME_FACTORS[unit]:g}'


def _sample_groups(samples):
    groups = [[]]
    for sample in samples:
        start, end, rate = sample['start'], sample['end'], sample['mbps']
        if not all(math.isfinite(v) for v in (start, end, rate)) or start < 0 or end <= start or rate < 0:
            raise ValueError('Invalid chart sample')
        if groups[-1] and abs(start - groups[-1][-1]['end']) > 0.011:
            groups.append([])
        groups[-1].append(sample)
    return [group for group in groups if group]


def _reduce_group(group, budget):
    """Retain actual extrema and low-rate points, never replace them with averages."""
    if len(group) <= budget:
        return group
    width = math.ceil(len(group) / max(1, budget // 5))
    selected = []
    for start in range(0, len(group), width):
        stop = min(len(group), start + width)
        indices = range(start, stop)
        keep = {start, stop-1, min(indices, key=lambda i: group[i]['mbps']),
                max(indices, key=lambda i: group[i]['mbps'])}
        low = [i for i in indices if group[i]['status'] == 'LOW']
        if low:
            keep.add(min(low, key=lambda i: group[i]['mbps']))
        selected.extend(group[i] for i in sorted(keep))
    return selected


def _curve_groups(groups):
    import numpy as np
    if not groups:
        return np.array([]), np.array([])
    xs, ys = [], []
    subdivisions = max(1, min(12, 6000 // max(1, sum(map(len, groups)) - 1)))
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


def curve_points(samples):
    """Bounded smoothstep interpolation through every original interval midpoint."""
    return _curve_groups(_sample_groups(samples))


def visible_samples(samples, left, right):
    """Binary search plus adjacent samples keeps focused redraws independent of history size."""
    first = bisect_left(samples, left, key=lambda s: s['end'])
    last = bisect_right(samples, right, key=lambda s: s['start'])
    return samples[max(0, first-1):min(len(samples), last+1)]


def draw_throughput(ax, samples, warmup, threshold, time_unit='auto', *, x_limits=None):
    """Plot the requested viewport. Overview reduction never modifies source samples."""
    from matplotlib.ticker import FuncFormatter, Locator, MaxNLocator

    ax.clear()
    end = max(warmup + 1, samples[-1]['end'] if samples else 60)
    left, right = x_limits if x_limits is not None else (0, end)
    if not all(math.isfinite(v) for v in (left, right)) or left < 0 or right <= left:
        raise ValueError('Invalid plot viewport')
    unit = resolve_time_unit(time_unit, right-left)
    visible = visible_samples(samples, left, right) if x_limits is not None else samples
    overview = len(visible) > MAX_DISPLAY_SAMPLES
    groups = _sample_groups(visible)
    if overview:
        groups = [_reduce_group(group, max(4, int(MAX_DISPLAY_SAMPLES * len(group) / len(visible)))) for group in groups]
    shown = [sample for group in groups for sample in group]
    ax.axvspan(0, warmup, color='#94a3b8', alpha=0.22, label='Warm-up (ignored)')
    ax.axhline(threshold, color='#c6373e', linestyle='--', linewidth=1, label=f'{threshold:g} Mbps threshold')
    if shown:
        x, y = _curve_groups(groups)
        ax.plot(x, y, color='#2466d6', linewidth=1.5, label='Throughput curve')
        ax.scatter([(s['start'] + s['end']) / 2 for s in shown], [s['mbps'] for s in shown],
                   color='#2466d6', s=7, alpha=0.55, zorder=3,
                   label='Overview extrema' if overview else 'Interval samples')
        lows = [s for s in shown if s['status'] == 'LOW']
        if lows:
            ax.scatter([(s['start'] + s['end']) / 2 for s in lows], [s['mbps'] for s in lows],
                       color='#c6373e', s=20, zorder=4, label='Below threshold')
        spans = []
        previous_low = False
        # Dense overviews use representative LOW dots, not misleading bucket-wide shading.
        for sample in ([] if overview else visible):
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
    ax.set_xlim(left, right)
    ax.set_ylim(0, max(threshold, max((s['mbps'] for s in shown), default=100)) * 1.18)
    class TimeLocator(Locator):
        def __call__(self):
            left, right = self.axis.get_view_interval()
            factor = TIME_FACTORS[unit]
            return MaxNLocator(nbins=6, min_n_ticks=3).tick_values(left / factor, right / factor) * factor

    ax.xaxis.set_major_locator(TimeLocator())
    decimals = max(0, min(12, 1-math.floor(math.log10((right-left) / TIME_FACTORS[unit] / 6))))
    def tick(value, _):
        label = f'{value / TIME_FACTORS[unit]:.{decimals}f}'
        return label.rstrip('0').rstrip('.') if '.' in label else label
    ax.xaxis.set_major_formatter(FuncFormatter(tick))
    ax.set_xlabel(f'Time since traffic started ({unit})')
    ax.set_ylabel('Throughput (Mbps)')
    ax.grid(alpha=0.2)
    ax.legend(loc='upper right', fontsize=8)
    return {'overview': overview, 'visible_samples': len(visible), 'rendered_samples': len(shown)}
