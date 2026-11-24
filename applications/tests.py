from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from applications.models import ApplicationStatus, StatusLog
from applications.services import (
    check_application_eligibility,
    submit_application,
    transition_application_status,
)
from notifications.models import Notification
from opportunities.models import Opportunity, OpportunitySkill, OpportunityStatus, OpportunityType
from orgs.models import Company, Institution
from profiles.models import StudentProfile, StudentSkill, StudentSkillStatus
from skills.models import Skill, SkillCategory, SkillLevel


@pytest.fixture
def institution(db):
    return Institution.objects.create(name="National Institute of Technology", city="Trichy", is_approved=True)


@pytest.fixture
def company(db):
    return Company.objects.create(name="Acme Corp", industry="Tech", is_approved=True)


@pytest.fixture
def unapproved_company(db):
    return Company.objects.create(name="Unapproved Co", industry="Finance", is_approved=False)


@pytest.fixture
def recruiter_user(db, company):
    return User.objects.create_user(
        email="recruiter@acme.com",
        password="Password123",
        role=UserRole.RECRUITER,
        company=company,
        is_verified=True,
    )


@pytest.fixture
def other_recruiter(db, unapproved_company):
    return User.objects.create_user(
        email="recruiter2@other.com",
        password="Password123",
        role=UserRole.RECRUITER,
        company=unapproved_company,
        is_verified=True,
    )


@pytest.fixture
def student_user(db, institution):
    user = User.objects.create_user(
        email="student@nit.edu",
        password="Password123",
        role=UserRole.STUDENT,
        institution=institution,
        is_verified=True,
    )
    StudentProfile.objects.create(
        user=user,
        institution=institution,
        roll_no="CS101",
        programme="B.Tech Computer Science",
        batch="2025",
        cgpa=8.5,
        graduation_year=2025,
    )
    return user


@pytest.fixture
def second_student_user(db, institution):
    user = User.objects.create_user(
        email="student2@nit.edu",
        password="Password123",
        role=UserRole.STUDENT,
        institution=institution,
        is_verified=True,
    )
    StudentProfile.objects.create(
        user=user,
        institution=institution,
        roll_no="CS102",
        programme="B.Tech Electrical",
        batch="2026",
        cgpa=6.8,
        graduation_year=2026,
    )
    return user


@pytest.fixture
def skills(db):
    cat = SkillCategory.objects.create(name="Programming")
    py = Skill.objects.create(category=cat, name="Python")
    sql = Skill.objects.create(category=cat, name="SQL")
    return py, sql


@pytest.fixture
def opportunity(db, company, skills):
    py, sql = skills
    opp = Opportunity.objects.create(
        company=company,
        title="Backend Software Intern",
        type=OpportunityType.INTERNSHIP,
        description="Exciting internship in backend engineering.",
        location="Bengaluru",
        deadline=timezone.now() + timedelta(days=10),
        status=OpportunityStatus.PUBLISHED,
        min_cgpa=7.5,
        programme="Computer Science",
        batch="2025",
    )
    OpportunitySkill.objects.create(opportunity=opp, skill=py, required_level=SkillLevel.ADVANCED, weight=5)  # r=3, w=5
    OpportunitySkill.objects.create(opportunity=opp, skill=sql, required_level=SkillLevel.INTERMEDIATE, weight=3)  # r=2, w=3
    return opp


@pytest.mark.django_db
class TestCoreRule1AndMatchScoreCalculation:
    def test_worked_example_match_score(self, student_user, opportunity, skills):
        """
        Worked example from requirements:
        Required: Python (r=3, w=5), SQL (r=2, w=3)
        Student: Python (level=2), SQL (level=2)
        Expected score:
          coverage Python = 2/3 = 0.6667 -> 5 * (2/3) = 3.3333
          coverage SQL = 2/2 = 1.0 -> 3 * 1.0 = 3.0
          weighted sum = 6.3333 / 8 = 0.791667 -> round(100 * 0.791667) = 79
        """
        py, sql = skills
        profile = student_user.student_profile

        StudentSkill.objects.create(student=profile, skill=py, level=SkillLevel.INTERMEDIATE, status=StudentSkillStatus.VERIFIED)
        StudentSkill.objects.create(student=profile, skill=sql, level=SkillLevel.INTERMEDIATE, status=StudentSkillStatus.VERIFIED)

        app = submit_application(student_profile=profile, opportunity=opportunity)
        assert app.match_score_at_apply == 79


