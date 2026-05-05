"""Atomic tool-life helpers.

`bump_tool_life` increments a Tool's `current_cycles` / `current_hours` denorms
via a conditional UPDATE so two concurrent post-save calls cannot stomp one
another. `consume_usage_log` is a higher-level wrapper that emits a
ToolUsageLog row AND bumps the tool atomically.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import F


@transaction.atomic
def bump_tool_life(tool, cycles_added=0, hours_added=Decimal('0')):
    """Atomically increment Tool.current_cycles + current_hours."""
    from apps.eam.models import Tool
    cycles_added = int(cycles_added or 0)
    hours_added = Decimal(hours_added or 0)
    Tool.all_objects.filter(pk=tool.pk).update(
        current_cycles=F('current_cycles') + cycles_added,
        current_hours=F('current_hours') + hours_added,
    )


@transaction.atomic
def consume_usage_log(tool, *, mes_work_order=None, cycles_added=0, hours_added=Decimal('0'),
                     operator=None, notes=''):
    """Emit a ToolUsageLog and bump the tool's denorms in one transaction."""
    from apps.eam.models import ToolUsageLog
    log = ToolUsageLog.all_objects.create(
        tenant=tool.tenant,
        tool=tool,
        mes_work_order=mes_work_order,
        cycles_added=int(cycles_added or 0),
        hours_added=Decimal(hours_added or 0),
        operator=operator,
        notes=notes or '',
    )
    bump_tool_life(tool, cycles_added=cycles_added, hours_added=hours_added)
    return log
