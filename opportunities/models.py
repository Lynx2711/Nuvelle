from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from skills.models import SkillLevel


class OpportunityType(models.TextChoices):
    INTERNSHIP = 'internship', 'Internship'
    JOB = 'job', 'Full-Time Job'


class OpportunityMode(models.TextChoices):
    ON_SITE = 'on_site', 'On-Site'
    REMOTE = 'remote', 'Remote'
    HYBRID = 'hybrid', 'Hybrid'


class OpportunityStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PUBLISHED = 'published', 'Published'
    CLOSED = 'closed', 'Closed'


class Opportunity(models.Model):
    company = models.ForeignKey(
        'orgs.Company',
        on_delete=models.CASCADE,
        related_name='opportunities',
    )
    title = models.CharField(max_length=200)
    type = models.CharField(
        max_length=20,
        choices=OpportunityType.choices,
        default=OpportunityType.INTERNSHIP,
    )
    description = models.TextField()
    location = models.CharField(max_length=150, help_text='City, State or Remote')
    mode = models.CharField(
        max_length=20,
        choices=OpportunityMode.choices,
        default=OpportunityMode.ON_SITE,
    )
    pay_min = models.PositiveIntegerField(null=True, blank=True, help_text='Minimum pay in INR')
    pay_max = models.PositiveIntegerField(null=True, blank=True, help_text='Maximum pay in INR')
    openings = models.PositiveIntegerField(default=1)
    deadline = models.DateTimeField(help_text='Application deadline (UTC, displayed in Asia/Kolkata)')
    min_cgpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Minimum CGPA (0.00-10.00)',
    )
    programme = models.CharField(
        max_length=100,
        blank=True,
        help_text='Eligible degree/programme (leave blank for all)',
    )
    batch = models.CharField(
        max_length=50,
        blank=True,
        help_text='Eligible batch (leave blank for all)',
    )
    status = models.CharField(
        max_length=20,
        choices=OpportunityStatus.choices,
        default=OpportunityStatus.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Opportunities'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['type', 'deadline', 'status'], name='opp_type_dead_stat_idx'),
            models.Index(fields=['company'], name='opp_company_idx'),
        ]

    def check_and_auto_close(self) -> bool:
        """Read-time check: If published and deadline passed, auto-close atomically."""
        if self.status == OpportunityStatus.PUBLISHED and self.deadline and timezone.now() > self.deadline:
            self.status = OpportunityStatus.CLOSED
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False

    @property
    def is_expired(self) -> bool:
        return bool(self.deadline and timezone.now() > self.deadline)

    def __str__(self):
        return f"{self.title} at {self.company.name} ({self.get_type_display()})"


class OpportunitySkill(models.Model):
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name='required_skills',
    )
    skill = models.ForeignKey(
        'skills.Skill',
        on_delete=models.CASCADE,
        related_name='opportunity_requirements',
    )
    required_level = models.PositiveSmallIntegerField(
        choices=SkillLevel.choices,
        default=SkillLevel.BEGINNER,
        help_text='Required proficiency level (1-4)',
    )
    weight = models.PositiveSmallIntegerField(
        default=1,
        help_text='Importance weight (1-5)',
    )

    class Meta:
        unique_together = ('opportunity', 'skill')
        ordering = ['-weight', 'skill__name']

    def clean(self):
        if self.required_level not in [1, 2, 3, 4]:
            raise ValidationError({'required_level': 'Required level must be between 1 and 4.'})
        if not (1 <= self.weight <= 5):
            raise ValidationError({'weight': 'Weight must be between 1 and 5.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.opportunity.title} - {self.skill.name} (Lvl {self.required_level}, Wt {self.weight})"
