from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from applications.models import ApplicationStatus
from applications.services import submit_application
from drives.models import DriveStatus, OfferStatus, PlacementDrive
from drives.services import (
    create_or_update_offer,
    create_placement_drive,
    get_eligible_students_for_drive,
    respond_to_offer,
)
from opportunities.models import Opportunity, OpportunitySkill, OpportunityStatus, OpportunityType
from orgs.models import Company, Institution
from profiles.models import StudentProfile, StudentSkill, StudentSkillStatus
from skills.models import Skill, SkillCategory, SkillLevel


@pytest.fixture
def test_setup(db):
    inst1 = Institution.objects.create(name="BITS Pilani", city="Pilani", is_approved=True)
    inst2 = Institution.objects.create(name="NIT Trichy", city="Trichy", is_approved=True)

    comp = Company.objects.create(name="Google India", industry="Software", is_approved=True)

    officer_user = User.objects.create_user(
        email="officer@bits.edu", password="Password123", role=UserRole.OFFICER, institution=inst1, is_verified=True
    )
    recruiter_user = User.objects.create_user(
        email="recruiter@google.com", password="Password123", role=UserRole.RECRUITER, company=comp, is_verified=True
    )

    # Student 1 at BITS (eligible: CGPA 8.5, CS, 2025)
    s1_user = User.objects.create_user(
        email="s1@bits.edu", password="Password123", role=UserRole.STUDENT, institution=inst1, is_verified=True
    )
    p1 = StudentProfile.objects.create(
        user=s1_user, institution=inst1, roll_no="BITS_CS01", programme="Computer Science", batch="2025", cgpa=Decimal('8.50')
    )

    # Student 2 at BITS (ineligible: CGPA 6.5, below 7.5 threshold)
    s2_user = User.objects.create_user(
        email="s2@bits.edu", password="Password123", role=UserRole.STUDENT, institution=inst1, is_verified=True
    )
    p2 = StudentProfile.objects.create(
        user=s2_user, institution=inst1, roll_no="BITS_CS02", programme="Computer Science", batch="2025", cgpa=Decimal('6.50')
    )

    # Student 3 at NIT (different institution)
    s3_user = User.objects.create_user(
        email="s3@nitt.edu", password="Password123", role=UserRole.STUDENT, institution=inst2, is_verified=True
    )
    p3 = StudentProfile.objects.create(
        user=s3_user, institution=inst2, roll_no="NITT_CS01", programme="Computer Science", batch="2025", cgpa=Decimal('9.00')
    )

    cat = SkillCategory.objects.create(name="Core")
    py = Skill.objects.create(category=cat, name="Python")
    StudentSkill.objects.create(student=p1, skill=py, level=SkillLevel.ADVANCED, status=StudentSkillStatus.VERIFIED)

    opp = Opportunity.objects.create(
        company=comp,
        title="Software Engineer Intern",
        type=OpportunityType.INTERNSHIP,
        location="Hyderabad",
        deadline=timezone.now() + timedelta(days=15),
        status=OpportunityStatus.PUBLISHED,
        min_cgpa=Decimal('7.50'),
        programme="Computer Science",
        batch="2025",
    )
    OpportunitySkill.objects.create(opportunity=opp, skill=py, required_level=SkillLevel.INTERMEDIATE, weight=5)

    return {
        'inst1': inst1,
        'inst2': inst2,
        'comp': comp,
        'officer': officer_user,
        'recruiter': recruiter_user,
        's1': s1_user,
        'p1': p1,
        'p2': p2,
        'p3': p3,
        'opp': opp,
    }


