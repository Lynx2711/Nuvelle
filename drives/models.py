from django.db import models
from django.utils import timezone


class DriveStatus(models.TextChoices):
    SCHEDULED = 'scheduled', 'Scheduled'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class PlacementDrive(models.Model):
    opportunity = models.ForeignKey(
        'opportunities.Opportunity',
        on_delete=models.CASCADE,
        related_name='placement_drives',
    )
    institution = models.ForeignKey(
        'orgs.Institution',
        on_delete=models.CASCADE,
        related_name='placement_drives',
    )
    drive_date = models.DateField()
    venue = models.CharField(max_length=255)
    rules = models.TextField(blank=True, help_text="Specific drive guidelines, dress code, rounds rules")
    status = models.CharField(
        max_length=20,
        choices=DriveStatus.choices,
        default=DriveStatus.SCHEDULED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-drive_date', 'institution']
        unique_together = ('opportunity', 'institution', 'drive_date')

    def __str__(self):
        return f"Drive for {self.opportunity.title} at {self.institution.name} on {self.drive_date}"


class DriveRound(models.Model):
    drive = models.ForeignKey(
        PlacementDrive,
        on_delete=models.CASCADE,
        related_name='rounds',
    )
    name = models.CharField(max_length=150, help_text="e.g. Online Assessment, Technical Interview, HR Round")
    sequence = models.PositiveSmallIntegerField(default=1)
    round_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sequence', 'created_at']

    def __str__(self):
        return f"Round {self.sequence}: {self.name} ({self.drive.opportunity.title})"


class OfferStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ACCEPTED = 'accepted', 'Accepted'
    DECLINED = 'declined', 'Declined'


class Offer(models.Model):
    application = models.OneToOneField(
        'applications.Application',
        on_delete=models.CASCADE,
        related_name='offer',
    )
    package = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Package / CTC in INR (e.g. 1200000.00)",
    )
    offered_on = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=OfferStatus.choices,
        default=OfferStatus.PENDING,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-offered_on', '-package']

    def __str__(self):
        return f"Offer for {self.application.student.roll_no} - ₹{self.package} ({self.get_status_display()})"
