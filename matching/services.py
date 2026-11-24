from datetime import datetime
from typing import Any

from django.db.models import Avg, Count

# -------------------------------------------------------------------------
# Core Pure Unit-Tested Functions (No Request / DB Dependencies)
# -------------------------------------------------------------------------

def calculate_skill_match_score(
    student_skills: dict[int, int],
    required_skills: list[dict[str, Any]],
) -> int:
    """
    Pure unit-tested function computing skill-match score (0-100).

    Formula (Core Rule 1):
      for each required skill i:
        coverage_i = min(student_level_i / required_level_i, 1), using 0 if missing.
      match_score = round(100 * sum(weight_i * coverage_i) / sum(weight_i)).

    Example:
      Python r=3, w=5 (student level 2) -> coverage = 2/3, weighted = 10/3
      SQL r=2, w=3 (student level 2) -> coverage = 1.0, weighted = 3
      sum(weight * coverage) = 6.3333..., sum(weight) = 8
      round(100 * 6.3333... / 8) = 79.
    """
    if not required_skills:
        return 100

    total_weight = 0
    weighted_coverage = 0.0

    for req in required_skills:
        req_level = req['required_level']
        weight = req['weight']
        skill_id = req['skill_id']

        student_level = student_skills.get(skill_id, 0)
        coverage = min(student_level / req_level, 1.0) if req_level > 0 else 1.0

        weighted_coverage += weight * coverage
        total_weight += weight

    if total_weight == 0:
        return 100

    return round(100 * weighted_coverage / total_weight)