@pytest.mark.django_db
class TestPlacementDrivesAndEligibility:
    def test_create_placement_drive_with_rounds(self, test_setup):
        opp = test_setup['opp']
        inst = test_setup['inst1']
        officer = test_setup['officer']

        drive = create_placement_drive(
            opportunity=opp,
            institution=inst,
            drive_date=timezone.now().date() + timedelta(days=5),
            venue="Auditorium Hall A",
            rules="Bring 2 copies of resume and college ID.",
            rounds_data=[
                {'name': 'Online Assessment', 'round_date': timezone.now().date() + timedelta(days=5)},
                {'name': 'Technical Interview', 'round_date': timezone.now().date() + timedelta(days=6)},
            ],
            created_by=officer,
        )
        assert drive.pk is not None
        assert drive.status == DriveStatus.SCHEDULED
        assert drive.rounds.count() == 2

    def test_eligible_students_filtering_for_drive(self, test_setup):
        opp = test_setup['opp']
        inst = test_setup['inst1']
        drive = PlacementDrive.objects.create(
            opportunity=opp,
            institution=inst,
            drive_date=timezone.now().date() + timedelta(days=7),
            venue="Seminar Hall",
        )

        eligible = get_eligible_students_for_drive(drive)
        # Only p1 should be eligible (p2 CGPA is low; p3 is at inst2)
        eligible_rolls = [e['student_profile'].roll_no for e in eligible]
        assert "BITS_CS01" in eligible_rolls
        assert "BITS_CS02" not in eligible_rolls
        assert "NITT_CS01" not in eligible_rolls


@pytest.mark.django_db
class TestOffersAndPlacedFlagLifecycle:
    def test_create_offer_and_accept_sets_placed_flag(self, test_setup):
        opp = test_setup['opp']
        p1 = test_setup['p1']
        recruiter = test_setup['recruiter']
        s1 = test_setup['s1']

        app = submit_application(student_profile=p1, opportunity=opp)
        assert p1.is_placed is False

        # Recruiter extends offer of ₹14 LPA
        offer = create_or_update_offer(
            application=app,
            package=Decimal('1400000.00'),
            offered_on=timezone.now().date(),
            notes="Joining bonus ₹1,00,000",
            created_by=recruiter,
        )
        assert offer.status == OfferStatus.PENDING
        app.refresh_from_db()
        assert app.status == ApplicationStatus.OFFERED

        # Student accepts offer
        respond_to_offer(offer, 'accept', user=s1)
        offer.refresh_from_db()
        p1.refresh_from_db()
        app.refresh_from_db()

        assert offer.status == OfferStatus.ACCEPTED
        assert p1.is_placed is True
        assert app.status == ApplicationStatus.ACCEPTED

    def test_student_decline_offer_keeps_unplaced(self, test_setup):
        opp = test_setup['opp']
        p1 = test_setup['p1']
        recruiter = test_setup['recruiter']
        s1 = test_setup['s1']

        app = submit_application(student_profile=p1, opportunity=opp)
        offer = create_or_update_offer(
            application=app,
            package=Decimal('1000000.00'),
            created_by=recruiter,
        )

        respond_to_offer(offer, 'decline', user=s1)
        offer.refresh_from_db()
        p1.refresh_from_db()

        assert offer.status == OfferStatus.DECLINED
        assert p1.is_placed is False


@pytest.mark.django_db
class TestDriveViewsAndExports:
    def test_drive_list_and_detail_views(self, client: Client, test_setup):
        opp = test_setup['opp']
        inst = test_setup['inst1']
        officer = test_setup['officer']

        drive = PlacementDrive.objects.create(
            opportunity=opp,
            institution=inst,
            drive_date=timezone.now().date() + timedelta(days=3),
            venue="Main Lab",
        )

        client.force_login(officer)
        res_list = client.get(reverse('drives:drive_list'))
        assert res_list.status_code == 200
        assert opp.title in res_list.content.decode()

        res_detail = client.get(reverse('drives:drive_detail', kwargs={'pk': drive.pk}))
        assert res_detail.status_code == 200
        assert "Main Lab" in res_detail.content.decode()

    def test_eligible_students_csv_export(self, client: Client, test_setup):
        opp = test_setup['opp']
        inst = test_setup['inst1']
        officer = test_setup['officer']

        drive = PlacementDrive.objects.create(
            opportunity=opp,
            institution=inst,
            drive_date=timezone.now().date() + timedelta(days=3),
            venue="Main Lab",
        )

        client.force_login(officer)
        url = reverse('drives:eligible_students', kwargs={'drive_pk': drive.pk})
        res = client.get(url, {'export': 'csv'})
        assert res.status_code == 200
        assert res['Content-Type'] == 'text/csv'
        content = res.content.decode('utf-8')
        assert "BITS_CS01" in content
        assert "Roll No,Name,Email" in content
