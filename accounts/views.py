from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import FormView, TemplateView

from opportunities.models import Opportunity, OpportunityStatus
from orgs.models import Company, Institution
from profiles.models import StudentProfile, StudentSkill, StudentSkillStatus
from skills.models import RoleProfile, Skill, SkillCategory

from .forms import (
    LoginForm,
    PasswordResetRequestForm,
    RegistrationForm,
    ResendVerificationForm,
    SetNewPasswordForm,
)
from .models import User, UserRole
from .permissions import RoleRequiredMixin
from .services import (
    authenticate_user_with_lockout,
    send_password_reset_email,
    send_verification_email,
)
from .tokens import verify_email_verification_token, verify_password_reset_token


class RegisterView(FormView):
    template_name = 'accounts/register.html'
    form_class = RegistrationForm

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('accounts:dashboard_redirect')
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.is_verified = False
        user.save()

        send_verification_email(user, request=self.request)
        messages.success(
            self.request,
            'Registration successful! A verification email has been sent to your address. '
            'Please verify your email within 24 hours to activate all features.',
        )
        return redirect('accounts:login')


class VerifyEmailView(View):
    def get(self, request, token):
        user = verify_email_verification_token(token, max_age=86400)
        if user:
            user.is_verified = True
            user.save(update_fields=['is_verified'])
            messages.success(
                request,
                'Your email address has been successfully verified! You may now sign in.',
            )
            return redirect('accounts:login')
        else:
            messages.error(
                request,
                'The verification link is invalid or has expired (24-hour limit). '
                'Please request a new verification link below.',
            )
            return redirect('accounts:resend_verification')


class ResendVerificationView(FormView):
    template_name = 'accounts/resend_verification.html'
    form_class = ResendVerificationForm

    def form_valid(self, form):
        email = form.cleaned_data['email'].strip().lower()
        user = User.objects.filter(email=email).first()
        if user:
            if user.is_verified:
                messages.info(self.request, 'This email address is already verified. Please log in.')
                return redirect('accounts:login')
            send_verification_email(user, request=self.request)

        # Inform the user regardless to avoid user enumeration
        messages.success(
            self.request,
            'If an account exists with that email, a fresh verification link has been sent.',
        )
        return redirect('accounts:login')


class LoginView(View):
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('accounts:dashboard_redirect')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            user, status, message = authenticate_user_with_lockout(request, email, password)

            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.first_name or user.email}!')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('accounts:dashboard_redirect')
            else:
                messages.error(request, message)

        return render(request, self.template_name, {'form': form})


class LogoutView(View):
    def get(self, request):
        return self.post(request)

    def post(self, request):
        logout(request)
        messages.info(request, 'You have been logged out.')
        return redirect('accounts:login')


class PasswordResetRequestView(FormView):
    template_name = 'accounts/password_reset.html'
    form_class = PasswordResetRequestForm

    def form_valid(self, form):
        email = form.cleaned_data['email'].strip().lower()
        user = User.objects.filter(email=email).first()
        if user:
            send_password_reset_email(user, request=self.request)
        messages.success(
            self.request,
            'If an account exists with that email address, password reset instructions have been sent.',
        )
        return redirect('accounts:login')


class PasswordResetConfirmView(View):
    template_name = 'accounts/password_reset_confirm.html'

    def get(self, request, token):
        user = verify_password_reset_token(token, max_age=3600)
        if not user:
            messages.error(
                request,
                'Password reset link is invalid or has expired (1-hour limit). Please request a new one.',
            )
            return redirect('accounts:password_reset')
        form = SetNewPasswordForm()
        return render(request, self.template_name, {'form': form, 'token': token})

    def post(self, request, token):
        user = verify_password_reset_token(token, max_age=3600)
        if not user:
            messages.error(
                request,
                'Password reset link is invalid or has expired (1-hour limit). Please request a new one.',
            )
            return redirect('accounts:password_reset')

        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['new_password1'])
            user.reset_failed_logins()
            user.save()
            messages.success(request, 'Your password has been reset successfully! You can now log in.')
            return redirect('accounts:login')

        return render(request, self.template_name, {'form': form, 'token': token})


