import csv

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin
from opportunities.models import Opportunity
from profiles.models import StudentProfile, StudentSkillStatus
from skills.models import Skill

from .models import Application, ApplicationStatus
from .services import submit_application, transition_application_status

# -------------------------------------------------------------------------
# Student Application Views
# -------------------------------------------------------------------------

class ApplyOpportunityView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request, opp_pk):
        opportunity = get_object_or_404(Opportunity, pk=opp_pk)
        profile = getattr(request.user, 'student_profile', None)

        if not profile:
            messages.error(request, "Please set up your student profile before applying.")
            return redirect('profiles:profile_edit')

        try:
            app = submit_application(profile, opportunity, request.user)
            messages.success(
                request,
                f"Application submitted successfully for '{opportunity.title}'! Your match score: {app.match_score_at_apply}%.",
            )
            return redirect('applications:student_applications')
        except ValidationError as exc:
            messages.error(request, f"Application rejected: {exc.message}")
            return redirect('opportunities:opportunity_detail', pk=opp_pk)


class StudentApplicationListView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.STUDENT]
    model = Application
    template_name = 'applications/student_applications.html'
    context_object_name = 'applications'

    def get_queryset(self):
        profile = getattr(self.request.user, 'student_profile', None)
        if not profile:
            return Application.objects.none()
        return Application.objects.filter(student=profile).select_related(
            'opportunity',
            'opportunity__company',
        ).order_by('-applied_at')


class WithdrawApplicationView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request, pk):
        profile = get_object_or_404(StudentProfile, user=request.user)
        application = get_object_or_404(Application, pk=pk, student=profile)

        try:
            transition_application_status(application, ApplicationStatus.WITHDRAWN, request.user)
            messages.info(request, f"Application for '{application.opportunity.title}' has been withdrawn.")
        except ValidationError as exc:
            messages.error(request, exc.message)

        return redirect('applications:student_applications')


# -------------------------------------------------------------------------
# Recruiter Applicant Tracking & Management
# -------------------------------------------------------------------------

class RecruiterApplicantListView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.RECRUITER, UserRole.ADMIN]
    template_name = 'applications/applicant_list.html'
    context_object_name = 'applications'
    paginate_by = 30

    def get_opportunity(self):
        opp = get_object_or_404(Opportunity.objects.select_related('company'), pk=self.kwargs['opp_pk'])
        user = self.request.user
        if user.role == UserRole.RECRUITER and opp.company != user.company and not user.is_superuser:
            raise PermissionDenied("You can only access applicants for your own company's opportunities.")
        return opp

    def get_queryset(self):
        opp = self.get_opportunity()
        qs = Application.objects.filter(opportunity=opp).select_related(
            'student',
            'student__user',
            'student__institution',
        ).prefetch_related('student__skills__skill')

        # Filter by Status
        status = self.request.GET.get('status', '').strip()
        if status in ApplicationStatus.values:
            qs = qs.filter(status=status)

        # Filter by Minimum CGPA
        min_cgpa = self.request.GET.get('min_cgpa', '').strip()
        if min_cgpa:
            try:
                qs = qs.filter(student__cgpa__gte=float(min_cgpa))
            except ValueError:
                pass

        # Filter by Skill + Minimum Level + Verified Only
        skill_id = (self.request.GET.get('skill') or self.request.GET.get('skill_id') or '').strip()
        min_level = (self.request.GET.get('level') or self.request.GET.get('min_level') or '').strip()
        verified_only = self.request.GET.get('verified_only') in ['on', '1', 'true', 'True']

        if skill_id:
            skill_filter = Q(student__skills__skill_id=skill_id)
            if min_level and min_level.isdigit():
                skill_filter &= Q(student__skills__level__gte=int(min_level))
            if verified_only:
                skill_filter &= Q(student__skills__status=StudentSkillStatus.VERIFIED)
            qs = qs.filter(skill_filter).distinct()

        # Keyword search
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(student__roll_no__icontains=q) |
                Q(student__user__first_name__icontains=q) |
                Q(student__user__last_name__icontains=q) |
                Q(student__user__email__icontains=q)
            )

        # Sorting
        sort = self.request.GET.get('sort', '-match_score_at_apply')
        if sort in ['-match_score_at_apply', '-student__cgpa', '-applied_at', 'applied_at']:
            qs = qs.order_by(sort)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        opp = self.get_opportunity()
        ctx['opportunity'] = opp
        ctx['skills'] = Skill.objects.filter(is_active=True).order_by('name')
        ctx['statuses'] = ApplicationStatus.choices
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_skill'] = self.request.GET.get('skill', '')
        ctx['selected_level'] = self.request.GET.get('level', '')
        ctx['verified_only'] = self.request.GET.get('verified_only') == 'on'
        ctx['selected_min_cgpa'] = self.request.GET.get('min_cgpa', '')
        ctx['query'] = self.request.GET.get('q', '')
        ctx['sort'] = self.request.GET.get('sort', '-match_score_at_apply')

        # Total counts
        all_apps = Application.objects.filter(opportunity=opp)
        ctx['total_applicants'] = all_apps.count()
        ctx['shortlisted_count'] = all_apps.filter(status=ApplicationStatus.SHORTLISTED).count()
        ctx['interview_count'] = all_apps.filter(status=ApplicationStatus.INTERVIEW).count()
        ctx['offered_count'] = all_apps.filter(status=ApplicationStatus.OFFERED).count()
        return ctx


