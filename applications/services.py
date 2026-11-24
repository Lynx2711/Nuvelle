from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from matching.services import calculate_skill_match_score
from notifications.services import create_audit_log, send_notification

from .models import Application, ApplicationStatus, StatusLog

VALID_TRANSITIONS: dict[str, list[str]] = {
    ApplicationStatus.APPLIED: [
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
    ApplicationStatus.SHORTLISTED: [
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
    ],
    ApplicationStatus.INTERVIEW: [
        ApplicationStatus.OFFERED,
        ApplicationStatus.REJECTED,
    ],
    ApplicationStatus.OFFERED: [
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    ],
    ApplicationStatus.ACCEPTED: [],
    ApplicationStatus.REJECTED: [],
    ApplicationStatus.WITHDRAWN: [],
}


def check_application_eligibility(student_profile, opportunity) -> tuple[bool, str | None]:
    """
    Validates Core Rule 2:
    - Opportunity is published
    - Deadline not passed
    - Student programme match
    - Student batch match
    - CGPA >= min_cgpa
    - No duplicate application
    Returns: (is_eligible, failing_reason)
    """
    if opportunity.status != 'published':
        return False, "This opportunity is not currently published for applications."

    if opportunity.is_expired:
        return False, f"The application deadline ({opportunity.deadline.strftime('%d %b %Y, %H:%M')}) has passed."

    if opportunity.programme:
        if not student_profile.programme or opportunity.programme.strip().lower() not in student_profile.programme.lower():
            return False, f"Restricted to candidates in '{opportunity.programme}' (Your programme: {student_profile.programme or 'None'})."

    if opportunity.batch:
        if not student_profile.batch or opportunity.batch.strip() != student_profile.batch.strip():
            return False, f"Restricted to Batch {opportunity.batch} (Your batch: {student_profile.batch or 'None'})."

    if opportunity.min_cgpa is not None:
        if student_profile.cgpa is None or student_profile.cgpa < opportunity.min_cgpa:
            return False, f"Requires a minimum CGPA of {opportunity.min_cgpa} (Your CGPA: {student_profile.cgpa or 'Not set'})."

    if Application.objects.filter(student=student_profile, opportunity=opportunity).exists():
        return False, "You have already submitted an application for this opportunity."

    return True, None


def compute_student_match_score_for_opportunity(student_profile, opportunity) -> int:
    """Calculates match score between student's claimed skills and opportunity requirements."""
    student_skills_map = {
        ss.skill_id: ss.level for ss in student_profile.skills.all()
    }
    required_skills_list = [
        {
            'skill_id': req.skill_id,
            'skill_name': req.skill.name,
            'required_level': req.required_level,
            'weight': req.weight,
        }
        for req in opportunity.required_skills.select_related('skill').all()
    ]
    return calculate_skill_match_score(student_skills_map, required_skills_list)


def submit_application(student_profile, opportunity, changed_by_user=None) -> Application:
    """
    Submits application atomically with eligibility verification, match score computation,
    status log, and notifications.
    """
    if changed_by_user is None:
        changed_by_user = student_profile.user

    is_eligible, reason = check_application_eligibility(student_profile, opportunity)
    if not is_eligible:
        raise ValidationError(reason)

    match_score = compute_student_match_score_for_opportunity(student_profile, opportunity)

    with transaction.atomic():
        app = Application.objects.create(
            student=student_profile,
            opportunity=opportunity,
            status=ApplicationStatus.APPLIED,
            match_score_at_apply=match_score,
        )

        StatusLog.objects.create(
            application=app,
            old_status='',
            new_status=ApplicationStatus.APPLIED,
            changed_by=changed_by_user,
        )

        # Notification for candidate
        send_notification(
            user=student_profile.user,
            message=f"Application submitted for '{opportunity.title}' at {opportunity.company.name} (Match Score: {match_score}%).",
            link=reverse('applications:student_applications'),
            send_email=True,
        )

        # Notification for company recruiters
        for recruiter in opportunity.company.users.filter(role='recruiter'):
            send_notification(
                user=recruiter,
                message=f"New applicant {student_profile.roll_no} applied for '{opportunity.title}' (Match: {match_score}%).",
                link=reverse('applications:applicant_list', kwargs={'opp_pk': opportunity.pk}),
            )

        create_audit_log(changed_by_user, 'SUBMIT_APPLICATION', 'Application', app.pk)

    return app


def transition_application_status(
    application: Application,
    new_status: str,
    changed_by_user: Any,
) -> Application:
    """
    Executes an atomic status transition adhering to Core Rule 3.
    """
    old_status = application.status

    if new_status == old_status:
        return application

    allowed = VALID_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        raise ValidationError(
            f"Invalid transition from '{application.get_status_display()}' to '{ApplicationStatus(new_status).label}'. "
            f"Allowed next states: {', '.join(ApplicationStatus(s).label for s in allowed) if allowed else 'None (Final State)'}."
        )

    # Withdrawn only allowed by student
    if new_status == ApplicationStatus.WITHDRAWN:
        if changed_by_user != application.student.user and not changed_by_user.is_superuser:
            raise ValidationError("Only the student candidate may withdraw their application.")

    with transaction.atomic():
        application.status = new_status
        application.save(update_fields=['status'])

        StatusLog.objects.create(
            application=application,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by_user,
        )

        # Notify student
        status_label = application.get_status_display()
        send_notification(
            user=application.student.user,
            message=f"Your application status for '{application.opportunity.title}' has been updated to '{status_label}'.",
            link=reverse('applications:student_applications'),
            send_email=True,
        )

        create_audit_log(changed_by_user, f'APPLICATION_STATUS_{new_status.upper()}', 'Application', application.pk)

    return application
