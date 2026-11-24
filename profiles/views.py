import csv

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin
from notifications.services import create_audit_log, send_notification

from .forms import (
    CertificationForm,
    ProjectForm,
    StudentCSVImportForm,
    StudentProfileForm,
    StudentSkillForm,
)
from .models import Certification, Project, StudentProfile, StudentSkill, StudentSkillStatus
from .services import import_students_from_csv

# -------------------------------------------------------------------------
# Student Profile Editor & Management
# -------------------------------------------------------------------------

class StudentProfileEditView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]
    template_name = 'profiles/profile_edit.html'

    def get_or_create_profile(self, user):
        profile = getattr(user, 'student_profile', None)
        if not profile:
            # Create a default profile if student doesn't have one yet
            inst = user.institution
            if not inst:
                from orgs.models import Institution
                inst = Institution.objects.filter(is_approved=True).first()
            profile = StudentProfile.objects.create(
                user=user,
                institution=inst,
                roll_no=f"STU{user.pk:04d}",
                programme="General",
                batch=str(timezone.now().year),
            )
        return profile

    def get(self, request):
        profile = self.get_or_create_profile(request.user)
        form = StudentProfileForm(instance=profile)
        skill_form = StudentSkillForm(student=profile)
        project_form = ProjectForm()
        cert_form = CertificationForm()

        context = {
            'profile': profile,
            'form': form,
            'skill_form': skill_form,
            'project_form': project_form,
            'cert_form': cert_form,
            'skills': profile.skills.select_related('skill', 'skill__category', 'verified_by').order_by('-status', '-level'),
            'projects': profile.projects.all(),
            'certifications': profile.certifications.all(),
            'completeness': profile.completeness_percentage,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        profile = self.get_or_create_profile(request.user)
        form = StudentProfileForm(request.POST, request.FILES, instance=profile)

        if form.is_valid():
            form.save()
            messages.success(request, "Profile details updated successfully.")
            return redirect('profiles:profile_edit')

        context = {
            'profile': profile,
            'form': form,
            'skill_form': StudentSkillForm(student=profile),
            'project_form': ProjectForm(),
            'cert_form': CertificationForm(),
            'skills': profile.skills.select_related('skill', 'skill__category', 'verified_by').order_by('-status', '-level'),
            'projects': profile.projects.all(),
            'certifications': profile.certifications.all(),
            'completeness': profile.completeness_percentage,
        }
        return render(request, self.template_name, context)


class StudentSkillAddView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request):
        profile = get_object_or_404(StudentProfile, user=request.user)
        form = StudentSkillForm(request.POST, student=profile)
        if form.is_valid():
            student_skill = form.save(commit=False)
            student_skill.student = profile
            student_skill.status = StudentSkillStatus.UNVERIFIED  # self-assessed
            student_skill.save()
            messages.success(request, f"Skill '{student_skill.skill.name}' added (Status: Unverified).")
        else:
            messages.error(request, "Could not add skill. It may already be added to your profile.")
        return redirect('profiles:profile_edit')


class StudentSkillEditView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request, pk):
        student_skill = get_object_or_404(StudentSkill, pk=pk, student__user=request.user)
        new_level = request.POST.get('level')
        if new_level and int(new_level) in [1, 2, 3, 4]:
            old_level = student_skill.level
            student_skill.level = int(new_level)
            # Rule 4: If level changes, model save() automatically resets verification status
            student_skill.save()
            if old_level != student_skill.level:
                messages.info(request, f"Updated '{student_skill.skill.name}' to {student_skill.get_level_display()}. Verification reset to Unverified.")
            else:
                messages.success(request, f"Saved skill level for '{student_skill.skill.name}'.")
        return redirect('profiles:profile_edit')


class StudentSkillDeleteView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request, pk):
        student_skill = get_object_or_404(StudentSkill, pk=pk, student__user=request.user)
        skill_name = student_skill.skill.name
        student_skill.delete()
        messages.success(request, f"Skill '{skill_name}' removed from your profile.")
        return redirect('profiles:profile_edit')


class ProjectCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.STUDENT]
    model = Project
    form_class = ProjectForm

    def form_valid(self, form):
        profile = get_object_or_404(StudentProfile, user=self.request.user)
        form.instance.student = profile
        messages.success(self.request, f"Project '{form.instance.title}' added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('profiles:profile_edit')


class ProjectDeleteView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk, student__user=request.user)
        title = project.title
        project.delete()
        messages.success(request, f"Project '{title}' deleted.")
        return redirect('profiles:profile_edit')


class CertificationCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.STUDENT]
    model = Certification
    form_class = CertificationForm

    def form_valid(self, form):
        profile = get_object_or_404(StudentProfile, user=self.request.user)
        form.instance.student = profile
        messages.success(self.request, f"Certification '{form.instance.name}' added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('profiles:profile_edit')


class CertificationDeleteView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT]

    def post(self, request, pk):
        cert = get_object_or_404(Certification, pk=pk, student__user=request.user)
        name = cert.name
        cert.delete()
        messages.success(request, f"Certification '{name}' deleted.")
        return redirect('profiles:profile_edit')


# -------------------------------------------------------------------------
# Faculty & Officer Verification Queue
# -------------------------------------------------------------------------

class FacultyVerificationQueueView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN]
    template_name = 'profiles/verification_queue.html'
    context_object_name = 'queued_skills'
    paginate_by = 25

    def get_queryset(self):
        user = self.request.user
        qs = StudentSkill.objects.select_related(
            'student',
            'student__user',
            'student__institution',
            'skill',
            'skill__category',
            'verified_by',
        ).order_by('-created_at')

        # Object-level permission: Faculty/Officer can only verify students in their own institution
        if user.role in [UserRole.FACULTY, UserRole.OFFICER]:
            if not user.institution:
                return StudentSkill.objects.none()
            qs = qs.filter(student__institution=user.institution)

        # Filters
        status = self.request.GET.get('status', 'unverified').strip()
        if status in ['unverified', 'verified', 'rejected']:
            qs = qs.filter(status=status)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(student__roll_no__icontains=q) |
                Q(student__user__first_name__icontains=q) |
                Q(student__user__last_name__icontains=q) |
                Q(skill__name__icontains=q)
            )

        batch = self.request.GET.get('batch', '').strip()
        if batch:
            qs = qs.filter(student__batch=batch)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        inst_skills = StudentSkill.objects.all()
        if user.role in [UserRole.FACULTY, UserRole.OFFICER] and user.institution:
            inst_skills = inst_skills.filter(student__institution=user.institution)

        ctx['pending_count'] = inst_skills.filter(status=StudentSkillStatus.UNVERIFIED).count()
        ctx['verified_count'] = inst_skills.filter(status=StudentSkillStatus.VERIFIED).count()
        ctx['rejected_count'] = inst_skills.filter(status=StudentSkillStatus.REJECTED).count()
        ctx['selected_status'] = self.request.GET.get('status', 'unverified')
        ctx['query'] = self.request.GET.get('q', '')
        ctx['selected_batch'] = self.request.GET.get('batch', '')

        # Filter batches list
        ctx['batches'] = inst_skills.values_list('student__batch', flat=True).distinct().order_by('student__batch')
        return ctx


class ApproveSkillView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN]

    def post(self, request, pk):
        skill_entry = get_object_or_404(StudentSkill, pk=pk)

        # Object permission check
        if request.user.role in [UserRole.FACULTY, UserRole.OFFICER]:
            if skill_entry.student.institution != request.user.institution:
                raise PermissionDenied("You can only verify skills for students in your own institution.")

        skill_entry.status = StudentSkillStatus.VERIFIED
        skill_entry.verified_by = request.user
        skill_entry.verified_at = timezone.now()
        skill_entry.rejection_reason = ''
        skill_entry.save(update_fields=['status', 'verified_by', 'verified_at', 'rejection_reason', 'updated_at'])

        send_notification(
            user=skill_entry.student.user,
            message=f"Your skill '{skill_entry.skill.name}' has been verified at {skill_entry.get_level_display()} by {request.user.get_full_name() or request.user.email}.",
            link=reverse('profiles:profile_edit'),
            send_email=True,
        )
        create_audit_log(request.user, 'APPROVE_SKILL', 'StudentSkill', skill_entry.pk)

        messages.success(
            request,
            f"Approved '{skill_entry.skill.name}' ({skill_entry.get_level_display()}) for student {skill_entry.student.roll_no}.",
        )
        return redirect(request.META.get('HTTP_REFERER', 'profiles:verification_queue'))


