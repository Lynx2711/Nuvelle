import json
from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin
from opportunities.models import Opportunity
from profiles.models import StudentProfile
from skills.models import RoleProfile

from .services import (
    calculate_skill_match_score,
    generate_gap_report,
    get_batch_skill_map_for_role_profile,
    get_market_demand_data,
)


class OpportunityGapReportView(LoginRequiredMixin, DetailView):
    """
    Renders student skill gap report against an Opportunity with Chart.js radar.
    Students see their own gap; faculty/officers can view for their students; recruiters can view for applicants.
    """
    model = Opportunity
    template_name = 'matching/gap_report.html'
    context_object_name = 'opportunity'
    pk_url_kwarg = 'opp_pk'

    def get_object(self, queryset=None):
        return get_object_or_404(
            Opportunity.objects.select_related('company').prefetch_related(
                'required_skills__skill',
                'required_skills__skill__category',
            ),
            pk=self.kwargs['opp_pk'],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        opp = self.object

        # Determine target student
        target_student = None
        student_id = self.request.GET.get('student_id')
        if student_id and user.role in [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN, UserRole.RECRUITER]:
            target_student = get_object_or_404(StudentProfile, pk=student_id)
            if user.role in [UserRole.FACULTY, UserRole.OFFICER] and target_student.institution != user.institution:
                raise PermissionDenied("Cannot view gap report for students outside your institution.")
        elif hasattr(user, 'student_profile'):
            target_student = user.student_profile
        else:
            raise PermissionDenied("Gap report requires a student profile.")

        ctx['student'] = target_student

        # Build student skills map
        student_skills = {ss.skill_id: ss.level for ss in target_student.skills.all()}

        # Build required skills list
        required_skills = [
            {
                'skill_id': req.skill_id,
                'skill_name': req.skill.name,
                'category_name': req.skill.category.name if req.skill.category else '',
                'required_level': req.required_level,
                'weight': req.weight,
            }
            for req in opp.required_skills.all()
        ]

        match_score = calculate_skill_match_score(student_skills, required_skills)
        gap_report = generate_gap_report(student_skills, required_skills)

        ctx['match_score'] = match_score
        ctx['gap_report'] = gap_report
        ctx['target_title'] = opp.title
        ctx['target_type'] = 'Opportunity'
        ctx['target_subtitle'] = f"{opp.company.name} &bull; {opp.get_type_display()}"

        # Chart.js Radar Data
        labels = [item['skill_name'] for item in gap_report]
        required_levels = [item['required_level'] for item in gap_report]
        student_levels = [item['student_level'] for item in gap_report]

        ctx['chart_labels_json'] = json.dumps(labels)
        ctx['chart_required_json'] = json.dumps(required_levels)
        ctx['chart_student_json'] = json.dumps(student_levels)
        return ctx


class RoleProfileGapReportView(LoginRequiredMixin, DetailView):
    """
    Renders student skill gap report against a standard benchmark Role Profile (e.g. Full Stack Developer).
    """
    model = RoleProfile
    template_name = 'matching/gap_report.html'
    context_object_name = 'role_profile'
    pk_url_kwarg = 'role_pk'

    def get_object(self, queryset=None):
        return get_object_or_404(
            RoleProfile.objects.prefetch_related(
                'role_skills__skill',
                'role_skills__skill__category',
            ),
            pk=self.kwargs['role_pk'],
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        role_prof = self.object

        # Determine target student
        target_student = None
        student_id = self.request.GET.get('student_id')
        if student_id and user.role in [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN]:
            target_student = get_object_or_404(StudentProfile, pk=student_id)
            if user.role in [UserRole.FACULTY, UserRole.OFFICER] and target_student.institution != user.institution:
                raise PermissionDenied("Cannot view gap report for students outside your institution.")
        elif hasattr(user, 'student_profile'):
            target_student = user.student_profile
        else:
            raise PermissionDenied("A student profile is required to generate a gap report.")

        ctx['student'] = target_student

        student_skills = {ss.skill_id: ss.level for ss in target_student.skills.all()}
        role_skills_qs = getattr(role_prof, 'role_skills', getattr(role_prof, 'required_skills', None))
        required_skills = [
            {
                'skill_id': req.skill_id,
                'skill_name': req.skill.name,
                'category_name': req.skill.category.name if req.skill.category else '',
                'required_level': req.required_level,
                'weight': req.weight,
            }
            for req in role_skills_qs.all()
        ]

        match_score = calculate_skill_match_score(student_skills, required_skills)
        gap_report = generate_gap_report(student_skills, required_skills)

        ctx['match_score'] = match_score
        ctx['gap_report'] = gap_report
        ctx['target_title'] = role_prof.name
        ctx['target_type'] = 'Role Profile Benchmark'
        ctx['target_subtitle'] = role_prof.description

        # Chart.js Radar Data
        labels = [item['skill_name'] for item in gap_report]
        required_levels = [item['required_level'] for item in gap_report]
        student_levels = [item['student_level'] for item in gap_report]

        ctx['chart_labels_json'] = json.dumps(labels)
        ctx['chart_required_json'] = json.dumps(required_levels)
        ctx['chart_student_json'] = json.dumps(student_levels)
        return ctx


class BatchSkillMapView(RoleRequiredMixin, TemplateView):
    """
    Computes institutional/batch skill readiness map and detects 5 weakest skills
    for a chosen Role Profile. Scoped to faculty/officer's institution.
    """
    allowed_roles = [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN]
    template_name = 'matching/batch_skill_map.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        institution = user.institution if user.role != UserRole.ADMIN else None

        role_profiles = RoleProfile.objects.all().order_by('name')
        ctx['role_profiles'] = role_profiles

        # Parameters
        role_pk = self.request.GET.get('role_id')
        programme = self.request.GET.get('programme', '').strip()
        batch = self.request.GET.get('batch', '').strip()

        ctx['selected_programme'] = programme
        ctx['selected_batch'] = batch

        selected_role = None
        if role_pk:
            selected_role = RoleProfile.objects.filter(pk=role_pk).first()
        if not selected_role and role_profiles.exists():
            selected_role = role_profiles.first()

        ctx['selected_role'] = selected_role

        if selected_role:
            batch_data = get_batch_skill_map_for_role_profile(
                role_profile=selected_role,
                institution=institution,
                programme=programme or None,
                batch=batch or None,
            )
            ctx['batch_data'] = batch_data

            # Chart.js Bar Data: Skill Coverage
            labels = [s['skill_name'] for s in batch_data['skills_breakdown']]
            coverage_pcts = [s['avg_coverage_pct'] for s in batch_data['skills_breakdown']]
            meeting_pcts = [s['students_meeting_pct'] for s in batch_data['skills_breakdown']]

            ctx['chart_labels_json'] = json.dumps(labels)
            ctx['chart_coverage_json'] = json.dumps(coverage_pcts)
            ctx['chart_meeting_json'] = json.dumps(meeting_pcts)

        return ctx


class MarketDemandView(LoginRequiredMixin, TemplateView):
    """
    Renders skills ranked by number of published opportunities requiring them for a date range.
    """
    template_name = 'matching/market_demand.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        range_param = self.request.GET.get('range', '90')
        now = timezone.now()

        start_date = None
        if range_param == '30':
            start_date = now - timedelta(days=30)
            range_label = 'Last 30 Days'
        elif range_param == '90':
            start_date = now - timedelta(days=90)
            range_label = 'Last 90 Days'
        elif range_param == '180':
            start_date = now - timedelta(days=180)
            range_label = 'Last 6 Months'
        elif range_param == '365':
            start_date = now - timedelta(days=365)
            range_label = 'Last 1 Year'
        else:
            range_label = 'All Time'

        skills_demand = get_market_demand_data(start_date=start_date, limit=20)
        ctx['skills_demand'] = skills_demand
        ctx['selected_range'] = range_param
        ctx['range_label'] = range_label

        # Chart.js Horizontal Bar Data
        labels = [item['skill_name'] for item in skills_demand[:12]]
        counts = [item['opp_count'] for item in skills_demand[:12]]
        avg_levels = [item['avg_required_level'] for item in skills_demand[:12]]

        ctx['chart_labels_json'] = json.dumps(labels)
        ctx['chart_counts_json'] = json.dumps(counts)
        ctx['chart_levels_json'] = json.dumps(avg_levels)
        return ctx