@pytest.mark.django_db
class TestCoreRule2Eligibility:
    def test_eligible_student_can_apply(self, student_user, opportunity):
        profile = student_user.student_profile
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is True
        assert reason is None

    def test_cgpa_below_minimum_fails_with_specific_reason(self, student_user, opportunity):
        profile = student_user.student_profile
        profile.cgpa = 7.0
        profile.save()
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is False
        assert "minimum CGPA of 7.5" in reason

    def test_programme_mismatch_fails_with_specific_reason(self, second_student_user, opportunity):
        profile = second_student_user.student_profile
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is False
        assert "Restricted to candidates in 'Computer Science'" in reason

    def test_batch_mismatch_fails_with_specific_reason(self, student_user, opportunity):
        profile = student_user.student_profile
        profile.batch = "2024"
        profile.save()
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is False
        assert "Restricted to Batch 2025" in reason

    def test_expired_opportunity_fails_with_specific_reason(self, student_user, opportunity):
        profile = student_user.student_profile
        opportunity.deadline = timezone.now() - timedelta(hours=1)
        opportunity.save()
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is False
        assert "deadline" in reason

    def test_unpublished_opportunity_fails(self, student_user, opportunity):
        profile = student_user.student_profile
        opportunity.status = OpportunityStatus.DRAFT
        opportunity.save()
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is False
        assert "not currently published" in reason

    def test_duplicate_application_fails(self, student_user, opportunity):
        profile = student_user.student_profile
        submit_application(student_profile=profile, opportunity=opportunity)
        is_eligible, reason = check_application_eligibility(profile, opportunity)
        assert is_eligible is False
        assert "already submitted an application" in reason


@pytest.mark.django_db
class TestCoreRule3StatusWorkflow:
    def test_valid_status_progression(self, student_user, opportunity, recruiter_user):
        profile = student_user.student_profile
        app = submit_application(student_profile=profile, opportunity=opportunity)
        assert app.status == ApplicationStatus.APPLIED

        # applied -> shortlisted
        transition_application_status(app, ApplicationStatus.SHORTLISTED, recruiter_user)
        app.refresh_from_db()
        assert app.status == ApplicationStatus.SHORTLISTED

        # shortlisted -> interview
        transition_application_status(app, ApplicationStatus.INTERVIEW, recruiter_user)
        app.refresh_from_db()
        assert app.status == ApplicationStatus.INTERVIEW

        # interview -> offered
        transition_application_status(app, ApplicationStatus.OFFERED, recruiter_user)
        app.refresh_from_db()
        assert app.status == ApplicationStatus.OFFERED

        # offered -> accepted
        transition_application_status(app, ApplicationStatus.ACCEPTED, recruiter_user)
        app.refresh_from_db()
        assert app.status == ApplicationStatus.ACCEPTED

        # Verify status logs count (1 initial creation log + 4 status transitions)
        logs = StatusLog.objects.filter(application=app)
        assert logs.count() == 5
        # Verify notifications sent to student (1 submission confirmation + 4 status transitions)
        notifications = Notification.objects.filter(user=student_user)
        assert notifications.count() == 5

    def test_rejection_from_non_final_state(self, student_user, opportunity, recruiter_user):
        profile = student_user.student_profile
        app = submit_application(student_profile=profile, opportunity=opportunity)

        # reject directly from applied
        transition_application_status(app, ApplicationStatus.REJECTED, recruiter_user)
        app.refresh_from_db()
        assert app.status == ApplicationStatus.REJECTED

        # No transitions allowed from rejected
        with pytest.raises(ValidationError):
            transition_application_status(app, ApplicationStatus.APPLIED, recruiter_user)

    def test_invalid_transition_fails(self, student_user, opportunity, recruiter_user):
        profile = student_user.student_profile
        app = submit_application(student_profile=profile, opportunity=opportunity)

        # Cannot skip directly from applied to offered
        with pytest.raises(ValidationError):
            transition_application_status(app, ApplicationStatus.OFFERED, recruiter_user)

    def test_withdrawal_rules(self, student_user, opportunity, recruiter_user):
        profile = student_user.student_profile
        app = submit_application(student_profile=profile, opportunity=opportunity)

        # Student can withdraw while status is applied
        transition_application_status(app, ApplicationStatus.WITHDRAWN, student_user)
        app.refresh_from_db()
        assert app.status == ApplicationStatus.WITHDRAWN

        # Reset status for shortlisted test
        app.status = ApplicationStatus.SHORTLISTED
        app.save()

        # Student CANNOT withdraw once shortlisted
        with pytest.raises(ValidationError) as exc:
            transition_application_status(app, ApplicationStatus.WITHDRAWN, student_user)
        assert "Invalid transition" in str(exc.value)

        # Recruiter cannot withdraw an application
        app.status = ApplicationStatus.APPLIED
        app.save()
        with pytest.raises(ValidationError) as exc2:
            transition_application_status(app, ApplicationStatus.WITHDRAWN, recruiter_user)
        assert "Only the student candidate may withdraw" in str(exc2.value)


