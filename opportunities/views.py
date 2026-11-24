from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin

from .forms import OpportunityForm, OpportunitySkillForm
from .models import (
    Opportunity,
    OpportunityMode,
    OpportunitySkill,
    OpportunityStatus,
    OpportunityType,
)

# -------------------------------------------------------------------------
# Student & Public Opportunity Search & Browsing
# -------------------------------------------------------------------------

class OpportunityBrowseView(LoginRequiredMixin, ListView):
    model = Opportunity
    template_name = 'opportunities/opportunity_list.html'
    context_object_name = 'opportunities'
    paginate_by = 12

    def get_queryset(self):
        # Auto-close expired published opportunities at read-time
        now = timezone.now()
        Opportunity.objects.filter(
            status=OpportunityStatus.PUBLISHED,
            deadline__lt=now,
        ).update(status=OpportunityStatus.CLOSED)

        qs = Opportunity.objects.filter(
            status=OpportunityStatus.PUBLISHED,
        ).select_related('company').prefetch_related(
            'required_skills__skill',
            'required_skills__skill__category',
        ).order_by('-created_at')

        # Keyword Search
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(company__name__icontains=q) |
                Q(location__icontains=q) |
                Q(required_skills__skill__name__icontains=q)
            ).distinct()

        # Filters
        opp_type = self.request.GET.get('type', '').strip()
        if opp_type:
            qs = qs.filter(type=opp_type)

        mode = self.request.GET.get('mode', '').strip()
        if mode:
            qs = qs.filter(mode=mode)

        programme = self.request.GET.get('programme', '').strip()
        if programme:
            qs = qs.filter(Q(programme__icontains=programme) | Q(programme=''))

        batch = self.request.GET.get('batch', '').strip()
        if batch:
            qs = qs.filter(Q(batch__icontains=batch) | Q(batch=''))

        min_pay = self.request.GET.get('min_pay', '').strip()
        if min_pay and min_pay.isdigit():
            qs = qs.filter(pay_max__gte=int(min_pay))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_mode'] = self.request.GET.get('mode', '')
        ctx['selected_programme'] = self.request.GET.get('programme', '')
        ctx['selected_batch'] = self.request.GET.get('batch', '')
        ctx['selected_min_pay'] = self.request.GET.get('min_pay', '')

        ctx['types'] = OpportunityType.choices
        ctx['modes'] = OpportunityMode.choices

        # Student user info for eligibility hints & match score calculation
        user = self.request.user
        student_profile = getattr(user, 'student_profile', None)
        ctx['student_profile'] = student_profile

        if student_profile and ctx.get('opportunities'):
            from matching.services import calculate_skill_match_score

            student_skills = {ss.skill_id: ss.level for ss in student_profile.skills.all()}
            for opp in ctx['opportunities']:
                req_list = [
                    {
                        'skill_id': req.skill_id,
                        'required_level': req.required_level,
                        'weight': req.weight,
                    }
                    for req in opp.required_skills.all()
                ]
                opp.student_match_score = calculate_skill_match_score(student_skills, req_list)

        return ctx

    def render_to_response(self, context, **response_kwargs):
        # HTMX partial rendering
        if self.request.headers.get('HX-Request'):
            return render(self.request, 'opportunities/partials/opportunity_cards.html', context)
        return super().render_to_response(context, **response_kwargs)


