"""Monotonic scheduling: wait after each round, with one overall elapsed-time limit."""
import math


def normalize_schedule(duration, repeat_minutes, total_minutes):
    if duration == 0:
        return 0, 0  # Disabled fields cannot prevent a continuous test from starting.
    for label, value in [('重測等待分鐘', repeat_minutes), ('總排程分鐘', total_minutes)]:
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 525600
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f'{label} 必須為 0–525600 的有限數字。')
    return repeat_minutes, total_minutes


class RepeatSchedule:
    def __init__(self, repeat_minutes, total_minutes, now):
        repeat_minutes, total_minutes = normalize_schedule(1, repeat_minutes, total_minutes)
        if total_minutes <= 0:
            raise ValueError('A repeat schedule needs a positive total duration')
        self.started = now
        self.deadline = now + total_minutes * 60
        self.wait_seconds = repeat_minutes * 60
        self.next_due = now
        self.round_number = 0

    def expired(self, now):
        return now >= self.deadline

    def ready(self, now):
        return not self.expired(now) and self.next_due is not None and now >= self.next_due

    def begin_round(self, now):
        if not self.ready(now):
            raise ValueError('Round is not due or schedule has expired')
        self.round_number += 1
        self.next_due = None

    def finish_round(self, now):
        self.next_due = now + self.wait_seconds
