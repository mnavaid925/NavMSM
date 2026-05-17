"""Module 20.4 - Integration orchestration.

Outbound HTTP via the `requests` library. The catalog connectors
(SAP / Oracle / Dynamics / NetSuite / Salesforce / HubSpot) ship as
data rows only - they do NOT carry real credentials and are seeded
with ``is_active=False`` so a misconfigured demo doesn't accidentally
fire a request at a production endpoint.

Functions here never import models at module scope so cyclic imports
stay impossible.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.template import Context, Template
from django.utils import timezone


logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10  # seconds


def render(template_str: str, context: dict) -> str:
    if not template_str:
        return ''
    try:
        return Template(template_str).render(Context(context or {}))
    except Exception as exc:
        logger.warning('wfa integration render failed: %s', exc, exc_info=True)
        return template_str


def _execute_http_call(step, ctx):
    """Resolve the connector endpoint + fire one HTTP request.

    Returns ``(ok, response_status, response_body, error)``.
    """
    endpoint = step.endpoint
    if endpoint is None:
        return False, None, '', 'no endpoint configured'
    connector = endpoint.connector
    url = (connector.base_url or '').rstrip('/') + '/' + (endpoint.path or '').lstrip('/')
    headers = dict(endpoint.headers_json or {}) if isinstance(endpoint.headers_json, dict) else {}
    headers.setdefault('Content-Type', 'application/json')
    body_str = render(endpoint.request_template or '', ctx)
    body_payload: Any = body_str
    if body_str.strip().startswith('{') or body_str.strip().startswith('['):
        try:
            body_payload = json.loads(body_str)
        except json.JSONDecodeError:
            body_payload = body_str
    method = (endpoint.method or 'GET').upper()
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body_payload if isinstance(body_payload, (dict, list)) else None,
            data=body_payload if isinstance(body_payload, str) else None,
            timeout=REQUEST_TIMEOUT,
        )
        return resp.ok, resp.status_code, resp.text[:5000], '' if resp.ok else resp.reason
    except requests.RequestException as exc:
        return False, None, '', str(exc)


def _execute_log(step, ctx):
    logger.info('wfa integration log step %s ctx=%s', step.name, ctx)
    return True, None, '', ''


def _execute_transform(step, ctx):
    cfg = step.config_json or {}
    mapping = cfg.get('set', {}) if isinstance(cfg, dict) else {}
    for k, v in mapping.items():
        ctx[str(k)] = v
    return True, None, json.dumps(mapping)[:5000], ''


def _execute_branch(step, ctx):
    cfg = step.config_json or {}
    when = cfg.get('when', '') if isinstance(cfg, dict) else ''
    # Pure boolean over the context dict; we re-use the bpmn_engine
    # whitelist evaluator so the same restrictions apply.
    from apps.wfa.services.bpmn_engine import evaluate_condition, FormulaError
    try:
        ok = evaluate_condition(when, ctx)
    except FormulaError as exc:
        return False, None, '', str(exc)
    return ok, None, str(ok), '' if ok else 'branch condition false'


STEP_EXECUTORS = {
    'http_call': _execute_http_call,
    'log': _execute_log,
    'transform': _execute_transform,
    'branch': _execute_branch,
    'sleep': lambda step, ctx: (True, None, '', ''),
}


def execute_flow(flow, triggered_by=None, initial_context=None):
    """Run every active step of ``flow`` in step_no order.

    Returns the created IntegrationRun row. The caller is responsible
    for surfacing the result to the user.
    """
    from apps.wfa.models import IntegrationRun

    ctx = dict(initial_context or {})
    run = IntegrationRun.all_objects.create(
        tenant=flow.tenant,
        flow=flow,
        status='running',
        triggered_by=triggered_by,
        started_at=timezone.now(),
        result_json={'steps': []},
    )
    overall_ok = True
    step_results = []
    for step in flow.steps.order_by('step_no'):
        fn = STEP_EXECUTORS.get(step.step_type)
        if fn is None:
            step_results.append({'step': step.name, 'ok': False, 'error': 'unknown step type'})
            if step.on_failure == 'abort':
                overall_ok = False
                break
            continue
        try:
            ok, status, body, err = fn(step, ctx)
        except Exception as exc:
            ok, status, body, err = False, None, '', str(exc)
        step_results.append({
            'step': step.name,
            'type': step.step_type,
            'ok': bool(ok),
            'status': status,
            'body': (body or '')[:2000],
            'error': err or '',
        })
        if not ok and step.on_failure == 'abort':
            overall_ok = False
            break
    IntegrationRun.all_objects.filter(pk=run.pk).update(
        status='completed' if overall_ok else 'failed',
        finished_at=timezone.now(),
        error_message='' if overall_ok else 'one or more steps failed (see result_json)',
        result_json={'steps': step_results, 'context': {k: str(v)[:200] for k, v in ctx.items()}},
    )
    run.refresh_from_db()
    return run