class OpportunityPublicDetailView(LoginRequiredMixin, DetailView):
    model = Opportunity
    template_name = 'opportunities/opportunity_detail.html'
    context_object_name = 'opportunity'

    def get_object(self, queryset=None):
        opp = get_object_or_404(
            Opportunity.objects.select_related('company').prefetch_related(
                'required_skills__skill',
                'required_skills__skill__category',
            ),
            pk=self.kwargs['pk'],
        )
        # Read-time auto-close check
        opp.check_and_auto_close()

        # Non-recruiters / other companies can only see published opportunities
        user = self.request.user
        if opp.status != OpportunityStatus.PUBLISHED:
            if not (user.role == UserRole.RECRUITER and user.company == opp.company) and not user.is_superuser:
                raise PermissionDenied("This opportunity is not currently published.")

        return opp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        opp = self.object
        ctx['required_skills'] = opp.required_skills.select_related('skill', 'skill__category').order_by('-weight', 'skill__name')
        ctx['is_recruiter_owner'] = bool(user.role == UserRole.RECRUITER and user.company == opp.company)

        # Student eligibility and application status
        student_profile = getattr(user, 'student_profile', None)
        ctx['student_profile'] = student_profile
        if student_profile:
            from applications.models import Application
            from matching.services import calculate_skill_match_score

            existing_app = Application.objects.filter(student=student_profile, opportunity=opp).first()
            ctx['existing_application'] = existing_app

            student_skills = {ss.skill_id: ss.level for ss in student_profile.skills.all()}
            req_list = [
                {'skill_id': req.skill_id, 'required_level': req.required_level, 'weight': req.weight}
                for req in opp.required_skills.all()
            ]
            ctx['current_match_score'] = calculate_skill_match_score(student_skills, req_list)

            eligibility_issues = []
            if opp.status != OpportunityStatus.PUBLISHED:
                eligibility_issues.append("This opportunity is not currently published for applications.")
            if opp.is_expired:
                eligibility_issues.append("Application deadline has passed.")
            if opp.min_cgpa and (student_profile.cgpa is None or student_profile.cgpa < opp.min_cgpa):
                eligibility_issues.append(f"Requires minimum CGPA of {opp.min_cgpa} (Your CGPA: {student_profile.cgpa or 'Not set'})")
            if opp.programme and opp.programme.strip().lower() not in student_profile.programme.lower():
                eligibility_issues.append(f"Restricted to {opp.programme} (Your programme: {student_profile.programme})")
            if opp.batch and opp.batch.strip() != student_profile.batch.strip():
                eligibility_issues.append(f"Restricted to Batch {opp.batch} (Your batch: {student_profile.batch})")
            if existing_app:
                eligibility_issues.append("You have already submitted an application for this opportunity.")

            ctx['is_eligible'] = len(eligibility_issues) == 0
            ctx['eligibility_issues'] = eligibility_issues
            ctx['eligibility_failing_reason'] = eligibility_issues[0] if eligibility_issues else None
        return ctx


# -------------------------------------------------------------------------
# Recruiter Opportunity Management
# -------------------------------------------------------------------------

class RecruiterOpportunityListView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.RECRUITER, UserRole.ADMIN]
    template_name = 'opportunities/recruiter_opportunity_list.html'
    context_object_name = 'opportunities'

    def get_queryset(self):
        user = self.request.user
        if not user.company and not user.is_superuser:
            return Opportunity.objects.none()

        # Read-time auto-close
        Opportunity.objects.filter(
            status=OpportunityStatus.PUBLISHED,
            deadline__lt=timezone.now(),
        ).update(status=OpportunityStatus.CLOSED)

        qs = Opportunity.objects.select_related('company').prefetch_related('required_skills')
        if not user.is_superuser:
            qs = qs.filter(company=user.company)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        ctx['company'] = company
        ctx['is_company_approved'] = company.is_approved if company else False
        return ctx


class OpportunityCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.RECRUITER]
    model = Opportunity
    form_class = OpportunityForm
    template_name = 'opportunities/opportunity_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.company:
            messages.error(request, "You must belong to a company to post opportunities.")
            return redirect('accounts:recruiter_dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.company = self.request.user.company
        form.instance.status = OpportunityStatus.DRAFT
        messages.success(self.request, f"Opportunity '{form.instance.title}' created as Draft. Now add required skills.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('opportunities:recruiter_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Create New Opportunity'
        ctx['is_company_approved'] = self.request.user.company.is_approved
        return ctx


class OpportunityUpdateView(RoleRequiredMixin, UpdateView):
    allowed_roles = [UserRole.RECRUITER]
    model = Opportunity
    form_class = OpportunityForm
    template_name = 'opportunities/opportunity_form.html'

    def get_object(self, queryset=None):
        opp = get_object_or_404(Opportunity, pk=self.kwargs['pk'])
        if opp.company != self.request.user.company and not self.request.user.is_superuser:
            raise PermissionDenied("You can only edit opportunities for your own company.")
        return opp

    def get_success_url(self):
        messages.success(self.request, f"Opportunity '{self.object.title}' updated.")
        return reverse('opportunities:recruiter_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = f"Edit Opportunity: {self.object.title}"
        ctx['is_company_approved'] = self.request.user.company.is_approved
        return ctx


class RecruiterOpportunityDetailView(RoleRequiredMixin, DetailView):
    allowed_roles = [UserRole.RECRUITER]
    model = Opportunity
    template_name = 'opportunities/recruiter_opportunity_detail.html'
    context_object_name = 'opportunity'

    def get_object(self, queryset=None):
        opp = get_object_or_404(
            Opportunity.objects.select_related('company').prefetch_related(
                'required_skills__skill',
                'required_skills__skill__category',
            ),
            pk=self.kwargs['pk'],
        )
        if opp.company != self.request.user.company and not self.request.user.is_superuser:
            raise PermissionDenied("You can only manage opportunities for your own company.")
        opp.check_and_auto_close()
        return opp

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['required_skills'] = self.object.required_skills.select_related('skill', 'skill__category').order_by('-weight', 'skill__name')
        ctx['skill_form'] = OpportunitySkillForm(opportunity=self.object)
        ctx['is_company_approved'] = self.object.company.is_approved
        return ctx


class OpportunitySkillAddView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER]

    def post(self, request, pk):
        opp = get_object_or_404(Opportunity, pk=pk)
        if opp.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only add skills to your company's opportunities.")

        form = OpportunitySkillForm(request.POST, opportunity=opp)
        if form.is_valid():
            opp_skill = form.save(commit=False)
            opp_skill.opportunity = opp
            opp_skill.save()
            messages.success(request, f"Skill '{opp_skill.skill.name}' added to requirements.")
        else:
            messages.error(request, "Failed to add skill requirement. It may already be added.")
        return redirect('opportunities:recruiter_detail', pk=pk)


class OpportunitySkillDeleteView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER]

    def post(self, request, opp_pk, pk):
        opp_skill = get_object_or_404(OpportunitySkill, pk=pk, opportunity_id=opp_pk)
        if opp_skill.opportunity.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only remove skills from your company's opportunities.")

        skill_name = opp_skill.skill.name
        opp_skill.delete()
        messages.success(request, f"Skill '{skill_name}' removed from requirements.")
        return redirect('opportunities:recruiter_detail', pk=opp_pk)


class OpportunityPublishView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER]

    def post(self, request, pk):
        opp = get_object_or_404(Opportunity, pk=pk)
        if opp.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only publish opportunities for your own company.")

        # Core Rule 5: Recruiters can publish only if their Company.is_approved
        if not opp.company.is_approved:
            messages.error(
                request,
                f"Cannot publish opportunity. '{opp.company.name}' is pending administrator verification. "
                "Recruiters can publish opportunities only after company approval.",
            )
            return redirect('opportunities:recruiter_detail', pk=pk)

        # Ensure deadline is in future
        if opp.is_expired:
            messages.error(request, "Cannot publish opportunity with an expired deadline. Please update the deadline first.")
            return redirect('opportunities:recruiter_detail', pk=pk)

        # Ensure at least 1 required skill is attached
        if not opp.required_skills.exists():
            messages.error(request, "Cannot publish opportunity without required skills. Please add at least one required skill.")
            return redirect('opportunities:recruiter_detail', pk=pk)

        opp.status = OpportunityStatus.PUBLISHED
        opp.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"Opportunity '{opp.title}' has been published and is now visible to students!")
        return redirect('opportunities:recruiter_detail', pk=pk)


class OpportunityCloseView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER]

    def post(self, request, pk):
        opp = get_object_or_404(Opportunity, pk=pk)
        if opp.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("You can only close opportunities for your own company.")

        opp.status = OpportunityStatus.CLOSED
        opp.save(update_fields=['status', 'updated_at'])
        messages.info(request, f"Opportunity '{opp.title}' has been closed.")
        return redirect('opportunities:recruiter_detail', pk=pk)
