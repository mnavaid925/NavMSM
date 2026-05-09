"""C.5 — RecallNotice.send actually delivers email via Django send_mail."""
import pytest
from django.core import mail

from apps.compliance import models as cm
from apps.compliance.forms import RecallNoticeForm
from apps.compliance.services.recall import send_notice


@pytest.fixture
def notice(db, recall):
    return cm.RecallNotice.objects.create(
        tenant=recall.tenant, recall=recall, channel='email',
        audience='Distributor partners', recipient_email='partner@example.com',
        subject='URGENT: Product Recall Notice',
        body='Recall body — please discontinue distribution.',
    )


@pytest.mark.django_db
class TestRecallNoticeEmailDelivery:

    def test_send_email_actually_dispatches(self, notice, settings):
        # Test backend captures email in mail.outbox
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        mail.outbox = []
        send_notice(notice)
        notice.refresh_from_db()
        assert notice.status == 'sent'
        assert notice.sent_at is not None
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.subject == 'URGENT: Product Recall Notice'
        assert 'Recall body' in msg.body
        assert notice.notice_number in msg.body
        assert notice.recall.recall_number in msg.body
        assert msg.to == ['partner@example.com']

    def test_send_idempotent_does_not_resend(self, notice, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        mail.outbox = []
        send_notice(notice)
        send_notice(notice)
        send_notice(notice)
        # Still only one email in the outbox — second + third calls hit the
        # is_sendable() guard and short-circuit without re-emailing.
        assert len(mail.outbox) == 1

    def test_non_email_channel_does_not_send(self, db, recall, settings):
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        mail.outbox = []
        letter_notice = cm.RecallNotice.objects.create(
            tenant=recall.tenant, recall=recall, channel='letter',
            audience='Mailing list', subject='Letter recall', body='Letter body',
        )
        send_notice(letter_notice)
        letter_notice.refresh_from_db()
        assert letter_notice.status == 'sent'  # status still flips
        assert len(mail.outbox) == 0  # but no email sent

    def test_email_form_requires_recipient_when_channel_is_email(self, acme, recall):
        f = RecallNoticeForm(
            data={
                'channel': 'email', 'audience': 'X',
                'subject': 'S', 'body': 'B',
                # missing recipient_email
            },
            tenant=acme,
        )
        assert not f.is_valid()
        assert 'recipient_email' in f.errors

    def test_email_form_accepts_blank_recipient_for_letter(self, acme, recall):
        f = RecallNoticeForm(
            data={
                'channel': 'letter', 'audience': 'X',
                'subject': 'S', 'body': 'B',
                'recipient_email': '',
            },
            tenant=acme,
        )
        assert f.is_valid(), f.errors

    def test_send_failure_does_not_roll_back_status(self, notice, settings, monkeypatch):
        """Transient SMTP failures must not block the status transition.

        Operators can re-attempt manually; rolling back would leave the
        recall workflow stuck in `draft` despite an obvious customer
        notification effort.
        """
        settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
        from apps.compliance.services import recall as recall_svc

        def boom(**kwargs):
            raise RuntimeError('SMTP went boom')

        monkeypatch.setattr('django.core.mail.send_mail', boom)
        send_notice(notice)
        notice.refresh_from_db()
        assert notice.status == 'sent', 'transition must not roll back on send failure'
