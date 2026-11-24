from django.conf import settings
from django.db import models


class ApplicationStatus(models.TextChoices):
    APPLIED = 'applied', 'Applied'
    SHORTLISTED = 'shortlisted', 'Shortlisted'
    INTERVIEW = 'interview', 'Interview'
    OFFERED = 'offered', 'Offered'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'
    WITHDRAWN = 'withdrawn', 'Withdrawn'


class Application(models.Model):
    student = models.ForeignKey(
        'profiles.StudentProfile',
        on_delete=models.CASCADE,
        related_name='applications',
    )
    opportunity = models.ForeignKey(
        'opportunities.Opportunity',
        on_delete=models.CASCADE,
        related_name='applications',
    )
    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.APPLIED,
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    match_score_at_apply = models.PositiveSmallIntegerField(
        default=0,
        help_text='Computed skill match score (0-100) at application time',
    )

    class Meta:
        unique_together = ('student', 'opportunity')
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.student.roll_no} -> {self.opportunity.title} ({self.get_status_display()})"


class StatusLog(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='status_logs',
    )
    old_status = models.CharField(max_length=20, choices=ApplicationStatus.choices)
    new_status = models.CharField(max_length=20, choices=ApplicationStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.application.student.roll_no}: {self.old_status} -> {self.new_status}"
