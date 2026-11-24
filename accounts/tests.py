from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from accounts.tokens import (
    generate_email_verification_token,
    generate_password_reset_token,
    verify_email_verification_token,
    verify_password_reset_token,
)
from accounts.validators import LetterAndDigitValidator
from orgs.models import Company, Institution

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_with_email_success(self):
        user = User.objects.create_user(
            email='student1@college.edu',
            password='Password123',
            role=UserRole.STUDENT,
        )
        assert user.email == 'student1@college.edu'
        assert user.role == UserRole.STUDENT
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_verified is False
        assert user.check_password('Password123')

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email='admin@nuvelle.edu',
            password='AdminPassword123',
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.is_verified is True
        assert admin.role == UserRole.ADMIN

    def test_user_requires_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user(email='', password='Password123')

    def test_user_org_relations(self):
        inst = Institution.objects.create(name='IIT Bombay', city='Mumbai', is_approved=True)
        comp = Company.objects.create(name='TechCorp', industry='Software', is_approved=True)

        student = User.objects.create_user(
            email='student2@college.edu',
            password='Password123',
            role=UserRole.STUDENT,
            institution=inst,
        )
        recruiter = User.objects.create_user(
            email='recruiter@techcorp.com',
            password='Password123',
            role=UserRole.RECRUITER,
            company=comp,
        )
        assert student.institution == inst
        assert student.company is None
        assert recruiter.company == comp
        assert recruiter.institution is None


class TestPasswordValidator:
    def test_password_requires_letter_and_digit(self):
        validator = LetterAndDigitValidator()

        # Only letters
        with pytest.raises(ValidationError):
            validator.validate('abcdefgh')

        # Only digits
        with pytest.raises(ValidationError):
            validator.validate('12345678')

        # Valid: letters and digits
        validator.validate('ValidPass123')


@pytest.mark.django_db
class TestTokens:
    def test_email_verification_token_lifecycle(self):
        user = User.objects.create_user(email='test_token@nuvelle.edu', password='Password123')
        token = generate_email_verification_token(user)

        # Valid token
        verified_user = verify_email_verification_token(token, max_age=86400)
        assert verified_user == user

        # Invalid token
        assert verify_email_verification_token('invalid-token') is None

        # Expired token (simulate 25 hours later)
        expired_user = verify_email_verification_token(token, max_age=-1)
        assert expired_user is None

    def test_password_reset_token_lifecycle(self):
        user = User.objects.create_user(email='test_reset@nuvelle.edu', password='OldPassword123')
        token = generate_password_reset_token(user)

        # Valid token
        reset_user = verify_password_reset_token(token, max_age=3600)
        assert reset_user == user

        # Token invalidated when password changed
        user.set_password('NewPassword123')
        user.save()
        assert verify_password_reset_token(token, max_age=3600) is None


@pytest.mark.django_db
class TestAccountLockout:
    def test_lockout_after_five_failed_attempts(self, client):
        user = User.objects.create_user(email='victim@nuvelle.edu', password='CorrectPassword123')

        url = reverse('accounts:login')

        # 4 incorrect attempts
        for attempt in range(1, 5):
            resp = client.post(url, {'email': 'victim@nuvelle.edu', 'password': 'WrongPassword123'})
            assert resp.status_code == 200
            user.refresh_from_db()
            assert user.failed_login_attempts == attempt
            assert user.is_locked is False

        # 5th attempt -> triggers lockout
        resp = client.post(url, {'email': 'victim@nuvelle.edu', 'password': 'WrongPassword123'})
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.failed_login_attempts == 5
        assert user.is_locked is True
        assert user.locked_until > timezone.now()

        # Subsequent attempt even with CORRECT password is denied during lockout
        resp = client.post(url, {'email': 'victim@nuvelle.edu', 'password': 'CorrectPassword123'})
        assert resp.status_code == 200
        assert '_auth_user_id' not in client.session

        # Advance time past 15 min lock
        user.locked_until = timezone.now() - timedelta(minutes=1)
        user.save()

        # Now login with correct password works and resets lockout
        resp = client.post(url, {'email': 'victim@nuvelle.edu', 'password': 'CorrectPassword123'})
        assert resp.status_code == 302
        user.refresh_from_db()
        assert user.failed_login_attempts == 0
        assert user.locked_until is None


@pytest.mark.django_db
class TestRoleDashboardRoutingAndAccess:
    def test_role_based_redirects(self, client):
        student = User.objects.create_user(email='s@nuvelle.edu', password='Pass1234', role=UserRole.STUDENT)
        recruiter = User.objects.create_user(email='r@nuvelle.edu', password='Pass1234', role=UserRole.RECRUITER)
        officer = User.objects.create_user(email='o@nuvelle.edu', password='Pass1234', role=UserRole.OFFICER)
        faculty = User.objects.create_user(email='f@nuvelle.edu', password='Pass1234', role=UserRole.FACULTY)

        # Student redirect
        client.force_login(student)
        resp = client.get(reverse('accounts:dashboard_redirect'))
        assert resp.status_code == 302
        assert resp.url == reverse('accounts:student_dashboard')

        # Recruiter redirect
        client.force_login(recruiter)
        resp = client.get(reverse('accounts:dashboard_redirect'))
        assert resp.status_code == 302
        assert resp.url == reverse('accounts:recruiter_dashboard')

        # Officer redirect
        client.force_login(officer)
        resp = client.get(reverse('accounts:dashboard_redirect'))
        assert resp.status_code == 302
        assert resp.url == reverse('accounts:officer_dashboard')

        # Faculty redirect
        client.force_login(faculty)
        resp = client.get(reverse('accounts:dashboard_redirect'))
        assert resp.status_code == 302
        assert resp.url == reverse('accounts:faculty_dashboard')

    def test_cross_role_access_forbidden(self, client):
        student = User.objects.create_user(email='student@nuvelle.edu', password='Pass1234', role=UserRole.STUDENT)
        client.force_login(student)

        # Student trying to view Recruiter Dashboard -> 403 Forbidden
        resp = client.get(reverse('accounts:recruiter_dashboard'))
        assert resp.status_code == 403


@pytest.mark.django_db
class TestRegistrationAndVerificationFlow:
    def test_registration_and_verification(self, client):
        # Register student
        resp = client.post(reverse('accounts:register'), {
            'first_name': 'Aarav',
            'last_name': 'Sharma',
            'email': 'aarav@college.edu',
            'role': UserRole.STUDENT,
            'password': 'SecurePass123',
            'confirm_password': 'SecurePass123',
        })
        assert resp.status_code == 302

        user = User.objects.get(email='aarav@college.edu')
        assert user.is_verified is False

        # Generate token and verify
        token = generate_email_verification_token(user)
        resp = client.get(reverse('accounts:verify_email', kwargs={'token': token}))
        assert resp.status_code == 302

        user.refresh_from_db()
        assert user.is_verified is True
