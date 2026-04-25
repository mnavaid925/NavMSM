"""ECO lifecycle: draft → submit → approve → implement (or → reject)."""
import pytest
from django.urls import reverse

from apps.plm.models import EngineeringChangeOrder


@pytest.mark.django_db
class TestECOLifecycle:

    def test_full_happy_path(self, client_acme, acme):
        # 1. Create
        r = client_acme.post(reverse('plm:eco_create'), data={
            'title': 'Material upgrade',
            'description': 'x', 'change_type': 'material', 'priority': 'high',
            'reason': 'cost reduction',
        })
        assert r.status_code == 302
        eco = EngineeringChangeOrder.objects.get(tenant=acme, title='Material upgrade')
        assert eco.status == 'draft'
        assert eco.number.startswith('ECO-')

        # 2. Submit
        client_acme.post(reverse('plm:eco_submit', args=[eco.pk]))
        eco.refresh_from_db()
        assert eco.status == 'submitted'
        assert eco.submitted_at is not None

        # 3. Approve
        client_acme.post(reverse('plm:eco_approve', args=[eco.pk]),
                         data={'comment': 'LGTM'})
        eco.refresh_from_db()
        assert eco.status == 'approved'
        assert eco.approved_at is not None
        assert eco.approvals.filter(decision='approved').exists()

        # 4. Implement
        client_acme.post(reverse('plm:eco_implement', args=[eco.pk]))
        eco.refresh_from_db()
        assert eco.status == 'implemented'
        assert eco.implemented_at is not None

    def test_reject_path(self, client_acme, submitted_eco):
        client_acme.post(reverse('plm:eco_reject', args=[submitted_eco.pk]),
                         data={'comment': 'no'})
        submitted_eco.refresh_from_db()
        assert submitted_eco.status == 'rejected'
        assert submitted_eco.approvals.filter(decision='rejected').exists()

    def test_edit_only_in_draft(self, client_acme, submitted_eco):
        # GET edit form on non-draft ECO redirects with warning
        r = client_acme.get(reverse('plm:eco_edit', args=[submitted_eco.pk]))
        assert r.status_code == 302

        # POST edit on non-draft ECO does not change the title
        r = client_acme.post(reverse('plm:eco_edit', args=[submitted_eco.pk]), data={
            'title': 'HACKED',
            'description': 'x', 'change_type': 'design', 'priority': 'low',
            'reason': 'x',
        })
        submitted_eco.refresh_from_db()
        assert submitted_eco.title != 'HACKED'

    def test_delete_only_in_draft(self, client_acme, submitted_eco):
        r = client_acme.post(reverse('plm:eco_delete', args=[submitted_eco.pk]))
        assert EngineeringChangeOrder.objects.filter(pk=submitted_eco.pk).exists()
