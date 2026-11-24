import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from opportunities.models import (
    Opportunity,
    OpportunityMode,
    OpportunitySkill,
    OpportunityStatus,
    OpportunityType,
)
from orgs.models import Company, Institution
from profiles.models import StudentProfile
from skills.models import Skill, SkillCategory, SkillLevel


@pytest.mark.django_db
class TestRecruiterOpportunityLifecycle:
    @pytest.fixture
    def setup_recruiter(self):
        comp = Company.objects.create(name='Acme Labs', industry='AI', is_approved=False)
        recruiter = User.objects.create_user(
            email='recruiter@acme.com',
            password='Password123',
            role=UserRole.RECRUITER,
            company=comp,
        )
        cat = SkillCategory.objects.create(name='Languages')
        skill = Skill.objects.create(name='Python', category=cat)
        return comp, recruiter, skill

    def test_recruiter_creates_opportunity_as_draft(self, client, setup_recruiter):
        comp, recruiter, _ = setup_recruiter
        client.force_login(recruiter)

        url = reverse('opportunities:opportunity_create')
        deadline = (timezone.now() + timedelta(days=14)).strftime('%Y-%m-%dT%H:%M')
        resp = client.post(url, {
            'title': 'AI Research Intern',
            'type': OpportunityType.INTERNSHIP,
            'mode': OpportunityMode.REMOTE,
            'location': 'Bengaluru',
            'openings': 2,
            'pay_min': 25000,
            'pay_max': 40000,
            'deadline': deadline,
            'min_cgpa': '8.00',
            'programme': 'B.Tech Computer Science',
            'batch': '2026',
            'description': 'Work with state-of-the-art LLMs.',
        })
        assert resp.status_code == 302

        opp = Opportunity.objects.get(title='AI Research Intern')
        assert opp.company == comp
        assert opp.status == OpportunityStatus.DRAFT
        assert opp.openings == 2
        assert opp.pay_min == 25000

    def test_core_rule_5_publishing_requires_approved_company(self, client, setup_recruiter):
        comp, recruiter, skill = setup_recruiter
        client.force_login(recruiter)

        # Create draft opportunity
        deadline = timezone.now() + timedelta(days=10)
        opp = Opportunity.objects.create(
            company=comp,
            title='ML Engineer',
            type=OpportunityType.JOB,
            location='Remote',
            deadline=deadline,
            description='Test role',
            status=OpportunityStatus.DRAFT,
        )
        # Attach skill requirement
        OpportunitySkill.objects.create(opportunity=opp, skill=skill, required_level=SkillLevel.ADVANCED, weight=4)

        # Company is unapproved -> Attempting to publish is rejected
        assert comp.is_approved is False
        publish_url = reverse('opportunities:opportunity_publish', kwargs={'pk': opp.pk})
        client.post(publish_url)
        opp.refresh_from_db()
        assert opp.status == OpportunityStatus.DRAFT

        # Approve company -> Publishing now succeeds
        comp.is_approved = True
        comp.save()

        client.post(publish_url)
        opp.refresh_from_db()
        assert opp.status == OpportunityStatus.PUBLISHED

    def test_publishing_blocked_without_required_skills(self, client, setup_recruiter):
        comp, recruiter, _ = setup_recruiter
        comp.is_approved = True
        comp.save()
        client.force_login(recruiter)

        deadline = timezone.now() + timedelta(days=10)
        opp = Opportunity.objects.create(
            company=comp,
            title='Skill-less Role',
            type=OpportunityType.JOB,
            location='Pune',
            deadline=deadline,
            description='Test role without skills',
            status=OpportunityStatus.DRAFT,
        )

        publish_url = reverse('opportunities:opportunity_publish', kwargs={'pk': opp.pk})
        client.post(publish_url)
        opp.refresh_from_db()
        assert opp.status == OpportunityStatus.DRAFT

    def test_recruiter_can_close_opportunity(self, client, setup_recruiter):
        comp, recruiter, skill = setup_recruiter
        comp.is_approved = True
        comp.save()
        client.force_login(recruiter)

        opp = Opportunity.objects.create(
            company=comp,
            title='Published Role',
            deadline=timezone.now() + timedelta(days=5),
            status=OpportunityStatus.PUBLISHED,
        )
        OpportunitySkill.objects.create(opportunity=opp, skill=skill, required_level=SkillLevel.BEGINNER, weight=1)

        close_url = reverse('opportunities:opportunity_close', kwargs={'pk': opp.pk})
        resp = client.post(close_url)
        assert resp.status_code == 302

        opp.refresh_from_db()
        assert opp.status == OpportunityStatus.CLOSED


