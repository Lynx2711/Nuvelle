from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from applications.models import Application, ApplicationStatus
from drives.models import Offer, OfferStatus
from opportunities.models import Opportunity, OpportunityStatus, OpportunityType
from orgs.models import Company, Institution
from profiles.models import StudentProfile
from reports.services import (
    export_placement_report_csv,
    export_placement_report_pdf,
    get_placement_statistics,
)


@pytest.fixture
def placement_data_setup(db):
    inst = Institution.objects.create(name="IIT Bombay", city="Mumbai", is_approved=True)
    c1 = Company.objects.create(name="Microsoft", industry="Tech", is_approved=True)
    c2 = Company.objects.create(name="Goldman Sachs", industry="Finance", is_approved=True)

    officer = User.objects.create_user(
        email="tpo@iitb.ac.in", password="Password123", role=UserRole.OFFICER, institution=inst, is_verified=True
    )

    # 3 students: 2 CS, 1 Mech
    u1 = User.objects.create_user(email="cs1@iitb.ac.in", password="Password123", role=UserRole.STUDENT, institution=inst)
    p1 = StudentProfile.objects.create(user=u1, institution=inst, roll_no="CS01", programme="Computer Science", batch="2025", cgpa=Decimal('9.2'), is_placed=True)

    u2 = User.objects.create_user(email="cs2@iitb.ac.in", password="Password123", role=UserRole.STUDENT, institution=inst)
    p2 = StudentProfile.objects.create(user=u2, institution=inst, roll_no="CS02", programme="Computer Science", batch="2025", cgpa=Decimal('8.4'), is_placed=True)

    u3 = User.objects.create_user(email="me1@iitb.ac.in", password="Password123", role=UserRole.STUDENT, institution=inst)
    p3 = StudentProfile.objects.create(user=u3, institution=inst, roll_no="ME01", programme="Mechanical", batch="2025", cgpa=Decimal('7.8'), is_placed=False)

    opp1 = Opportunity.objects.create(company=c1, title="SDE", type=OpportunityType.JOB, location="Bengaluru", deadline=timezone.now() + timedelta(days=5), status=OpportunityStatus.PUBLISHED)
    opp2 = Opportunity.objects.create(company=c2, title="Analyst", type=OpportunityType.JOB, location="Mumbai", deadline=timezone.now() + timedelta(days=5), status=OpportunityStatus.PUBLISHED)

    app1 = Application.objects.create(student=p1, opportunity=opp1, status=ApplicationStatus.ACCEPTED, match_score_at_apply=90)
    app2 = Application.objects.create(student=p2, opportunity=opp2, status=ApplicationStatus.ACCEPTED, match_score_at_apply=85)

    Offer.objects.create(application=app1, package=Decimal('2400000.00'), status=OfferStatus.ACCEPTED)
    Offer.objects.create(application=app2, package=Decimal('1800000.00'), status=OfferStatus.ACCEPTED)

    return {
        'inst': inst,
        'officer': officer,
        'c1': c1,
        'c2': c2,
        'students': (p1, p2, p3),
    }


@pytest.mark.django_db
class TestPlacementReportsAndAnalytics:
    def test_placement_statistics_calculation(self, placement_data_setup):
        inst = placement_data_setup['inst']
        stats = get_placement_statistics(institution=inst)

        # 3 total students, 2 placed -> 66.7%
        assert stats['total_students'] == 3
        assert stats['placed_students'] == 2
        assert stats['placement_rate'] == 66.7
        assert stats['total_offers'] == 2
        assert stats['highest_package'] == Decimal('2400000.00')
        assert stats['average_package'] == Decimal('2100000.00')

        # Department breakdown: CS (2 students, 2 placed -> 100%), Mech (1 student, 0 placed -> 0%)
        cs_data = next(d for d in stats['departments_data'] if d['programme'] == 'Computer Science')
        assert cs_data['total_students'] == 2
        assert cs_data['placed_students'] == 2
        assert cs_data['placement_rate'] == 100.0
        assert cs_data['highest_package'] == Decimal('2400000.00')

        mech_data = next(d for d in stats['departments_data'] if d['programme'] == 'Mechanical')
        assert mech_data['total_students'] == 1
        assert mech_data['placed_students'] == 0
        assert mech_data['placement_rate'] == 0.0

        # Company breakdown
        ms_data = next(c for c in stats['companies_data'] if c['company_name'] == 'Microsoft')
        assert ms_data['offers_count'] == 1
        assert ms_data['highest_package'] == Decimal('2400000.00')

    def test_export_placement_csv(self, placement_data_setup):
        inst = placement_data_setup['inst']
        stats = get_placement_statistics(institution=inst)

        res = export_placement_report_csv(stats)
        assert res.status_code == 200
        assert res['Content-Type'] == 'text/csv'
        content = res.content.decode('utf-8')

        assert "NUVELLE PLACEMENT & RECRUITMENT REPORT" in content
        assert "Computer Science" in content
        assert "Microsoft" in content
        assert "2400000.00" in content

    def test_export_placement_pdf_xhtml2pdf(self, placement_data_setup):
        inst = placement_data_setup['inst']
        stats = get_placement_statistics(institution=inst)

        res = export_placement_report_pdf(stats)
        assert res.status_code == 200
        assert res['Content-Type'] == 'application/pdf'
        assert res.content.startswith(b'%PDF')

    def test_placement_statistics_view(self, client: Client, placement_data_setup):
        officer = placement_data_setup['officer']
        client.force_login(officer)

        url = reverse('reports:placement_statistics')
        res = client.get(url)
        assert res.status_code == 200
        content = res.content.decode()

        assert "Placement Statistics & Reports" in content
        assert "66.7%" in content
        assert "deptPlacementChart" in content
        assert "companyOffersChart" in content
        assert "Computer Science" in content
        assert "Microsoft" in content
