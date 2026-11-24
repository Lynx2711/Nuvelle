from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from skills.models import SkillLevel


class StudentSkillStatus(models.TextChoices):
    UNVERIFIED = 'unverified', 'Unverified'
    VERIFIED = 'verified', 'Verified'
    REJECTED = 'rejected', 'Rejected'


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile',
    )
    institution = models.ForeignKey(
        'orgs.Institution',
        on_delete=models.CASCADE,
        related_name='student_profiles',
    )
    roll_no = models.CharField(max_length=50)
    programme = models.CharField(max_length=100)
    batch = models.CharField(max_length=50)
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    graduation_year = models.PositiveIntegerField(null=True, blank=True)
    is_placed = models.BooleanField(
        default=False,
        help_text="Indicates whether the student has accepted a placement offer",
    )
    resume_file = models.FileField(upload_to='resumes/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('institution', 'roll_no')
        ordering = ['institution', 'roll_no']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.email} ({self.roll_no})"

    @property
    def completeness_percentage(self) -> int:
        """
        Calculates profile completeness percentage:
        - Academic details (roll_no, programme, batch, cgpa): 25%
        - Resume file uploaded: 25%
        - At least 1 self-assessed skill: 25%
        - At least 1 project or certification: 25%
        Total: 100%
        """
        score = 0
        # 1. Academic details
        if self.roll_no and self.programme and self.batch and self.cgpa:
            score += 25
        elif self.roll_no and self.programme and self.batch:
            score += 15

        # 2. Resume file
        if self.resume_file:
            score += 25

        # 3. Skills
        if self.skills.exists():
            score += 25

        # 4. Projects or Certifications
        if self.projects.exists() or self.certifications.exists():
            score += 25

        return min(100, score)


class StudentSkill(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='skills',
    )
    skill = models.ForeignKey(
        'skills.Skill',
        on_delete=models.CASCADE,
        related_name='student_skills',
    )
    level = models.PositiveSmallIntegerField(
        choices=SkillLevel.choices,
        default=SkillLevel.BEGINNER,
        help_text='Self-assessed proficiency level (1-4)',
    )
    status = models.CharField(
        max_length=20,
        choices=StudentSkillStatus.choices,
        default=StudentSkillStatus.UNVERIFIED,
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_student_skills',
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'skill')
        ordering = ['-level', 'skill__name']

    def clean(self):
        if self.status == StudentSkillStatus.REJECTED and not self.rejection_reason.strip():
            raise ValidationError({'rejection_reason': 'A rejection reason is mandatory when rejecting a skill.'})

    def save(self, *args, **kwargs):
        # Rule 4: Editing a verified skill resets it to unverified
        if self.pk:
            old = StudentSkill.objects.filter(pk=self.pk).first()
            if old and old.status == StudentSkillStatus.VERIFIED and old.level != self.level:
                # Level was edited by student -> reset verification
                self.status = StudentSkillStatus.UNVERIFIED
                self.verified_by = None
                self.rejection_reason = ''
                self.verified_at = None

        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.roll_no} - {self.skill.name} ({self.get_level_display()} - {self.get_status_display()})"


class Project(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='projects',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    link = models.URLField(blank=True, help_text='Link to GitHub repo, demo, or project document.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.student.roll_no})"


class Certification(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='certifications',
    )
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200)
    issued_on = models.DateField(null=True, blank=True)
    credential_url = models.URLField(blank=True, help_text='Verification URL or badge link.')
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issued_on', '-created_at']

    def __str__(self):
        return f"{self.name} - {self.issuer} ({self.student.roll_no})"