@pytest.mark.django_db
class TestAutoCloseExpiredOpportunities:
    def test_management_command_closes_expired_opportunities(self):
        comp = Company.objects.create(name='Alpha Corp', industry='Fintech', is_approved=True)

        # 1. Past deadline (expired)
        past_deadline = timezone.now() - timedelta(days=1)
        opp_expired = Opportunity.objects.create(
            company=comp,
            title='Expired Posting',
            deadline=past_deadline,
            status=OpportunityStatus.PUBLISHED,
        )

        # 2. Future deadline (active)
        future_deadline = timezone.now() + timedelta(days=5)
        opp_active = Opportunity.objects.create(
            company=comp,
            title='Active Posting',
            deadline=future_deadline,
            status=OpportunityStatus.PUBLISHED,
        )

        # Run command
        out = io.StringIO()
        call_command('close_expired_opportunities', stdout=out)

        opp_expired.refresh_from_db()
        opp_active.refresh_from_db()

        assert opp_expired.status == OpportunityStatus.CLOSED
        assert opp_active.status == OpportunityStatus.PUBLISHED
        assert "Successfully auto-closed 1" in out.getvalue()

    def test_read_time_auto_close_on_detail_and_browse(self, client):
        comp = Company.objects.create(name='Beta Tech', industry='EdTech', is_approved=True)
        user = User.objects.create_user(email='student_browse@nuvelle.edu', password='Password123')
        client.force_login(user)

        opp = Opportunity.objects.create(
            company=comp,
            title='Deadline Passed Today',
            deadline=timezone.now() - timedelta(hours=2),
            status=OpportunityStatus.PUBLISHED,
        )

        # Browse view should filter it out and mark it closed
        browse_url = reverse('opportunities:opportunity_list')
        resp = client.get(browse_url)
        assert resp.status_code == 200

        opp.refresh_from_db()
        assert opp.status == OpportunityStatus.CLOSED


@pytest.mark.django_db
class TestStudentBrowsingAndHTMXFilters:
    @pytest.fixture
    def catalog_setup(self):
        comp1 = Company.objects.create(name='Stripe India', industry='Payments', is_approved=True)
        comp2 = Company.objects.create(name='DeepMind', industry='AI', is_approved=True)

        cat = SkillCategory.objects.create(name='Engineering')
        skill_python = Skill.objects.create(name='Python', category=cat)
        skill_rust = Skill.objects.create(name='Rust', category=cat)

        deadline = timezone.now() + timedelta(days=20)

        opp1 = Opportunity.objects.create(
            company=comp1,
            title='Backend Intern',
            type=OpportunityType.INTERNSHIP,
            mode=OpportunityMode.REMOTE,
            location='Remote',
            pay_max=60000,
            deadline=deadline,
            batch='2026',
            status=OpportunityStatus.PUBLISHED,
        )
        OpportunitySkill.objects.create(opportunity=opp1, skill=skill_python, required_level=SkillLevel.INTERMEDIATE, weight=3)

        opp2 = Opportunity.objects.create(
            company=comp2,
            title='Rust Systems Engineer',
            type=OpportunityType.JOB,
            mode=OpportunityMode.ON_SITE,
            location='London',
            pay_max=120000,
            deadline=deadline,
            batch='2025',
            status=OpportunityStatus.PUBLISHED,
        )
        OpportunitySkill.objects.create(opportunity=opp2, skill=skill_rust, required_level=SkillLevel.ADVANCED, weight=5)

        return comp1, comp2, opp1, opp2

    def test_student_htmx_search_and_filters(self, client, catalog_setup):
        _, _, opp1, opp2 = catalog_setup
        user = User.objects.create_user(email='student_filter@nuvelle.edu', password='Password123')
        client.force_login(user)

        url = reverse('opportunities:opportunity_list')

        # Filter by keyword 'Backend'
        resp = client.get(url + '?q=Backend', HTTP_HX_REQUEST='true')
        assert resp.status_code == 200
        content = resp.content.decode()
        assert 'Backend Intern' in content
        assert 'Rust Systems Engineer' not in content

        # Filter by type 'job'
        resp_job = client.get(url + '?type=job', HTTP_HX_REQUEST='true')
        content_job = resp_job.content.decode()
        assert 'Rust Systems Engineer' in content_job
        assert 'Backend Intern' not in content_job

    def test_opportunity_detail_eligibility_report(self, client, catalog_setup):
        _, _, opp1, _ = catalog_setup  # Requires Batch 2026
        opp1.min_cgpa = Decimal('8.50')
        opp1.programme = 'B.Tech CSE'
        opp1.save()

        inst = Institution.objects.create(name='College of Engineering', city='Pune', is_approved=True)
        student_user = User.objects.create_user(email='ineligible_stu@college.edu', password='Password123', role=UserRole.STUDENT)
        # Student has CGPA 7.80 and Batch 2025
        StudentProfile.objects.create(
            user=student_user,
            institution=inst,
            roll_no='PUNE001',
            programme='B.Tech IT',
            batch='2025',
            cgpa=Decimal('7.80'),
        )

        client.force_login(student_user)
        detail_url = reverse('opportunities:opportunity_detail', kwargs={'pk': opp1.pk})
        resp = client.get(detail_url)
        assert resp.status_code == 200
        assert resp.context['is_eligible'] is False
        issues = resp.context['eligibility_issues']
        assert any('minimum CGPA' in i for i in issues)
        assert any('Batch' in i for i in issues)
