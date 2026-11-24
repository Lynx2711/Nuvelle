from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User, UserRole
from notifications.context_processors import unread_notifications
from notifications.models import Notification
from notifications.services import (
    create_audit_log,
    mark_all_notifications_as_read,
    mark_notification_as_read,
    send_email_with_retry,
    send_notification,
)
from orgs.models import Company, Institution


@pytest.fixture
def institution(db):
    return Institution.objects.create(name="IIT Delhi", city="New Delhi", is_approved=True)


@pytest.fixture
def company(db):
    return Company.objects.create(name="Infosys", industry="IT Services", is_approved=True)


@pytest.fixture
def student_user(db, institution):
    return User.objects.create_user(
        email="student@iitd.ac.in",
        password="Password123",
        role=UserRole.STUDENT,
        institution=institution,
        is_verified=True,
    )


@pytest.fixture
def recruiter_user(db, company):
    return User.objects.create_user(
        email="recruiter@infosys.com",
        password="Password123",
        role=UserRole.RECRUITER,
        company=company,
        is_verified=True,
    )


# =========================================================================
# Unit Tests: Notification & Email Retry Services
# =========================================================================

@pytest.mark.django_db
class TestNotificationAndEmailServices:
    def test_send_notification_creates_in_app_record(self, student_user):
        notification = send_notification(
            user=student_user,
            message="Your skill has been verified.",
            link="/profiles/me/",
        )
        assert notification.pk is not None
        assert notification.user == student_user
        assert notification.is_read is False
        assert notification.message == "Your skill has been verified."
        assert notification.link == "/profiles/me/"

    def test_send_notification_with_email_dispatches_mail(self, student_user):
        with patch('notifications.services.send_mail') as mock_send:
            send_notification(
                user=student_user,
                message="Offer extended for Software Engineer role.",
                link="/applications/my/",
                send_email=True,
            )
            assert mock_send.call_count == 1
            call_kwargs = mock_send.call_args[1]
            assert "Offer extended" in call_kwargs['message']
            assert student_user.email in call_kwargs['recipient_list']

    def test_send_email_with_retry_succeeds_first_attempt(self):
        with patch('notifications.services.send_mail') as mock_send:
            success = send_email_with_retry(
                subject="Test Subject",
                message="Test Message",
                recipient_list=["test@example.com"],
                max_retries=3,
            )
            assert success is True
            assert mock_send.call_count == 1

    def test_send_email_with_retry_retries_three_times_on_failure(self):
        """
        Verifies retry up to 3 times on transient connection errors before reporting failure.
        """
        with patch('notifications.services.send_mail', side_effect=Exception("SMTP Connection Error")) as mock_send:
            with patch('time.sleep') as mock_sleep:
                success = send_email_with_retry(
                    subject="Test Subject",
                    message="Test Message",
                    recipient_list=["test@example.com"],
                    max_retries=3,
                )
                assert success is False
                assert mock_send.call_count == 3
                assert mock_sleep.call_count == 2  # Sleep between attempt 1-2 and 2-3

    def test_mark_notification_as_read(self, student_user):
        n1 = send_notification(student_user, "Message 1")
        n2 = send_notification(student_user, "Message 2")
        assert Notification.objects.filter(user=student_user, is_read=False).count() == 2

        # Mark single
        mark_notification_as_read(n1.pk, student_user)
        n1.refresh_from_db()
        assert n1.is_read is True
        assert n2.is_read is False

        # Mark all
        mark_all_notifications_as_read(student_user)
        n2.refresh_from_db()
        assert n2.is_read is True
        assert Notification.objects.filter(user=student_user, is_read=False).count() == 0

    def test_create_audit_log(self, student_user):
        log = create_audit_log(
            user=student_user,
            action="APPLICATION_STATUS_SHORTLISTED",
            object_type="Application",
            object_id=42,
        )
        assert log.pk is not None
        assert log.user == student_user
        assert log.action == "APPLICATION_STATUS_SHORTLISTED"
        assert log.object_id == "42"


# =========================================================================
# Integration Tests: In-App Notification Views & Context Processors
# =========================================================================

