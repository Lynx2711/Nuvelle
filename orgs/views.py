from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import CreateView, ListView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin
from notifications.services import create_audit_log, send_notification

from .forms import CompanyForm, InstitutionForm
from .models import Company, Institution


class ManageOrgsView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.ADMIN]
    template_name = 'orgs/manage_orgs.html'
    context_object_name = 'institutions'

    def get_queryset(self):
        return Institution.objects.annotate(user_count=Count('users')).order_by('name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['companies'] = Company.objects.annotate(user_count=Count('users')).order_by('name')
        ctx['pending_institutions_count'] = Institution.objects.filter(is_approved=False).count()
        ctx['pending_companies_count'] = Company.objects.filter(is_approved=False).count()
        return ctx


class ToggleInstitutionApprovalView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.ADMIN]

    def post(self, request, pk):
        institution = get_object_or_404(Institution, pk=pk)
        institution.is_approved = not institution.is_approved
        institution.save(update_fields=['is_approved', 'updated_at'])
        status_text = "approved" if institution.is_approved else "moved to pending"
        create_audit_log(request.user, f'TOGGLE_INSTITUTION_{status_text.upper()}', 'Institution', institution.pk)
        messages.success(request, f"Institution '{institution.name}' has been {status_text}.")
        return redirect('orgs:manage_orgs')


class ToggleCompanyApprovalView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.ADMIN]

    def post(self, request, pk):
        company = get_object_or_404(Company, pk=pk)
        company.is_approved = not company.is_approved
        company.save(update_fields=['is_approved', 'updated_at'])
        status_text = "approved" if company.is_approved else "moved to pending"
        create_audit_log(request.user, f'TOGGLE_COMPANY_{status_text.upper()}', 'Company', company.pk)

        if company.is_approved:
            for recruiter in company.users.filter(role=UserRole.RECRUITER):
                send_notification(
                    user=recruiter,
                    message=f"Good news! Your company '{company.name}' has been approved by admin. You can now publish opportunities.",
                    link='/opportunities/my/',
                    send_email=True,
                )

        messages.success(request, f"Company '{company.name}' has been {status_text}.")
        return redirect('orgs:manage_orgs')


class InstitutionCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.ADMIN]
    model = Institution
    form_class = InstitutionForm
    template_name = 'orgs/org_form.html'
    success_url = '/orgs/manage/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Add New Institution'
        ctx['org_type'] = 'Institution'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Institution '{form.instance.name}' created.")
        return super().form_valid(form)


class CompanyCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.ADMIN]
    model = Company
    form_class = CompanyForm
    template_name = 'orgs/org_form.html'
    success_url = '/orgs/manage/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Add New Company'
        ctx['org_type'] = 'Company'
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Company '{form.instance.name}' created.")
        return super().form_valid(form)
