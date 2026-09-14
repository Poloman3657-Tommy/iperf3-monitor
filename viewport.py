"""Horizontal chart navigation, independent of Tk and measurement collection."""
import math


def elapsed_label(seconds):
    ticks = round(max(0, seconds) * 100)
    days, ticks = divmod(ticks, 86400 * 100)
    hours, ticks = divmod(ticks, 3600 * 100)
    minutes, ticks = divmod(ticks, 60 * 100)
    return (f'{days}天 ' if days else '') + f'{hours:02}:{minutes:02}:{ticks / 100:05.2f}'


class TimeViewport:
    def __init__(self):
        self.mode = 'all'
        self.left, self.right = 0.0, 60.0

    @staticmethod
    def _total(total):
        if not math.isfinite(total) or total < 0:
            raise ValueError('Invalid timeline length')
        return max(1.0, total)

    @staticmethod
    def _clamp(left, width, total):
        width = max(min(1.0, total), min(width, total))
        left = max(0.0, min(left, total - width))
        return left, left + width

    def limits(self, total):
        total = self._total(total)
        if self.mode == 'all':
            return 0.0, total
        width = self.right - self.left
        if self.mode == 'follow':
            return max(0.0, total - width), total
        return self._clamp(self.left, width, total)

    def set_window(self, left, right, total):
        total = self._total(total)
        if not all(math.isfinite(v) for v in (left, right)) or right <= left:
            raise ValueError('Invalid chart window')
        self.left, self.right = self._clamp(left, right - left, total)
        self.mode = 'manual'

    def zoom(self, factor, anchor, total):
        total = self._total(total)
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError('Invalid zoom factor')
        left, right = self.limits(total)
        anchor = max(left, min(anchor, right))
        fraction = (anchor - left) / (right - left)
        width = max(1.0, min(total, (right - left) * factor))
        start = anchor - fraction * width
        self.set_window(start, start + width, total)

    def pan(self, seconds, total):
        left, right = self.limits(total)
        self.set_window(left + seconds, right + seconds, total)

    def move_to(self, fraction, total):
        left, right = self.limits(total)
        start = self._total(total) * max(0.0, min(1.0, fraction))
        self.set_window(start, start + right - left, total)

    def fractions(self, total):
        total = self._total(total)
        left, right = self.limits(total)
        return left / total, right / total

    def show_all(self):
        self.mode = 'all'

    def follow_latest(self, total):
        left, right = self.limits(total)
        width = right - left if self.mode != 'all' else 60.0
        self.left, self.right, self.mode = 0.0, width, 'follow'

    def focus_event(self, start, end, total):
        padding = max(5.0, (end - start) * 0.5)
        self.set_window(start - padding, end + padding, total)
