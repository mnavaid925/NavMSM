"""Lightweight test helpers for compliance entities.

We avoid factory-boy (not in requirements) — plain helpers keep the dependency
surface tight and the test code obvious.
"""
from datetime import date, timedelta
from itertools import count

from apps.plm.models import ComplianceStandard, ProductCompliance


_std_seq = count(1)
_cert_seq = count(1)


def make_standard(**kwargs):
    """Return a ComplianceStandard, get_or_create on `code`."""
    code = kwargs.pop('code', None) or f'STD-{next(_std_seq):03d}'
    defaults = {
        'name': f'{code} -- Test Standard',
        'region': 'global',
        'is_active': True,
    }
    defaults.update(kwargs)
    obj, _ = ComplianceStandard.objects.get_or_create(code=code, defaults=defaults)
    return obj


def make_compliance(*, tenant, product, standard=None, **kwargs):
    """Return a ProductCompliance row attached to (tenant, product, standard).

    `standard` defaults to a fresh `make_standard()` so duplicate-trap tests
    can exercise the unique constraint deliberately.
    """
    if standard is None:
        standard = make_standard()
    defaults = {
        'status': 'compliant',
        'certification_number': f'CRT-{next(_cert_seq):05d}',
        'issuing_body': 'TUV',
        'issued_date': date.today() - timedelta(days=180),
        'expiry_date': date.today() + timedelta(days=180),
        'notes': '',
    }
    defaults.update(kwargs)
    return ProductCompliance.objects.create(
        tenant=tenant, product=product, standard=standard, **defaults,
    )
