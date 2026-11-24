import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin
from applications.models import Application

from .forms import DriveRoundForm, OfferForm, PlacementDriveForm
from .models import Offer, PlacementDrive
from .services import (
    create_or_update_offer,
    get_eligible_students_for_drive,
    respond_to_offer,
)


class PlacementDriveListView(LoginRequiredMixin, ListView):
    model = PlacementDrive
    template_name = 'drives/drive_list.html'
    context_object_name = 'drives'
    paginate_by = 15

    def get_queryset(self):
        user = self.request.user
        qs = PlacementDrive.objects.select_related(
            'opportunity',
            'opportunity__company',
            'institution',
        ).prefetch_related('rounds')

        if user.role == UserRole.OFFICER or user.role == UserRole.FACULTY:
            if not user.institution:
                return PlacementDrive.objects.none()
            qs = qs.filter(institution=user.institution)
        elif user.role == UserRole.RECRUITER:
            if not user.company:
                return PlacementDrive.objects.none()
            qs = qs.filter(opportunity__company=user.company)
        elif user.role == UserRole.STUDENT:
            if hasattr(user, 'student_profile'):
                qs = qs.filter(institution=user.student_profile.institution)
            else:
                return PlacementDrive.objects.none()

        return qs.order_by('-drive_date')


class PlacementDriveCreateView(RoleRequiredMixin, CreateView):
    allowed_roles = [UserRole.OFFICER, UserRole.RECRUITER, UserRole.ADMIN]
    model = PlacementDrive
    form_class = PlacementDriveForm
    template_name = 'drives/drive_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = self.request.user
        # If officer, enforce their institution
        if user.role == UserRole.OFFICER:
            form.instance.institution = user.institution
        # If recruiter, enforce their company opportunity
        if user.role == UserRole.RECRUITER:
            if form.instance.opportunity.company != user.company:
                raise PermissionDenied("You can only schedule drives for your own company's postings.")

        drive = form.save()
        messages.success(self.request, f"Placement drive scheduled for '{drive.opportunity.title}' on {drive.drive_date}.")
        return redirect('drives:drive_detail', pk=drive.pk)


class PlacementDriveDetailView(LoginRequiredMixin, DetailView):
    model = PlacementDrive
    template_name = 'drives/drive_detail.html'
    context_object_name = 'drive'

    def get_object(self, queryset=None):
        drive = get_object_or_404(
            PlacementDrive.objects.select_related(
                'opportunity',
                'opportunity__company',
                'institution',
            ).prefetch_related('rounds'),
            pk=self.kwargs['pk'],
        )
        user = self.request.user
        # Verify access
        if user.role in [UserRole.OFFICER, UserRole.FACULTY]:
            if drive.institution != user.institution and not user.is_superuser:
                raise PermissionDenied("You cannot view drives for another institution.")
        elif user.role == UserRole.RECRUITER:
            if drive.opportunity.company != user.company and not user.is_superuser:
                raise PermissionDenied("You cannot view drives for another company.")
        elif user.role == UserRole.STUDENT:
            if hasattr(user, 'student_profile') and drive.institution != user.student_profile.institution:
                raise PermissionDenied("This drive is hosted at a different institution.")
        return drive

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        drive = self.object
        ctx['round_form'] = DriveRoundForm()
        ctx['can_manage'] = bool(
            self.request.user.role in [UserRole.OFFICER, UserRole.ADMIN] or
            (self.request.user.role == UserRole.RECRUITER and drive.opportunity.company == self.request.user.company)
        )
        return ctx


class DriveRoundCreateView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.OFFICER, UserRole.RECRUITER, UserRole.ADMIN]

    def post(self, request, drive_pk):
        drive = get_object_or_404(PlacementDrive, pk=drive_pk)
        form = DriveRoundForm(request.POST)
        if form.is_valid():
            round_obj = form.save(commit=False)
            round_obj.drive = drive
            round_obj.save()
            messages.success(request, f"Added round '{round_obj.name}' to placement drive.")
        else:
            messages.error(request, "Error adding round. Please check the input fields.")
        return redirect('drives:drive_detail', pk=drive_pk)


