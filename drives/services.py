from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from applications.models import Application, ApplicationStatus
from matching.services import calculate_skill_match_score
from notifications.services import create_audit_log, send_notification
from opportunities.models import Opportunity
from orgs.models import Institution
from profiles.models import StudentProfile

from .models import DriveRound, Offer, OfferStatus, PlacementDrive


def create_placement_drive(
    opportunity: Opportunity,
    institution: Institution,
    drive_date,
    venue: str,
    rules: str = '',
    rounds_data: list[dict[str, Any]] | None = None,
    created_by: Any = None,
) -> PlacementDrive:
    """
    Creates a placement drive for an opportunity hosted at an institution.
    """
    with transaction.atomic():
        drive = PlacementDrive.objects.create(
            opportunity=opportunity,
            institution=institution,
            drive_date=drive_date,
            venue=venue,
            rules=rules,
        )

        if rounds_data:
            for idx, r in enumerate(rounds_data, start=1):
                DriveRound.objects.create(
                    drive=drive,
                    name=r.get('name', f"Round {idx}"),
                    sequence=idx,
                    round_date=r.get('round_date'),
                    description=r.get('description', ''),
                )

        create_audit_log(created_by, 'CREATE_PLACEMENT_DRIVE', 'PlacementDrive', drive.pk)

        # Notify institution officers
        for officer in institution.users.filter(role='officer'):
            send_notification(
                user=officer,
                message=f"New placement drive scheduled for '{opportunity.title}' by {opportunity.company.name} on {drive_date}.",
                link=reverse('drives:drive_detail', kwargs={'pk': drive.pk}),
                send_email=True,
            )

    return drive


def get_eligible_students_for_drive(drive: PlacementDrive) -> list[dict[str, Any]]:
    """
    Returns list of eligible students from the drive's institution with computed match scores.
    """
    opp = drive.opportunity
    institution = drive.institution

    qs = StudentProfile.objects.filter(institution=institution).select_related(
        'user',
        'institution',
    ).prefetch_related('skills__skill')

    if opp.programme:
        qs = qs.filter(programme__icontains=opp.programme.strip())
    if opp.batch:
        qs = qs.filter(batch__iexact=opp.batch.strip())
    if opp.min_cgpa is not None:
        qs = qs.filter(cgpa__gte=opp.min_cgpa)

    required_skills = [
        {'skill_id': req.skill_id, 'required_level': req.required_level, 'weight': req.weight}
        for req in opp.required_skills.all()
    ]

    eligible_list = []
    for sp in qs:
        student_skills = {ss.skill_id: ss.level for ss in sp.skills.all()}
        score = calculate_skill_match_score(student_skills, required_skills)
        app = Application.objects.filter(student=sp, opportunity=opp).first()

        eligible_list.append({
            'student_profile': sp,
            'match_score': score,
            'application': app,
            'has_applied': app is not None,
            'status': app.get_status_display() if app else 'Not Applied',
            'is_placed': sp.is_placed,
        })

    # Sort by match score descending, then CGPA descending
    eligible_list.sort(key=lambda x: (x['match_score'], x['student_profile'].cgpa or 0), reverse=True)
    return eligible_list


def create_or_update_offer(
    application: Application,
    package: Decimal | float | int,
    offered_on=None,
    notes: str = '',
    created_by: Any = None,
) -> Offer:
    """
    Creates or updates an offer for an application (1:1 relation),
    atomically updating application status to OFFERED and sending notifications.
    """
    if offered_on is None:
        offered_on = timezone.now().date()

    with transaction.atomic():
        offer, created = Offer.objects.get_or_create(
            application=application,
            defaults={
                'package': Decimal(str(package)),
                'offered_on': offered_on,
                'notes': notes,
                'status': OfferStatus.PENDING,
            },
        )
        if not created:
            offer.package = Decimal(str(package))
            offer.offered_on = offered_on
            offer.notes = notes
            offer.save()

        # Update application status to offered if not already final
        if application.status != ApplicationStatus.OFFERED and application.status != ApplicationStatus.ACCEPTED:
            application.status = ApplicationStatus.OFFERED
            application.save(update_fields=['status'])

        create_audit_log(created_by, 'CREATE_OFFER', 'Offer', offer.pk)

        # Notify student candidate
        send_notification(
            user=application.student.user,
            message=f"Congratulations! You received an offer of ₹{package:,.2f} for '{application.opportunity.title}' from {application.opportunity.company.name}.",
            link=reverse('drives:student_offers'),
            send_email=True,
        )

    return offer


def respond_to_offer(
    offer: Offer,
    action: str,
    user: Any,
) -> Offer:
    """
    Student accepts or declines an offer:
    - On accept: sets offer status=ACCEPTED, sets student.is_placed=True, updates application=ACCEPTED.
    - On decline: sets offer status=DECLINED.
    """
    if action not in ['accept', 'decline']:
        raise ValidationError("Action must be either 'accept' or 'decline'.")

    # Only student applicant or admin can respond
    if user != offer.application.student.user and not user.is_superuser:
        raise ValidationError("Only the candidate student can accept or decline this offer.")

    if offer.status != OfferStatus.PENDING:
        raise ValidationError(f"This offer has already been {offer.get_status_display().lower()}.")

    with transaction.atomic():
        if action == 'accept':
            offer.status = OfferStatus.ACCEPTED
            offer.save(update_fields=['status', 'updated_at'])

            student_profile = offer.application.student
            student_profile.is_placed = True
            student_profile.save(update_fields=['is_placed', 'updated_at'])

            offer.application.status = ApplicationStatus.ACCEPTED
            offer.application.save(update_fields=['status'])

            create_audit_log(user, 'ACCEPT_OFFER', 'Offer', offer.pk)

            # Notify company recruiters
            for recruiter in offer.application.opportunity.company.users.filter(role='recruiter'):
                send_notification(
                    user=recruiter,
                    message=f"Candidate {student_profile.roll_no} ACCEPTED the offer for '{offer.application.opportunity.title}'.",
                    link=reverse('drives:offer_detail', kwargs={'pk': offer.pk}),
                    send_email=True,
                )

        elif action == 'decline':
            offer.status = OfferStatus.DECLINED
            offer.save(update_fields=['status', 'updated_at'])

            create_audit_log(user, 'DECLINE_OFFER', 'Offer', offer.pk)

            for recruiter in offer.application.opportunity.company.users.filter(role='recruiter'):
                send_notification(
                    user=recruiter,
                    message=f"Candidate {offer.application.student.roll_no} DECLINED the offer for '{offer.application.opportunity.title}'.",
                    link=reverse('drives:offer_detail', kwargs={'pk': offer.pk}),
                    send_email=True,
                )

    return offer