def generate_gap_report(
    student_skills: dict[int, int],
    required_skills: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Computes a skill-gap report sorted by (weight * gap) descending.
    Each item contains:
      skill_id, skill_name, required_level, student_level, gap, weight, priority
    """
    gap_report = []

    for req in required_skills:
        skill_id = req['skill_id']
        skill_name = req.get('skill_name', f"Skill {skill_id}")
        category_name = req.get('category_name', '')
        req_level = req['required_level']
        weight = req['weight']
        student_level = student_skills.get(skill_id, 0)

        gap = max(req_level - student_level, 0)
        priority = weight * gap

        gap_report.append({
            'skill_id': skill_id,
            'skill_name': skill_name,
            'category_name': category_name,
            'required_level': req_level,
            'student_level': student_level,
            'gap': gap,
            'weight': weight,
            'priority': priority,
            'coverage_pct': round((min(student_level / req_level, 1.0) if req_level > 0 else 1.0) * 100),
        })

    # Sort by weight*gap descending, then weight descending, then name
    gap_report.sort(key=lambda x: (x['priority'], x['weight']), reverse=True)
    return gap_report


def calculate_batch_skill_map(
    students_skills: list[dict[int, int]],
    role_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Pure unit-tested function computing:
      - Average coverage per skill for a role over a batch/department
      - Overall batch role readiness percentage
      - 5 weakest skills (lowest average coverage, sorted by coverage asc, weight desc)
    """
    if not role_skills:
        return {
            'total_students': len(students_skills),
            'overall_readiness_pct': 0,
            'skills_breakdown': [],
            'weakest_skills': [],
        }

    total_students = len(students_skills)
    skills_breakdown = []
    total_role_weight = sum(req['weight'] for req in role_skills)
    weighted_batch_readiness = 0.0

    for req in role_skills:
        skill_id = req['skill_id']
        skill_name = req.get('skill_name', f"Skill {skill_id}")
        category_name = req.get('category_name', '')
        req_level = req['required_level']
        weight = req['weight']

        if total_students > 0:
            student_coverages = [
                min(s.get(skill_id, 0) / req_level, 1.0) if req_level > 0 else 1.0
                for s in students_skills
            ]
            avg_coverage = sum(student_coverages) / total_students
            students_meeting = sum(1 for s in students_skills if s.get(skill_id, 0) >= req_level)
            students_possessing = sum(1 for s in students_skills if s.get(skill_id, 0) > 0)
        else:
            avg_coverage = 0.0
            students_meeting = 0
            students_possessing = 0

        avg_coverage_pct = round(avg_coverage * 100, 1)
        weighted_batch_readiness += weight * avg_coverage

        skills_breakdown.append({
            'skill_id': skill_id,
            'skill_name': skill_name,
            'category_name': category_name,
            'required_level': req_level,
            'weight': weight,
            'avg_coverage': avg_coverage,
            'avg_coverage_pct': avg_coverage_pct,
            'students_meeting_count': students_meeting,
            'students_meeting_pct': round((students_meeting / total_students * 100), 1) if total_students > 0 else 0,
            'students_possessing_count': students_possessing,
        })

    overall_readiness_pct = (
        round(100 * weighted_batch_readiness / total_role_weight, 1)
        if total_role_weight > 0
        else 0.0
    )

    # 5 weakest skills: lowest average coverage, tie-break on higher weight
    sorted_by_weakness = sorted(
        skills_breakdown,
        key=lambda x: (x['avg_coverage'], -x['weight'], x['skill_name']),
    )
    weakest_skills = sorted_by_weakness[:5]

    return {
        'total_students': total_students,
        'overall_readiness_pct': overall_readiness_pct,
        'skills_breakdown': skills_breakdown,
        'weakest_skills': weakest_skills,
    }


def rank_skills_by_market_demand(
    skill_counts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Pure unit-tested function ranking skills by published opportunity demand.
    """
    ranked = sorted(
        skill_counts,
        key=lambda x: (x.get('opp_count', 0), x.get('avg_required_level', 0)),
        reverse=True,
    )
    for idx, item in enumerate(ranked, start=1):
        item['rank'] = idx
    return ranked


# -------------------------------------------------------------------------
# Database Query Helpers
# -------------------------------------------------------------------------

def get_market_demand_data(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """
    Queries published opportunities within date range, groups by required skills,
    and returns ranked list with opportunity counts and average required level.
    """
    from opportunities.models import OpportunitySkill, OpportunityStatus

    qs = OpportunitySkill.objects.filter(opportunity__status=OpportunityStatus.PUBLISHED)

    if start_date:
        qs = qs.filter(opportunity__created_at__gte=start_date)
    if end_date:
        qs = qs.filter(opportunity__created_at__lte=end_date)

    aggregated = (
        qs.values(
            'skill__id',
            'skill__name',
            'skill__category__name',
        )
        .annotate(
            opp_count=Count('opportunity_id', distinct=True),
            avg_required_level=Avg('required_level'),
            avg_weight=Avg('weight'),
        )
        .order_by('-opp_count', 'skill__name')
    )

    results = []
    for item in aggregated[:limit]:
        results.append({
            'skill_id': item['skill__id'],
            'skill_name': item['skill__name'],
            'category_name': item['skill__category__name'] or 'General',
            'opp_count': item['opp_count'],
            'avg_required_level': round(item['avg_required_level'] or 0, 1),
            'avg_weight': round(item['avg_weight'] or 0, 1),
        })

    return rank_skills_by_market_demand(results)


def get_batch_skill_map_for_role_profile(
    role_profile,
    institution=None,
    programme: str | None = None,
    batch: str | None = None,
) -> dict[str, Any]:
    """
    Compiles students across a batch/programme at an institution, and computes
    batch skill map against a RoleProfile.
    """
    from profiles.models import StudentProfile

    students_qs = StudentProfile.objects.select_related('user', 'institution').prefetch_related(
        'skills__skill',
    )
    if institution:
        students_qs = students_qs.filter(institution=institution)
    if programme:
        students_qs = students_qs.filter(programme__icontains=programme.strip())
    if batch:
        students_qs = students_qs.filter(batch__iexact=batch.strip())

    students_skills_list = []
    for sp in students_qs:
        student_skills = {ss.skill_id: ss.level for ss in sp.skills.all()}
        students_skills_list.append(student_skills)

    role_skills_qs = getattr(role_profile, 'role_skills', None)
    if role_skills_qs is None:
        role_skills_qs = getattr(role_profile, 'required_skills')

    role_skills = [
        {
            'skill_id': rs.skill_id,
            'skill_name': rs.skill.name,
            'category_name': rs.skill.category.name if rs.skill.category else '',
            'required_level': rs.required_level,
            'weight': rs.weight,
        }
        for rs in role_skills_qs.select_related('skill', 'skill__category').all()
    ]

    result = calculate_batch_skill_map(students_skills_list, role_skills)
    result['role_profile'] = role_profile
    result['institution'] = institution
    result['selected_programme'] = programme
    result['selected_batch'] = batch
    return result