@pytest.mark.django_db
class TestCoreRule6RecruiterProfileVisibility:
    def test_recruiter_profile_access_restricted_by_applications(
        self, client: Client, student_user, second_student_user, opportunity, recruiter_user, other_recruiter
    ):
        """
        Recruiters see a student's profile ONLY if that student applied to their opportunity.
        """
        profile1 = student_user.student_profile
        profile2 = second_student_user.student_profile

        # Student 1 applies to Acme's opportunity
        submit_application(student_profile=profile1, opportunity=opportunity)

        # Log in as Acme recruiter
        client.force_login(recruiter_user)

        # Recruiter can view Student 1's profile
        res1 = client.get(reverse('profiles:student_detail', kwargs={'pk': profile1.pk}))
        assert res1.status_code == 200
        assert profile1.roll_no in res1.content.decode()

        # Recruiter cannot view Student 2's profile (has not applied to Acme)
        res2 = client.get(reverse('profiles:student_detail', kwargs={'pk': profile2.pk}))
        assert res2.status_code == 403

        # Another company's recruiter cannot view Student 1's profile
        client.force_login(other_recruiter)
        res3 = client.get(reverse('profiles:student_detail', kwargs={'pk': profile1.pk}))
        assert res3.status_code == 403


@pytest.mark.django_db
class TestRecruiterApplicantManagementAndViews:
    def test_applicant_list_filtering(self, client: Client, student_user, second_student_user, opportunity, recruiter_user, skills):
        py, sql = skills
        p1 = student_user.student_profile
        p2 = second_student_user.student_profile

        # Make student 2 eligible for this opportunity
        p2.programme = "B.Tech Computer Science"
        p2.batch = "2025"
        p2.cgpa = 8.0
        p2.save()

        # Give student 1 verified Python level 3 (CGPA 8.5)
        StudentSkill.objects.create(student=p1, skill=py, level=SkillLevel.ADVANCED, status=StudentSkillStatus.VERIFIED)
        # Give student 2 unverified Python level 2 (CGPA 8.0)
        StudentSkill.objects.create(student=p2, skill=py, level=SkillLevel.INTERMEDIATE, status=StudentSkillStatus.UNVERIFIED)

        # Submit applications directly via service for both students
        app1 = submit_application(student_profile=p1, opportunity=opportunity)
        app2 = submit_application(student_profile=p2, opportunity=opportunity)

        client.force_login(recruiter_user)

        url = reverse('applications:applicant_list', kwargs={'opp_pk': opportunity.pk})
        res = client.get(url)
        assert res.status_code == 200
        assert app1.student.roll_no in res.content.decode()
        assert app2.student.roll_no in res.content.decode()

        # Filter by min_cgpa = 8.2 (Student 1 has 8.5, Student 2 has 8.0)
        res_cgpa = client.get(url, {'min_cgpa': '8.2'})
        assert res_cgpa.status_code == 200
        assert app1.student.roll_no in res_cgpa.content.decode()
        assert app2.student.roll_no not in res_cgpa.content.decode()

        # Filter by skill Python >= level 3
        res_skill = client.get(url, {'skill_id': str(py.pk), 'min_level': '3'})
        assert res_skill.status_code == 200
        assert app1.student.roll_no in res_skill.content.decode()
        assert app2.student.roll_no not in res_skill.content.decode()

        # Filter verified only
        res_verified = client.get(url, {'skill_id': str(py.pk), 'min_level': '2', 'verified_only': '1'})
        assert res_verified.status_code == 200
        assert app1.student.roll_no in res_verified.content.decode()
        assert app2.student.roll_no not in res_verified.content.decode()

    def test_bulk_status_change(self, client: Client, student_user, second_student_user, opportunity, recruiter_user):
        p1 = student_user.student_profile
        p2 = second_student_user.student_profile
        p2.programme = "B.Tech Computer Science"
        p2.batch = "2025"
        p2.cgpa = 8.0
        p2.save()

        app1 = submit_application(student_profile=p1, opportunity=opportunity)
        app2 = submit_application(student_profile=p2, opportunity=opportunity)

        client.force_login(recruiter_user)
        bulk_url = reverse('applications:bulk_status', kwargs={'opp_pk': opportunity.pk})
        post_data = {
            'action_status': ApplicationStatus.SHORTLISTED,
            'selected_applications': [str(app1.pk), str(app2.pk)],
        }
        res = client.post(bulk_url, post_data)
        assert res.status_code == 302

        app1.refresh_from_db()
        app2.refresh_from_db()
        assert app1.status == ApplicationStatus.SHORTLISTED
        assert app2.status == ApplicationStatus.SHORTLISTED

    def test_export_applicants_csv(self, client: Client, student_user, opportunity, recruiter_user):
        profile = student_user.student_profile
        submit_application(student_profile=profile, opportunity=opportunity)

        client.force_login(recruiter_user)
        export_url = reverse('applications:export_csv', kwargs={'opp_pk': opportunity.pk})
        res = client.get(export_url)
        assert res.status_code == 200
        assert res['Content-Type'] == 'text/csv'
        content = res.content.decode('utf-8')
        assert "Roll No,Student Name,Email" in content
        assert profile.roll_no in content
        assert profile.user.email in content
