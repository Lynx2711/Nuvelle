from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, UserRole
from matching.services import (
    calculate_batch_skill_map,
    calculate_skill_match_score,
    generate_gap_report,
    get_market_demand_data,
    rank_skills_by_market_demand,
)
from opportunities.models import Opportunity, OpportunitySkill, OpportunityStatus, OpportunityType
from orgs.models import Company, Institution
from profiles.models import StudentProfile, StudentSkill, StudentSkillStatus
from skills.models import RoleProfile, RoleSkill, Skill, SkillCategory, SkillLevel

# =========================================================================
# Unit Tests for Pure Calculation Functions (Core Business Rule 1)
# =========================================================================

class TestPureSkillMatchFormula:
    def test_worked_example_from_spec(self):
        """
        User Specification Worked Example:
          Python: required_level=3, weight=5
          SQL: required_level=2, weight=3
          Student: Python level=2, SQL level=2
          Coverage Python = min(2/3, 1) = 0.666667
          Coverage SQL = min(2/2, 1) = 1.0
          Weighted sum = 5 * (2/3) + 3 * 1.0 = 3.333333 + 3.0 = 6.333333
          Total weight = 8
          Match score = round(100 * 6.333333 / 8) = round(79.166667) = 79.
        """
        student_skills = {101: 2, 102: 2}
        required_skills = [
            {'skill_id': 101, 'skill_name': 'Python', 'required_level': 3, 'weight': 5},
            {'skill_id': 102, 'skill_name': 'SQL', 'required_level': 2, 'weight': 3},
        ]
        score = calculate_skill_match_score(student_skills, required_skills)
        assert score == 79

    def test_missing_skills_yield_zero_coverage(self):
        student_skills = {}
        required_skills = [
            {'skill_id': 1, 'skill_name': 'Python', 'required_level': 4, 'weight': 5},
            {'skill_id': 2, 'skill_name': 'Django', 'required_level': 3, 'weight': 4},
        ]
        assert calculate_skill_match_score(student_skills, required_skills) == 0

    def test_exceeding_required_level_is_capped_at_one(self):
        # Student has level 4 in skill requiring level 2 -> coverage is capped at 1.0
        student_skills = {1: 4, 2: 4}
        required_skills = [
            {'skill_id': 1, 'skill_name': 'Python', 'required_level': 2, 'weight': 5},
            {'skill_id': 2, 'skill_name': 'Git', 'required_level': 1, 'weight': 3},
        ]
        assert calculate_skill_match_score(student_skills, required_skills) == 100

    def test_partial_coverage_with_multiple_weights(self):
        # Skill 1: req=4, student=2 (cov=0.5, w=2 -> 1.0)
        # Skill 2: req=2, student=1 (cov=0.5, w=4 -> 2.0)
        # Total weighted = 3.0, total weight = 6 -> 50%
        student_skills = {1: 2, 2: 1}
        required_skills = [
            {'skill_id': 1, 'skill_name': 'Python', 'required_level': 4, 'weight': 2},
            {'skill_id': 2, 'skill_name': 'Docker', 'required_level': 2, 'weight': 4},
        ]
        assert calculate_skill_match_score(student_skills, required_skills) == 50

    def test_empty_requirements_returns_hundred(self):
        assert calculate_skill_match_score({1: 2}, []) == 100


class TestPureGapReportCalculation:
    def test_gap_report_priority_sorting(self):
        """
        Gap report must be sorted by (weight * gap) descending.
        """
        student_skills = {
            1: 1,  # Python: req=4, gap=3, w=5 -> priority = 15
            2: 2,  # SQL: req=3, gap=1, w=4 -> priority = 4
            3: 0,  # Docker: req=2, gap=2, w=4 -> priority = 8
            4: 3,  # Linux: req=2, gap=0, w=2 -> priority = 0
        }
        required_skills = [
            {'skill_id': 1, 'skill_name': 'Python', 'required_level': 4, 'weight': 5},
            {'skill_id': 2, 'skill_name': 'SQL', 'required_level': 3, 'weight': 4},
            {'skill_id': 3, 'skill_name': 'Docker', 'required_level': 2, 'weight': 4},
            {'skill_id': 4, 'skill_name': 'Linux', 'required_level': 2, 'weight': 2},
        ]
        report = generate_gap_report(student_skills, required_skills)
        assert len(report) == 4
        # Ordering must be: Python (15), Docker (8), SQL (4), Linux (0)
        assert report[0]['skill_name'] == 'Python'
        assert report[0]['priority'] == 15
        assert report[0]['gap'] == 3

        assert report[1]['skill_name'] == 'Docker'
        assert report[1]['priority'] == 8
        assert report[1]['gap'] == 2

        assert report[2]['skill_name'] == 'SQL'
        assert report[2]['priority'] == 4

        assert report[3]['skill_name'] == 'Linux'
        assert report[3]['priority'] == 0
        assert report[3]['gap'] == 0