@pytest.mark.django_db
class TestInAppNotificationViews:
    def test_notification_list_view_and_filtering(self, client: Client, student_user):
        send_notification(student_user, "Unread update 1")
        n2 = send_notification(student_user, "Read update 2")
        mark_notification_as_read(n2.pk, student_user)

        client.force_login(student_user)

        # All notifications
        res_all = client.get(reverse('notifications:notification_list'))
        assert res_all.status_code == 200
        assert "Unread update 1" in res_all.content.decode()
        assert "Read update 2" in res_all.content.decode()

        # Unread filter
        res_unread = client.get(reverse('notifications:notification_list'), {'filter': 'unread'})
        assert res_unread.status_code == 200
        assert "Unread update 1" in res_unread.content.decode()
        assert "Read update 2" not in res_unread.content.decode()

        # Read filter
        res_read = client.get(reverse('notifications:notification_list'), {'filter': 'read'})
        assert res_read.status_code == 200
        assert "Unread update 1" not in res_read.content.decode()
        assert "Read update 2" in res_read.content.decode()

    def test_mark_single_notification_read_action(self, client: Client, student_user):
        n = send_notification(student_user, "Important announcement")
        assert n.is_read is False

        client.force_login(student_user)
        res = client.post(reverse('notifications:mark_read', kwargs={'pk': n.pk}))
        assert res.status_code == 302
        n.refresh_from_db()
        assert n.is_read is True

    def test_mark_all_notifications_read_action(self, client: Client, student_user):
        send_notification(student_user, "Msg 1")
        send_notification(student_user, "Msg 2")

        client.force_login(student_user)
        res = client.post(reverse('notifications:mark_all_read'))
        assert res.status_code == 302
        assert Notification.objects.filter(user=student_user, is_read=False).count() == 0

    def test_unread_notifications_context_processor(self, student_user):
        class DummyRequest:
            pass

        req = DummyRequest()
        req.user = student_user

        assert unread_notifications(req)['unread_notifications_count'] == 0

        send_notification(student_user, "Alert 1")
        send_notification(student_user, "Alert 2")
        assert unread_notifications(req)['unread_notifications_count'] == 2

        # Anonymous request
        anon_req = DummyRequest()
        anon_req.user = None
        assert unread_notifications(anon_req)['unread_notifications_count'] == 0


# =========================================================================
# Integration Tests: Comprehensive Role Dashboards
# =========================================================================

@pytest.mark.django_db
class TestRoleDashboards:
    def test_student_dashboard_metrics_and_notifications(self, client: Client, student_user):
        from profiles.models import StudentProfile
        StudentProfile.objects.create(
            user=student_user,
            institution=student_user.institution,
            roll_no="DASH101",
            programme="B.Tech CS",
            batch="2025",
            cgpa=9.1,
        )
        send_notification(student_user, "Welcome to your student dashboard.")

        client.force_login(student_user)
        res = client.get(reverse('accounts:student_dashboard'))
        assert res.status_code == 200
        content = res.content.decode()

        assert "Student Dashboard" in content
        assert "Profile Completeness" in content
        assert "My Applications Pipeline" in content
        assert "Welcome to your student dashboard." in content
        assert res.context['unread_notifications_count'] == 1

    def test_recruiter_dashboard_metrics(self, client: Client, recruiter_user):
        send_notification(recruiter_user, "Review your active hiring campaigns.")
        client.force_login(recruiter_user)

        res = client.get(reverse('accounts:recruiter_dashboard'))
        assert res.status_code == 200
        content = res.content.decode()

        assert "Recruiter Dashboard" in content
        assert "My Hiring Overview" in content
        assert "Recent Postings & Pipeline" in content
        assert "Review your active hiring campaigns." in content

    def test_faculty_dashboard_metrics(self, client: Client, institution):
        faculty = User.objects.create_user(
            email="faculty@iitd.ac.in", password="Password123", role=UserRole.FACULTY, institution=institution
        )
        send_notification(faculty, "You have student skills to verify.")
        client.force_login(faculty)

        res = client.get(reverse('accounts:faculty_dashboard'))
        assert res.status_code == 200
        content = res.content.decode()

        assert "Faculty Mentor Dashboard" in content
        assert "Skill Verification Queue" in content
        assert "Recent Pending Skill Claims" in content

    def test_officer_dashboard_metrics(self, client: Client, institution):
        officer = User.objects.create_user(
            email="officer@iitd.ac.in", password="Password123", role=UserRole.OFFICER, institution=institution
        )
        client.force_login(officer)

        res = client.get(reverse('accounts:officer_dashboard'))
        assert res.status_code == 200
        content = res.content.decode()

        assert "Placement Officer Dashboard" in content
        assert "Cohort Size" in content
        assert "Skill Verifications" in content

    def test_admin_dashboard_metrics_and_audit_trail(self, client: Client):
        admin = User.objects.create_superuser(email="admin@nuvelle.edu", password="Password123")
        create_audit_log(admin, "TEST_SYSTEM_INIT", "Platform", 1)
        client.force_login(admin)

        res = client.get(reverse('accounts:admin_dashboard'))
        assert res.status_code == 200
        content = res.content.decode()

        assert "Administrator Dashboard" in content
        assert "System Compliance & Audit Trail" in content
        assert "TEST_SYSTEM_INIT" in content
