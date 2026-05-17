"""Module 20.3 - Notification dispatch.

Renders templates against a context dict, then fans out per the
template's channels list:

    email     -> Django send_mail (uses the EMAIL_BACKEND setting;
                 dev defaults to console)
    sms       -> writes an SMSDelivery row (stub-only; surfaces wiring
                 without depending on Twilio)
    in_app    -> the Notification row IS the in-app surface; nothing
                 to dispatch externally
    webhook   -> creates a WebhookOutboxEntry for the integration
                 layer to pick up

Every dispatch path writes a NotificationDelivery row so we always
have a per-channel audit trail.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.core.mail import send_mail
from django.template import Context, Template
from django.utils import timezone


logger = logging.getLogger(__name__)


def render_template(template_str: str, context: dict) -> str:
    """Render Django template syntax against ``context``."""
    if not template_str:
        return ''
    try:
        return Template(template_str).render(Context(context or {}))
    except Exception as exc:
        logger.warning('wfa template render failed: %s', exc, exc_info=True)
        return template_str


def _record_delivery(*, notification, channel_code, status, external_ref='', error=''):
    from apps.wfa.models import NotificationChannel, NotificationDelivery

    channel = NotificationChannel.all_objects.filter(
        tenant=notification.tenant, code=channel_code,
    ).first()
    if channel is None:
        return None
    return NotificationDelivery.all_objects.create(
        tenant=notification.tenant,
        notification=notification,
        channel=channel,
        status=status,
        external_ref=external_ref,
        error_message=error or '',
    )


def _dispatch_email(notification):
    try:
        send_mail(
            subject=notification.subject or '(no subject)',
            message=notification.body or '',
            from_email=None,
            recipient_list=[notification.recipient.email] if notification.recipient and notification.recipient.email else [],
            fail_silently=True,
        )
        _record_delivery(
            notification=notification, channel_code='email',
            status='sent',
        )
        return True
    except Exception as exc:
        logger.warning('wfa email send failed: %s', exc, exc_info=True)
        _record_delivery(
            notification=notification, channel_code='email',
            status='failed', error=str(exc),
        )
        return False


def _dispatch_sms(notification):
    """Stub: insert SMSDelivery + NotificationDelivery rows.

    Never actually contacts a provider - swap this implementation when
    Twilio (or equivalent) credentials are wired in.
    """
    from apps.wfa.models import SMSDelivery

    phone = ''
    if notification.recipient and hasattr(notification.recipient, 'profile'):
        prof = getattr(notification.recipient, 'profile', None)
        phone = getattr(prof, 'phone', '') if prof else ''
    if not phone:
        phone = 'unknown'
    try:
        SMSDelivery.all_objects.create(
            tenant=notification.tenant,
            notification=notification,
            to_phone=phone,
            body=notification.body or '',
            status='sent_stub',
        )
        _record_delivery(
            notification=notification, channel_code='sms',
            status='sent',
        )
        return True
    except Exception as exc:
        logger.warning('wfa sms stub failed: %s', exc, exc_info=True)
        _record_delivery(
            notification=notification, channel_code='sms',
            status='failed', error=str(exc),
        )
        return False


def _dispatch_in_app(notification):
    _record_delivery(
        notification=notification, channel_code='in_app',
        status='sent',
    )
    return True


def _dispatch_webhook(notification):
    from apps.wfa.models import WebhookOutboxEntry

    try:
        WebhookOutboxEntry.all_objects.create(
            tenant=notification.tenant,
            target_url=(notification.payload_json or {}).get('webhook_url', ''),
            payload_json={
                'subject': notification.subject,
                'body': notification.body,
                'event_type': notification.event_type,
                'payload': notification.payload_json or {},
            },
            status='pending',
        )
        _record_delivery(
            notification=notification, channel_code='webhook',
            status='sent',
        )
        return True
    except Exception as exc:
        logger.warning('wfa webhook outbox failed: %s', exc, exc_info=True)
        _record_delivery(
            notification=notification, channel_code='webhook',
            status='failed', error=str(exc),
        )
        return False


CHANNEL_DISPATCHERS = {
    'email': _dispatch_email,
    'sms': _dispatch_sms,
    'in_app': _dispatch_in_app,
    'webhook': _dispatch_webhook,
}


def dispatch(notification):
    """Fan out a Notification across the channels its template lists.

    Idempotent: if the Notification is already ``sent`` we re-run the
    channel dispatch only for channels with no successful
    NotificationDelivery row.
    """
    from apps.wfa.models import Notification

    template = getattr(getattr(notification, 'rule', None), 'template', None)
    channels = []
    if template and isinstance(template.channels, list):
        channels = [str(c) for c in template.channels if c]
    if not channels:
        channels = ['in_app']

    already_sent_codes = set(
        notification.deliveries.filter(status='sent').values_list(
            'channel__code', flat=True,
        )
    )
    any_ok = False
    for code in channels:
        if code in already_sent_codes:
            any_ok = True
            continue
        fn = CHANNEL_DISPATCHERS.get(code)
        if fn is None:
            continue
        if fn(notification):
            any_ok = True

    Notification.all_objects.filter(pk=notification.pk).update(
        status='sent' if any_ok else 'failed',
        dispatched_at=timezone.now(),
    )
    notification.refresh_from_db()
    return notification


def create_notification(*, tenant, rule, recipient, payload=None):
    """Create + (optionally) render a Notification row from a NotificationRule."""
    from apps.wfa.models import Notification

    template = rule.template
    ctx = payload or {}
    subject = render_template(template.subject_template if template else '', ctx)
    body = render_template(template.body_template if template else '', ctx)
    return Notification.all_objects.create(
        tenant=tenant,
        rule=rule,
        event_type=rule.event_type,
        recipient=recipient,
        subject=subject[:255],
        body=body,
        payload_json=ctx,
        status='pending',
    )