class RejectSkillView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN]

    def post(self, request, pk):
        skill_entry = get_object_or_404(StudentSkill, pk=pk)

        if request.user.role in [UserRole.FACULTY, UserRole.OFFICER]:
            if skill_entry.student.institution != request.user.institution:
                raise PermissionDenied("You can only verify skills for students in your own institution.")

        reason = request.POST.get('rejection_reason', '').strip()
        if not reason:
            messages.error(request, "A rejection reason is mandatory when rejecting a student skill.")
            return redirect(request.META.get('HTTP_REFERER', 'profiles:verification_queue'))

        skill_entry.status = StudentSkillStatus.REJECTED
        skill_entry.verified_by = request.user
        skill_entry.verified_at = timezone.now()
        skill_entry.rejection_reason = reason
        skill_entry.save(update_fields=['status', 'verified_by', 'verified_at', 'rejection_reason', 'updated_at'])

        send_notification(
            user=skill_entry.student.user,
            message=f"Your skill claim for '{skill_entry.skill.name}' was rejected by faculty. Reason: {reason}",
            link=reverse('profiles:profile_edit'),
            send_email=True,
        )
        create_audit_log(request.user, 'REJECT_SKILL', 'StudentSkill', skill_entry.pk)

        messages.warning(
            request,
            f"Rejected '{skill_entry.skill.name}' for {skill_entry.student.roll_no}. Reason: {reason}",
        )
        return redirect(request.META.get('HTTP_REFERER', 'profiles:verification_queue'))


class AdjustSkillLevelView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.FACULTY, UserRole.OFFICER, UserRole.ADMIN]

    def post(self, request, pk):
        skill_entry = get_object_or_404(StudentSkill, pk=pk)

        if request.user.role in [UserRole.FACULTY, UserRole.OFFICER]:
            if skill_entry.student.institution != request.user.institution:
                raise PermissionDenied("You can only verify skills for students in your own institution.")

        new_level = request.POST.get('adjusted_level')
        if not new_level or int(new_level) not in [1, 2, 3, 4]:
            messages.error(request, "Invalid proficiency level specified.")
            return redirect(request.META.get('HTTP_REFERER', 'profiles:verification_queue'))

        old_level_disp = skill_entry.get_level_display()
        skill_entry.level = int(new_level)
        skill_entry.status = StudentSkillStatus.VERIFIED
        skill_entry.verified_by = request.user
        skill_entry.verified_at = timezone.now()
        skill_entry.rejection_reason = ''
        skill_entry.save(update_fields=['level', 'status', 'verified_by', 'verified_at', 'rejection_reason', 'updated_at'])

        send_notification(
            user=skill_entry.student.user,
            message=f"Your skill '{skill_entry.skill.name}' was adjusted ({old_level_disp} -> {skill_entry.get_level_display()}) and verified.",
            link=reverse('profiles:profile_edit'),
            send_email=True,
        )
        create_audit_log(request.user, 'ADJUST_SKILL', 'StudentSkill', skill_entry.pk)

        messages.success(
            request,
            f"Adjusted level for '{skill_entry.skill.name}' ({old_level_disp} &rarr; {skill_entry.get_level_display()}) and marked verified for {skill_entry.student.roll_no}.",
        )
        return redirect(request.META.get('HTTP_REFERER', 'profiles:verification_queue'))


# -------------------------------------------------------------------------
# Student Directory & CSV Import Views (Built in Phase 1)
# -------------------------------------------------------------------------

class StudentCSVImportView(RoleRequiredMixin, FormView):
    allowed_roles = [UserRole.OFFICER, UserRole.ADMIN]
    template_name = 'profiles/import_students.html'
    form_class = StudentCSVImportForm

    def get_institution(self):
        if self.request.user.role == UserRole.OFFICER:
            if not self.request.user.institution:
                raise PermissionDenied("You must be affiliated with an approved institution to import students.")
            return self.request.user.institution

        if self.request.user.institution:
            return self.request.user.institution
        from orgs.models import Institution
        first_inst = Institution.objects.filter(is_approved=True).first()
        if not first_inst:
            raise PermissionDenied("No approved institution found in the system.")
        return first_inst

    def form_valid(self, form):
        institution = self.get_institution()
        csv_file = form.cleaned_data['csv_file']

        success_count, error_records = import_students_from_csv(csv_file, institution)

        self.request.session['student_import_errors'] = error_records
        self.request.session['student_import_summary'] = {
            'success_count': success_count,
            'error_count': len(error_records),
            'institution_name': institution.name,
            'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        if success_count > 0 and len(error_records) == 0:
            messages.success(self.request, f"Successfully imported all {success_count} students into {institution.name}!")
        elif success_count > 0 and len(error_records) > 0:
            messages.warning(
                self.request,
                f"Imported {success_count} students successfully. {len(error_records)} rows had errors and were skipped.",
            )
        else:
            messages.error(
                self.request,
                f"No students imported. All {len(error_records)} rows had errors.",
            )

        return redirect('profiles:import_report')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['institution'] = self.get_institution()
        return ctx


class ImportReportView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.OFFICER, UserRole.ADMIN]
    template_name = 'profiles/import_report.html'

    def get(self, request):
        summary = request.session.get('student_import_summary')
        errors = request.session.get('student_import_errors', [])

        if not summary and not errors:
            messages.info(request, "No recent import session found.")
            return redirect('profiles:student_list')

        context = {
            'summary': summary,
            'errors': errors,
        }
        return render(request, self.template_name, context)