class DashboardRedirectView(LoginRequiredMixin, View):
    """Redirects the authenticated user to their role-specific dashboard."""

    def get(self, request):
        role_map = {
            UserRole.STUDENT: 'accounts:student_dashboard',
            UserRole.FACULTY: 'accounts:faculty_dashboard',
            UserRole.RECRUITER: 'accounts:recruiter_dashboard',
            UserRole.OFFICER: 'accounts:officer_dashboard',
            UserRole.ADMIN: 'accounts:admin_dashboard',
        }
        dest = role_map.get(request.user.role, 'accounts:student_dashboard')
        return redirect(dest)


class BaseDashboardView(RoleRequiredMixin, TemplateView):
    template_name = 'accounts/dashboard.html'
    role_title = 'Dashboard'
    role_description = 'Overview and actions.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['role_title'] = self.role_title
        ctx['role_description'] = self.role_description
        ctx['role_name'] = user.get_role_display()

        # In-App Notifications
        if user.is_authenticated:
            ctx['recent_notifications'] = user.notifications.all()[:5]
            ctx['unread_notifications_count'] = user.notifications.filter(is_read=False).count()
        else:
            ctx['recent_notifications'] = []
            ctx['unread_notifications_count'] = 0

        # Platform-wide live metrics
        ctx['skills_count'] = Skill.objects.filter(is_active=True).count()
        ctx['categories_count'] = SkillCategory.objects.count()
        ctx['role_profiles_count'] = RoleProfile.objects.count()
        ctx['published_opportunities_count'] = Opportunity.objects.filter(
            status=OpportunityStatus.PUBLISHED,
            deadline__gt=timezone.now(),
        ).count()
        return ctx


class StudentDashboardView(BaseDashboardView):
    allowed_roles = [UserRole.STUDENT]
    role_title = 'Student Dashboard'
    role_description = 'Build your skill profile, track applications, and view match scores.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        profile = getattr(user, 'student_profile', None)
        ctx['student_profile'] = profile
        if profile:
            ctx['completeness'] = profile.completeness_percentage
            ctx['verified_skills_count'] = profile.skills.filter(status=StudentSkillStatus.VERIFIED).count()
            ctx['unverified_skills_count'] = profile.skills.filter(status=StudentSkillStatus.UNVERIFIED).count()

            # Student application pipeline stats
            from applications.models import Application, ApplicationStatus
            apps = Application.objects.filter(student=profile).select_related('opportunity', 'opportunity__company').order_by('-applied_at')
            ctx['total_applications'] = apps.count()
            ctx['shortlisted_count'] = apps.filter(status=ApplicationStatus.SHORTLISTED).count()
            ctx['interview_count'] = apps.filter(status=ApplicationStatus.INTERVIEW).count()
            ctx['offered_count'] = apps.filter(status=ApplicationStatus.OFFERED).count()
            ctx['accepted_count'] = apps.filter(status=ApplicationStatus.ACCEPTED).count()
            ctx['recent_applications'] = apps[:5]
        else:
            ctx['completeness'] = 0
            ctx['verified_skills_count'] = 0
            ctx['unverified_skills_count'] = 0
            ctx['total_applications'] = 0
            ctx['shortlisted_count'] = 0
            ctx['interview_count'] = 0
            ctx['offered_count'] = 0
            ctx['accepted_count'] = 0
            ctx['recent_applications'] = []
        return ctx


class FacultyDashboardView(BaseDashboardView):
    allowed_roles = [UserRole.FACULTY]
    role_title = 'Faculty Mentor Dashboard'
    role_description = 'Verify student skill self-assessments and view department analytics.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if user.institution:
            ctx['students_count'] = StudentProfile.objects.filter(institution=user.institution).count()
            unverified_skills = StudentSkill.objects.filter(
                student__institution=user.institution,
                status=StudentSkillStatus.UNVERIFIED,
            )
            ctx['pending_verifications_count'] = unverified_skills.count()
            ctx['recent_pending_skills'] = unverified_skills.select_related(
                'student', 'student__user', 'skill', 'skill__category'
            ).order_by('-created_at')[:5]
        else:
            ctx['students_count'] = 0
            ctx['pending_verifications_count'] = 0
            ctx['recent_pending_skills'] = []
        return ctx


