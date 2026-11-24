from datetime import timedelta

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    STUDENT = 'student', 'Student'
    FACULTY = 'faculty', 'Faculty (Mentor)'
    RECRUITER = 'recruiter', 'Recruiter'
    OFFICER = 'officer', 'Placement Officer'
    ADMIN = 'admin', 'Admin'


class UserManager(BaseUserManager):
    """Custom manager for User where email is the unique identifier for auth."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', UserRole.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model with email as username and role-based fields."""

    username = None
    email = models.EmailField(unique=True, verbose_name='email address')

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
    )
    is_verified = models.BooleanField(
        default=False,
        help_text='Designates whether the user has verified their email address.',
    )

    # Nullable FK to Institution (students, faculty, officers)
    institution = models.ForeignKey(
        'orgs.Institution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    # Nullable FK to Company (recruiters)
    company = models.ForeignKey(
        'orgs.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    # Failed logins & account lockout
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ['email']

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_locked(self):
        """Returns True if account is currently locked out."""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def register_failed_login(self):
        """Increment failed attempts and lock for 15 minutes after 5 failures."""
        # If previous lock expired, reset counter first
        if self.locked_until and self.locked_until <= timezone.now():
            self.failed_login_attempts = 0
            self.locked_until = None

        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=15)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def reset_failed_logins(self):
        """Reset failed attempts and unlock."""
        if self.failed_login_attempts > 0 or self.locked_until is not None:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=['failed_login_attempts', 'locked_until'])