class TestPureBatchSkillMapCalculation:
    def test_batch_skill_map_and_five_weakest_skills(self):
        """
        Tests average coverage per skill over a batch of students, and detects 5 weakest skills.
        """
        # 3 students
        # S1: Py=2, SQL=2, Git=1, Docker=0, K8s=0, Linux=2
        # S2: Py=3, SQL=1, Git=2, Docker=1, K8s=0, Linux=1
        # S3: Py=1, SQL=2, Git=0, Docker=0, K8s=0, Linux=2
        students_skills = [
            {1: 2, 2: 2, 3: 1, 4: 0, 5: 0, 6: 2},
            {1: 3, 2: 1, 3: 2, 4: 1, 5: 0, 6: 1},
            {1: 1, 2: 2, 3: 0, 4: 0, 5: 0, 6: 2},
        ]
        role_skills = [
            {'skill_id': 1, 'skill_name': 'Python', 'required_level': 3, 'weight': 5},
            {'skill_id': 2, 'skill_name': 'SQL', 'required_level': 2, 'weight': 4},
            {'skill_id': 3, 'skill_name': 'Git', 'required_level': 2, 'weight': 2},
            {'skill_id': 4, 'skill_name': 'Docker', 'required_level': 2, 'weight': 3},
            {'skill_id': 5, 'skill_name': 'Kubernetes', 'required_level': 2, 'weight': 4},
            {'skill_id': 6, 'skill_name': 'Linux', 'required_level': 2, 'weight': 3},
        ]

        result = calculate_batch_skill_map(students_skills, role_skills)
        assert result['total_students'] == 3
        assert len(result['skills_breakdown']) == 6

        # Weakest 5 should have Kubernetes (avg 0) first, then Docker
        weakest_names = [w['skill_name'] for w in result['weakest_skills']]
        assert len(weakest_names) == 5
        assert weakest_names[0] == 'Kubernetes'
        assert weakest_names[1] == 'Docker'


class TestPureMarketDemandRanking:
    def test_ranking_by_opp_count_descending(self):
        items = [
            {'skill_name': 'Java', 'opp_count': 5, 'avg_required_level': 2.5},
            {'skill_name': 'Python', 'opp_count': 18, 'avg_required_level': 3.0},
            {'skill_name': 'Go', 'opp_count': 3, 'avg_required_level': 2.0},
        ]
        ranked = rank_skills_by_market_demand(items)
        assert ranked[0]['skill_name'] == 'Python'
        assert ranked[0]['rank'] == 1
        assert ranked[1]['skill_name'] == 'Java'
        assert ranked[1]['rank'] == 2
        assert ranked[2]['skill_name'] == 'Go'
        assert ranked[2]['rank'] == 3


# =========================================================================
# Integration Tests: DB Queries, Views & Chart Context
# =========================================================================