class BulkStatusChangeView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER, UserRole.ADMIN]

    def post(self, request, opp_pk):
        opp = get_object_or_404(Opportunity, pk=opp_pk)
        if request.user.role == UserRole.RECRUITER and opp.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only manage applicants for your own company.")

        selected_ids = request.POST.getlist('selected_applications')
        new_status = (
            request.POST.get('bulk_new_status')
            or request.POST.get('action_status')
            or request.POST.get('status')
        )

        if not selected_ids:
            messages.warning(request, "No applicants selected.")
            return redirect('applications:applicant_list', opp_pk=opp_pk)

        if not new_status or new_status not in ApplicationStatus.values:
            messages.error(request, "Invalid status chosen for bulk transition.")
            return redirect('applications:applicant_list', opp_pk=opp_pk)

        success_count = 0
        failure_messages = []

        apps = Application.objects.filter(id__in=selected_ids, opportunity=opp)
        for app in apps:
            try:
                transition_application_status(app, new_status, request.user)
                success_count += 1
            except ValidationError as exc:
                msg = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
                failure_messages.append(f"{app.student.roll_no}: {msg}")

        if success_count > 0:
            messages.success(request, f"Updated {success_count} applicant(s) to '{ApplicationStatus(new_status).label}'.")
        if failure_messages:
            messages.warning(request, f"Skipped {len(failure_messages)} applicant(s) due to invalid transitions: {'; '.join(failure_messages[:3])}")

        return redirect('applications:applicant_list', opp_pk=opp_pk)


class SingleStatusChangeView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER, UserRole.ADMIN]

    def post(self, request, pk):
        app = get_object_or_404(Application.objects.select_related('opportunity'), pk=pk)
        opp = app.opportunity
        if request.user.role == UserRole.RECRUITER and opp.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only manage applicants for your own company.")

        new_status = request.POST.get('new_status')
        try:
            transition_application_status(app, new_status, request.user)
            messages.success(request, f"Updated {app.student.roll_no} status to '{app.get_status_display()}'.")
        except ValidationError as exc:
            messages.error(request, exc.message)

        return redirect('applications:applicant_list', opp_pk=opp.pk)


class ExportApplicantsCSVView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER, UserRole.ADMIN]

    def get(self, request, opp_pk):
        opp = get_object_or_404(Opportunity.objects.select_related('company'), pk=opp_pk)
        if request.user.role == UserRole.RECRUITER and opp.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only export applicants for your own company.")

        response = HttpResponse(content_type='text/csv')
        filename = f"applicants_{opp.pk}_{opp.title[:15].replace(' ', '_')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Roll No',
            'Student Name',
            'Email',
            'Institution',
            'Programme',
            'Batch',
            'CGPA',
            'Match Score (%)',
            'Applied At',
            'Current Status',
        ])

        apps = Application.objects.filter(opportunity=opp).select_related(
            'student',
            'student__user',
            'student__institution',
        ).order_by('-match_score_at_apply')

        for a in apps:
            writer.writerow([
                a.student.roll_no,
                a.student.user.get_full_name() or a.student.user.email,
                a.student.user.email,
                a.student.institution.name,
                a.student.programme,
                a.student.batch,
                a.student.cgpa or 'N/A',
                a.match_score_at_apply,
                a.applied_at.strftime('%Y-%m-%d %H:%M'),
                a.get_status_display(),
            ])

        return response
