import pytest
from django.urls import reverse

from accounts.models import User, UserRole
from orgs.models import Company, Institution


@pytest.mark.django_db
class TestOrgApproval:
    def test_institution_and_company_default_unapproved(self):
        inst = Institution.objects.create(name='BITS Pilani', city='Pilani')
        comp = Company.objects.create(name='Google', industry='Tech')

        assert inst.is_approved is False
        assert comp.is_approved is False

    def test_admin_can_toggle_institution_approval(self, client):
        admin = User.objects.create_superuser(email='admin_org@nuvelle.edu', password='Pass1234Admin')
        inst = Institution.objects.create(name='IIIT Hyderabad', city='Hyderabad', is_approved=False)

        client.force_login(admin)
        url = reverse('orgs:toggle_institution_approval', kwargs={'pk': inst.pk})
        resp = client.post(url)
        assert resp.status_code == 302

        inst.refresh_from_db()
        assert inst.is_approved is True

        # Toggle back
        client.post(url)
        inst.refresh_from_db()
        assert inst.is_approved is False

    def test_admin_can_toggle_company_approval(self, client):
        admin = User.objects.create_superuser(email='admin_comp@nuvelle.edu', password='Pass1234Admin')
        comp = Company.objects.create(name='Microsoft', industry='Cloud', is_approved=False)

        client.force_login(admin)
        url = reverse('orgs:toggle_company_approval', kwargs={'pk': comp.pk})
        resp = client.post(url)
        assert resp.status_code == 302

        comp.refresh_from_db()
        assert comp.is_approved is True

    def test_non_admin_cannot_toggle_approval(self, client):
        student = User.objects.create_user(email='hacker@student.edu', password='Password123', role=UserRole.STUDENT)
        comp = Company.objects.create(name='StartupX', industry='AI', is_approved=False)

        client.force_login(student)
        url = reverse('orgs:toggle_company_approval', kwargs={'pk': comp.pk})
        resp = client.post(url)
        assert resp.status_code == 403

        comp.refresh_from_db()
        assert comp.is_approved is False