class EligibleStudentsView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.OFFICER, UserRole.FACULTY, UserRole.RECRUITER, UserRole.ADMIN]
    template_name = 'drives/eligible_students.html'

    def get(self, request, drive_pk):
        drive = get_object_or_404(
            PlacementDrive.objects.select_related('opportunity', 'institution', 'opportunity__company'),
            pk=drive_pk,
        )
        user = request.user
        if user.role in [UserRole.OFFICER, UserRole.FACULTY] and drive.institution != user.institution and not user.is_superuser:
            raise PermissionDenied("Cannot access students from another institution.")
        if user.role == UserRole.RECRUITER and drive.opportunity.company != user.company and not user.is_superuser:
            raise PermissionDenied("Cannot access drives of other companies.")

        eligible_students = get_eligible_students_for_drive(drive)

        # CSV export check
        if request.GET.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="eligible_students_drive_{drive.pk}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Roll No', 'Name', 'Email', 'Programme', 'Batch', 'CGPA', 'Match Score (%)', 'Applied', 'Current Status', 'Placed'])
            for row in eligible_students:
                sp = row['student_profile']
                writer.writerow([
                    sp.roll_no,
                    sp.user.get_full_name() or sp.user.email,
                    sp.user.email,
                    sp.programme,
                    sp.batch,
                    sp.cgpa or 'N/A',
                    row['match_score'],
                    'Yes' if row['has_applied'] else 'No',
                    row['status'],
                    'Yes' if row['is_placed'] else 'No',
                ])
            return response

        ctx = {
            'drive': drive,
            'eligible_students': eligible_students,
            'total_eligible': len(eligible_students),
        }
        return render(request, self.template_name, ctx)


class CreateOfferForApplicationView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.RECRUITER, UserRole.ADMIN]
    template_name = 'drives/offer_form.html'

    def get(self, request, app_pk):
        app = get_object_or_404(
            Application.objects.select_related('student', 'student__user', 'opportunity', 'opportunity__company'),
            pk=app_pk,
        )
        if request.user.role == UserRole.RECRUITER and app.opportunity.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("Cannot extend offer for another company.")

        existing_offer = getattr(app, 'offer', None)
        form = OfferForm(instance=existing_offer)
        return render(request, self.template_name, {'form': form, 'application': app, 'offer': existing_offer})

    def post(self, request, app_pk):
        app = get_object_or_404(
            Application.objects.select_related('student', 'student__user', 'opportunity', 'opportunity__company'),
            pk=app_pk,
        )
        if request.user.role == UserRole.RECRUITER and app.opportunity.company != request.user.company and not request.user.is_superuser:
            raise PermissionDenied("Cannot extend offer for another company.")

        existing_offer = getattr(app, 'offer', None)
        form = OfferForm(request.POST, instance=existing_offer)
        if form.is_valid():
            offer = create_or_update_offer(
                application=app,
                package=form.cleaned_data['package'],
                offered_on=form.cleaned_data['offered_on'],
                notes=form.cleaned_data['notes'],
                created_by=request.user,
            )
            messages.success(request, f"Offer of ₹{offer.package:,.2f} extended to {app.student.roll_no}!")
            return redirect('applications:applicant_list', opp_pk=app.opportunity.pk)
        return render(request, self.template_name, {'form': form, 'application': app, 'offer': existing_offer})


class StudentOfferListView(RoleRequiredMixin, ListView):
    allowed_roles = [UserRole.STUDENT]
    template_name = 'drives/student_offers.html'
    context_object_name = 'offers'

    def get_queryset(self):
        user = self.request.user
        if not hasattr(user, 'student_profile'):
            return Offer.objects.none()
        return Offer.objects.filter(
            application__student=user.student_profile,
        ).select_related(
            'application',
            'application__opportunity',
            'application__opportunity__company',
        ).order_by('-created_at')


class OfferRespondView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.STUDENT, UserRole.ADMIN]

    def post(self, request, pk, action):
        offer = get_object_or_404(
            Offer.objects.select_related('application', 'application__student', 'application__student__user', 'application__opportunity', 'application__opportunity__company'),
            pk=pk,
        )
        try:
            respond_to_offer(offer, action, request.user)
            if action == 'accept':
                messages.success(request, f"Congratulations! You accepted the offer from {offer.application.opportunity.company.name}!")
            else:
                messages.info(request, f"You declined the offer from {offer.application.opportunity.company.name}.")
        except ValidationError as exc:
            messages.error(request, str(exc))

        return redirect('drives:student_offers')


class OfferDetailView(LoginRequiredMixin, DetailView):
    model = Offer
    template_name = 'drives/offer_detail.html'
    context_object_name = 'offer'