class DownloadImportErrorReportView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.OFFICER, UserRole.ADMIN]

    def get(self, request):
        errors = request.session.get('student_import_errors', [])
        if not errors:
            messages.info(request, "No import errors available to download.")
            return redirect('profiles:student_list')

        response = HttpResponse(content_type='text/csv')
        filename = f"student_import_errors_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(['Row', 'Roll No', 'Name', 'Email', 'Programme', 'Batch', 'CGPA', 'Reason for Failure'])

        for err in errors:
            writer.writerow([
                err.get('row', ''),
                err.get('roll_no', ''),
                err.get('name', ''),
                err.get('email', ''),
                err.get('programme', ''),
                err.get('batch', ''),
                err.get('cgpa', ''),
                err.get('reason', ''),
            ])

        return response


class StudentListView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.OFFICER, UserRole.FACULTY, UserRole.ADMIN]
    model = StudentProfile
    template_name = 'profiles/student_list.html'
    context_object_name = 'students'
    paginate_by = 30

    def get_queryset(self):
        user = self.request.user
        qs = StudentProfile.objects.select_related('user', 'institution').order_by('roll_no')

        if user.role in [UserRole.OFFICER, UserRole.FACULTY]:
            if not user.institution:
                return StudentProfile.objects.none()
            qs = qs.filter(institution=user.institution)

        q = self.request.GET.get('q', '').strip()
        batch = self.request.GET.get('batch', '').strip()
        programme = self.request.GET.get('programme', '').strip()

        if q:
            qs = qs.filter(
                Q(roll_no__icontains=q) |
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(user__email__icontains=q)
            )
        if batch:
            qs = qs.filter(batch=batch)
        if programme:
            qs = qs.filter(programme=programme)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = StudentProfile.objects.all()
        if self.request.user.role in [UserRole.OFFICER, UserRole.FACULTY] and self.request.user.institution:
            base_qs = base_qs.filter(institution=self.request.user.institution)

        ctx['batches'] = base_qs.values_list('batch', flat=True).distinct().order_by('batch')
        ctx['programmes'] = base_qs.values_list('programme', flat=True).distinct().order_by('programme')
        ctx['selected_batch'] = self.request.GET.get('batch', '')
        ctx['selected_programme'] = self.request.GET.get('programme', '')
        ctx['query'] = self.request.GET.get('q', '')
        ctx['can_import'] = self.request.user.role in [UserRole.OFFICER, UserRole.ADMIN]
        return ctx


class StudentProfileDetailView(RoleRequiredMixin, DetailView):
    model = StudentProfile
    template_name = 'profiles/student_detail.html'
    context_object_name = 'student'

    def get_object(self, queryset=None):
        student = get_object_or_404(StudentProfile.objects.select_related('user', 'institution'), pk=self.kwargs['pk'])
        user = self.request.user

        if user.role == UserRole.STUDENT and student.user != user:
            raise PermissionDenied("You can only view your own student profile.")
        if user.role in [UserRole.OFFICER, UserRole.FACULTY] and student.institution != user.institution and not user.is_superuser:
            raise PermissionDenied("You can only view profiles within your own institution.")
        if user.role == UserRole.RECRUITER and not user.is_superuser:
            from applications.models import Application
            has_applied = Application.objects.filter(student=student, opportunity__company=user.company).exists()
            if not has_applied:
                raise PermissionDenied("Recruiters can only view profiles of candidates who have applied to their company's opportunities.")

        return student

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['skills'] = self.object.skills.select_related('skill', 'skill__category', 'verified_by').order_by('-level', 'skill__name')
        ctx['projects'] = self.object.projects.all()
        ctx['certifications'] = self.object.certifications.all()
        ctx['completeness'] = self.object.completeness_percentage
        return ctx
