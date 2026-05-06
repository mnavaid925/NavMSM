"""Pure-function helpers for shift roster generation."""
from datetime import date, timedelta


def date_range(start: date, end: date):
    """Yield each date from start to end inclusive."""
    if end < start:
        return
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


def split_overlapping(start: date, end: date, existing_ranges):
    """Given a candidate (start, end) and a list of existing (start, end) tuples,
    return the list of remaining sub-ranges that do NOT overlap any existing one.

    Existing ranges are inclusive. Used by the seeder to avoid duplicating
    rosters when re-running ``seed_labor`` against an already-seeded tenant.
    """
    out = [(start, end)]
    for ex_start, ex_end in existing_ranges:
        new_out = []
        for cur_start, cur_end in out:
            if ex_end < cur_start or ex_start > cur_end:
                new_out.append((cur_start, cur_end))
                continue
            if ex_start > cur_start:
                new_out.append((cur_start, ex_start - timedelta(days=1)))
            if ex_end < cur_end:
                new_out.append((ex_end + timedelta(days=1), cur_end))
        out = new_out
        if not out:
            break
    return out