class RecruiterDashboardView(BaseDashboardView):
    allowed_roles = [UserRole.RECRUITER]
    role_title = 'Recruiter Dashboard'
    role_description = 'Post internship/job opportunities, view matched candidates, and manage applications.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.request.user.company
        ctx['company'] = company
        ctx['is_company_approved'] = company.is_approved if company else False
        if company:
            ctx['recruiter_opps_count'] = Opportunity.objects.filter(company=company).count()
            ctx['recruiter_published_count'] = Opportunity.objects.filter(company=company, status=OpportunityStatus.PUBLISHED).count()

            from applications.models import Application, ApplicationStatus
            company_apps = Application.objects.filter(opportunity__company=company)
            ctx['total_applicants'] = company_apps.count()
            ctx['shortlisted_applicants'] = company_apps.filter(status=ApplicationStatus.SHORTLISTED).count()
            ctx['interview_applicants'] = company_apps.filter(status=ApplicationStatus.INTERVIEW).count()
            ctx['offered_applicants'] = company_apps.filter(status=ApplicationStatus.OFFERED).count()
            ctx['recent_opportunities'] = Opportunity.objects.filter(company=company).prefetch_related('applications').order_by('-created_at')[:5]
        else:
            ctx['recruiter_opps_count'] = 0
            ctx['recruiter_published_count'] = 0
            ctx['total_applicants'] = 0
            ctx['shortlisted_applicants'] = 0
            ctx['interview_applicants'] = 0
            ctx['offered_applicants'] = 0
            ctx['recent_opportunities'] = []
        return ctx


class OfficerDashboardView(BaseDashboardView):
    allowed_roles = [UserRole.OFFICER]
    role_title = 'Placement Officer Dashboard'
    role_description = 'Manage placement drives, student batches, institution skills, and offer records.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        if user.institution:
            ctx['students_count'] = StudentProfile.objects.filter(institution=user.institution).count()
            ctx['batches_count'] = StudentProfile.objects.filter(institution=user.institution).values('batch').distinct().count()
            ctx['pending_verifications_count'] = StudentSkill.objects.filter(
                student__institution=user.institution,
                status=StudentSkillStatus.UNVERIFIED,
            ).count()
            ctx['open_opportunities_count'] = Opportunity.objects.filter(
                status=OpportunityStatus.PUBLISHED,
                deadline__gt=timezone.now(),
            ).count()
        else:
            ctx['students_count'] = 0
            ctx['batches_count'] = 0
            ctx['pending_verifications_count'] = 0
            ctx['open_opportunities_count'] = 0
        return ctx


class AdminDashboardView(BaseDashboardView):
    allowed_roles = [UserRole.ADMIN]
    role_title = 'Administrator Dashboard'
    role_description = 'Approve institutions and companies, manage skill taxonomies, and audit logs.'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pending_institutions_count'] = Institution.objects.filter(is_approved=False).count()
        ctx['total_institutions_count'] = Institution.objects.count()
        ctx['pending_companies_count'] = Company.objects.filter(is_approved=False).count()
        ctx['total_companies_count'] = Company.objects.count()
        ctx['total_students_count'] = StudentProfile.objects.count()
        ctx['total_users_count'] = User.objects.count()
        ctx['total_opportunities_count'] = Opportunity.objects.count()
        ctx['pending_verifications_count'] = StudentSkill.objects.filter(status=StudentSkillStatus.UNVERIFIED).count()

        from notifications.models import AuditLog
        ctx['recent_audit_logs'] = AuditLog.objects.select_related('user').order_by('-created_at')[:8]
        return ctx