@pytest.fixture
def test_setup(db):
    inst = Institution.objects.create(name="IIT Madras", city="Chennai", is_approved=True)
    comp = Company.objects.create(name="Razorpay", industry="Fintech", is_approved=True)

    faculty_user = User.objects.create_user(
        email="prof@iitm.ac.in", password="Password123", role=UserRole.FACULTY, institution=inst, is_verified=True
    )
    recruiter_user = User.objects.create_user(
        email="hr@razorpay.com", password="Password123", role=UserRole.RECRUITER, company=comp, is_verified=True
    )
    student_user = User.objects.create_user(
        email="student@iitm.ac.in", password="Password123", role=UserRole.STUDENT, institution=inst, is_verified=True
    )
    profile = StudentProfile.objects.create(
        user=student_user, institution=inst, roll_no="CS2025_01", programme="Computer Science", batch="2025", cgpa=8.8
    )

    cat = SkillCategory.objects.create(name="Backend Development")
    py = Skill.objects.create(category=cat, name="Python")
    sql = Skill.objects.create(category=cat, name="SQL")
    django = Skill.objects.create(category=cat, name="Django")

    # Student has Python=2, SQL=2
    StudentSkill.objects.create(student=profile, skill=py, level=SkillLevel.INTERMEDIATE, status=StudentSkillStatus.VERIFIED)
    StudentSkill.objects.create(student=profile, skill=sql, level=SkillLevel.INTERMEDIATE, status=StudentSkillStatus.VERIFIED)

    # Opportunity: Python r=3,w=5; SQL r=2,w=3 (Spec worked example)
    opp = Opportunity.objects.create(
        company=comp,
        title="Backend Engineer Intern",
        type=OpportunityType.INTERNSHIP,
        location="Bengaluru",
        deadline=timezone.now() + timedelta(days=20),
        status=OpportunityStatus.PUBLISHED,
        min_cgpa=7.5,
        programme="Computer Science",
        batch="2025",
    )
    OpportunitySkill.objects.create(opportunity=opp, skill=py, required_level=SkillLevel.ADVANCED, weight=5)
    OpportunitySkill.objects.create(opportunity=opp, skill=sql, required_level=SkillLevel.INTERMEDIATE, weight=3)

    # Role Profile: Backend Developer
    rp = RoleProfile.objects.create(name="Junior Backend Developer", description="Standard junior backend role")
    RoleSkill.objects.create(role=rp, skill=py, required_level=SkillLevel.ADVANCED, weight=5)
    RoleSkill.objects.create(role=rp, skill=sql, required_level=SkillLevel.INTERMEDIATE, weight=3)
    RoleSkill.objects.create(role=rp, skill=django, required_level=SkillLevel.INTERMEDIATE, weight=4)

    return {
        'inst': inst,
        'comp': comp,
        'faculty': faculty_user,
        'recruiter': recruiter_user,
        'student': student_user,
        'profile': profile,
        'opp': opp,
        'rp': rp,
        'skills': (py, sql, django),
    }


@pytest.mark.django_db
class TestMatchingViewsAndVisualizations:
    def test_opportunity_cards_display_student_match_score(self, client: Client, test_setup):
        student = test_setup['student']
        opp = test_setup['opp']

        client.force_login(student)
        res = client.get(reverse('opportunities:opportunity_list'))
        assert res.status_code == 200
        # Student score for this worked example is 79%
        assert "79% Match" in res.content.decode()
        assert f"/matching/opportunity/{opp.pk}/gap-report/" in res.content.decode()

    def test_opportunity_gap_report_page_with_radar_chart_data(self, client: Client, test_setup):
        student = test_setup['student']
        opp = test_setup['opp']

        client.force_login(student)
        url = reverse('matching:opportunity_gap_report', kwargs={'opp_pk': opp.pk})
        res = client.get(url)
        assert res.status_code == 200
        content = res.content.decode()

        assert "Overall Match Score" in content
        assert "79%" in content
        assert "gapRadarChart" in content
        assert "Required Benchmark Level" in content
        assert "Your Current Level" in content
        # Check context has radar chart JSON
        assert 'chart_labels_json' in res.context
        assert 'chart_required_json' in res.context
        assert 'chart_student_json' in res.context

    def test_role_profile_gap_report_page(self, client: Client, test_setup):
        student = test_setup['student']
        rp = test_setup['rp']

        client.force_login(student)
        url = reverse('matching:role_gap_report', kwargs={'role_pk': rp.pk})
        res = client.get(url)
        assert res.status_code == 200
        assert rp.name in res.content.decode()
        assert "gapRadarChart" in res.content.decode()
        assert len(res.context['gap_report']) == 3

    def test_batch_skill_map_view_accessible_by_faculty_and_officer(self, client: Client, test_setup):
        faculty = test_setup['faculty']
        student = test_setup['student']
        rp = test_setup['rp']

        # Faculty can access
        client.force_login(faculty)
        url = reverse('matching:batch_skill_map')
        res = client.get(url, {'role_id': str(rp.pk)})
        assert res.status_code == 200
        content = res.content.decode()
        assert "Batch Skill Map & Readiness Analysis" in content
        assert "Top 5 Weakest Skills" in content
        assert "batchSkillChart" in content

        # Student cannot access (403 RoleRequiredMixin)
        client.force_login(student)
        res_stu = client.get(url)
        assert res_stu.status_code == 403

    def test_market_demand_service_and_view(self, client: Client, test_setup):
        student = test_setup['student']

        # Query service directly
        demand = get_market_demand_data()
        assert len(demand) >= 2
        assert any(d['skill_name'] == 'Python' for d in demand)

        # Test view with date range filter
        client.force_login(student)
        url = reverse('matching:market_demand')
        res = client.get(url, {'range': '90'})
        assert res.status_code == 200
        content = res.content.decode()
        assert "Industry Skill Demand Trends" in content
        assert "marketDemandChart" in content
        assert "Python" in content
