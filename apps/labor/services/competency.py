"""Pure-function helpers for competency assessments and certification expiry."""
from datetime import date, timedelta
from decimal import Decimal


def compute_overall_score(results) -> Decimal:
    """Return 0-100 score from an iterable of CompetencyResult-like rows.

    score = avg(actual_level / expected_level) * 100, clamped to [0, 100].
    """
    pairs = [(int(r.expected_level), int(r.actual_level)) for r in results
             if int(r.expected_level) > 0]
    if not pairs:
        return Decimal('0')
    total = sum(min(actual, expected) / expected for expected, actual in pairs)
    avg = total / len(pairs) * 100
    return Decimal(str(round(avg, 2)))


def gap_summary(results):
    """Return a list of (skill_id, expected, actual, gap) tuples sorted by gap desc."""
    rows = [
        (r.skill_id, int(r.expected_level), int(r.actual_level),
         int(r.expected_level) - int(r.actual_level))
        for r in results
    ]
    rows.sort(key=lambda t: t[3], reverse=True)
    return rows


def cert_status_for(expires_at: date, today: date | None = None,
                    *, warning_window_days: int = 30) -> str:
    """Return 'active' / 'expiring_soon' / 'expired' based on dates.

    If ``today`` is None, uses date.today(). Pure - safe to unit-test.
    """
    if expires_at is None:
        return 'active'
    today = today or date.today()
    if expires_at < today:
        return 'expired'
    if expires_at <= today + timedelta(days=warning_window_days):
        return 'expiring_soon'
    return 'active'
