import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import User, UserRole
from orgs.models import Institution
from profiles.forms import StudentProfileForm
from profiles.models import (
    Certification,
    Project,
    StudentProfile,
    StudentSkill,
    StudentSkillStatus,
)
from profiles.services import import_students_from_csv
from skills.models import Skill, SkillCategory, SkillLevel


@pytest.mark.django_db
class TestStudentCSVImport:
    @pytest.fixture
    def setup_data(self):
        inst = Institution.objects.create(name='IIT Madras', city='Chennai', is_approved=True)
        officer = User.objects.create_user(
            email='officer@iitm.ac.in',
            password='Password123',
            role=UserRole.OFFICER,
            institution=inst,
        )
        return inst, officer

    def test_import_clean_csv(self, setup_data):
        inst, _ = setup_data

        csv_content = (
            "roll_no,name,email,programme,batch,cgpa\n"
            "CS202101,Aarav Sharma,aarav@iitm.ac.in,B.Tech CSE,2025,8.95\n"
            "CS202102,Diya Patel,diya@iitm.ac.in,B.Tech CSE,2025,9.20\n"
            "EC202101,Rohan Iyer,rohan@iitm.ac.in,B.Tech ECE,2025,7.80\n"
        )
        csv_file = io.StringIO(csv_content)

        success_count, errors = import_students_from_csv(csv_file, inst)
        assert success_count == 3
        assert len(errors) == 0

        profile = StudentProfile.objects.get(institution=inst, roll_no='CS202101')
        assert profile.user.email == 'aarav@iitm.ac.in'
        assert profile.user.first_name == 'Aarav'
        assert profile.user.last_name == 'Sharma'
        assert profile.programme == 'B.Tech CSE'
        assert profile.batch == '2025'
        assert float(profile.cgpa) == 8.95
        assert profile.user.is_verified is True
        assert profile.user.role == UserRole.STUDENT

    def test_import_skips_invalid_rows_and_creates_valid_rows(self, setup_data):
        inst, _ = setup_data

        existing_user = User.objects.create_user(email='existing@iitm.ac.in', password='Password123')
        StudentProfile.objects.create(
            user=existing_user,
            institution=inst,
            roll_no='EXISTING01',
            programme='B.Tech',
            batch='2025',
        )

        csv_content = (
            "roll_no,name,email,programme,batch,cgpa\n"
            "VALID01,Sunil Kumar,sunil@iitm.ac.in,B.Tech ME,2025,8.10\n"
            "EXISTING01,Duplicate Roll,dup_roll@iitm.ac.in,B.Tech,2025,7.50\n"
            "INV02,Bad Email,not-an-email,B.Tech,2025,8.00\n"
            "INV03,Bad CGPA,bad_cgpa@iitm.ac.in,B.Tech,2025,12.50\n"
            "INV04,Existing Email,existing@iitm.ac.in,B.Tech,2025,7.00\n"
            "VALID02,Meera Nair,meera@iitm.ac.in,B.Tech EE,2025,9.40\n"
        )
        csv_file = io.StringIO(csv_content)

        success_count, errors = import_students_from_csv(csv_file, inst)
        assert success_count == 2
        assert len(errors) == 4

        assert StudentProfile.objects.filter(institution=inst, roll_no='VALID01').exists()
        assert StudentProfile.objects.filter(institution=inst, roll_no='VALID02').exists()

    def test_officer_csv_upload_view(self, client, setup_data):
        inst, officer = setup_data
        client.force_login(officer)

        csv_data = b"roll_no,name,email,programme,batch,cgpa\nTEST01,Test Student,test@iitm.ac.in,B.Tech,2025,8.5\n"
        uploaded_file = SimpleUploadedFile("students.csv", csv_data, content_type="text/csv")

        url = reverse('profiles:import_students')
        resp = client.post(url, {'csv_file': uploaded_file})
        assert resp.status_code == 302
        assert resp.url == reverse('profiles:import_report')

        assert StudentProfile.objects.filter(institution=inst, roll_no='TEST01').exists()

    def test_student_cannot_access_csv_import(self, client):
        student = User.objects.create_user(email='student_unauth@nuvelle.edu', password='Pass1234Student', role=UserRole.STUDENT)
        client.force_login(student)

        resp = client.get(reverse('profiles:import_students'))
        assert resp.status_code == 403


@pytest.mark.django_db
class TestProfileCompletenessAndResumeValidation:
    def test_completeness_calculation(self):
        inst = Institution.objects.create(name='NIT Trichy', city='Trichy', is_approved=True)
        user = User.objects.create_user(email='complete@nitt.edu', password='Password123', role=UserRole.STUDENT)

        profile = StudentProfile.objects.create(
            user=user,
            institution=inst,
            roll_no='106122001',
            programme='B.Tech CSE',
            batch='2026',
            cgpa=Decimal('8.50'),
        )
        # Academic details filled = 25%
        assert profile.completeness_percentage == 25

        # Upload resume -> +25% = 50%
        profile.resume_file = SimpleUploadedFile("resume.pdf", b"%PDF-1.4 dummy", content_type="application/pdf")
        profile.save()
        assert profile.completeness_percentage == 50

        # Add skill -> +25% = 75%
        cat = SkillCategory.objects.create(name='DevOps')
        skill = Skill.objects.create(name='Docker', category=cat)
        StudentSkill.objects.create(student=profile, skill=skill, level=SkillLevel.INTERMEDIATE)
        assert profile.completeness_percentage == 75

        # Add project -> +25% = 100%
        Project.objects.create(student=profile, title='CI/CD Pipeline', description='Automated builds')
        assert profile.completeness_percentage == 100

    def test_resume_pdf_and_size_validation(self):
        # Non-PDF rejection
        txt_file = SimpleUploadedFile("resume.txt", b"plain text", content_type="text/plain")
        form = StudentProfileForm(data={'programme': 'B.Tech', 'batch': '2026'}, files={'resume_file': txt_file})
        assert not form.is_valid()
        assert 'resume_file' in form.errors

        # Exceeding 2 MB rejection
        big_bytes = b"0" * (2 * 1024 * 1024 + 100)
        big_pdf = SimpleUploadedFile("big.pdf", big_bytes, content_type="application/pdf")
        form2 = StudentProfileForm(data={'programme': 'B.Tech', 'batch': '2026'}, files={'resume_file': big_pdf})
        assert not form2.is_valid()
        assert 'resume_file' in form2.errors


@pytest.mark.django_db
class TestSkillVerificationRules:
    @pytest.fixture
    def env_setup(self):
        inst1 = Institution.objects.create(name='IIT Delhi', city='Delhi', is_approved=True)
        inst2 = Institution.objects.create(name='IIT Bombay', city='Mumbai', is_approved=True)

        student = User.objects.create_user(email='stu1@iitd.ac.in', password='Pass1234Student', role=UserRole.STUDENT, institution=inst1)
        faculty_iitd = User.objects.create_user(email='prof1@iitd.ac.in', password='Pass1234Faculty', role=UserRole.FACULTY, institution=inst1)
        faculty_iitb = User.objects.create_user(email='prof2@iitb.ac.in', password='Pass1234Faculty', role=UserRole.FACULTY, institution=inst2)

        profile = StudentProfile.objects.create(user=student, institution=inst1, roll_no='2021CS101', programme='CSE', batch='2025')
        cat = SkillCategory.objects.create(name='Languages')
        skill = Skill.objects.create(name='C++', category=cat)

        return {
            'inst1': inst1,
            'inst2': inst2,
            'student': student,
            'faculty_iitd': faculty_iitd,
            'faculty_iitb': faculty_iitb,
            'profile': profile,
            'skill': skill,
        }

    def test_self_assessed_skill_defaults_unverified(self, env_setup):
        profile = env_setup['profile']
        skill = env_setup['skill']

        stu_skill = StudentSkill.objects.create(
            student=profile,
            skill=skill,
            level=SkillLevel.INTERMEDIATE,
        )
        assert stu_skill.status == StudentSkillStatus.UNVERIFIED
        assert stu_skill.verified_by is None

    def test_faculty_can_approve_skill(self, client, env_setup):
        profile = env_setup['profile']
        skill = env_setup['skill']
        faculty = env_setup['faculty_iitd']

        stu_skill = StudentSkill.objects.create(student=profile, skill=skill, level=SkillLevel.INTERMEDIATE)

        client.force_login(faculty)
        url = reverse('profiles:approve_skill', kwargs={'pk': stu_skill.pk})
        resp = client.post(url)
        assert resp.status_code == 302

        stu_skill.refresh_from_db()
        assert stu_skill.status == StudentSkillStatus.VERIFIED
        assert stu_skill.verified_by == faculty
        assert stu_skill.verified_at is not None

    def test_faculty_can_reject_skill_with_mandatory_reason(self, client, env_setup):
        profile = env_setup['profile']
        skill = env_setup['skill']
        faculty = env_setup['faculty_iitd']

        stu_skill = StudentSkill.objects.create(student=profile, skill=skill, level=SkillLevel.ADVANCED)
        client.force_login(faculty)
        url = reverse('profiles:reject_skill', kwargs={'pk': stu_skill.pk})

        # Missing reason -> fails
        client.post(url, {'rejection_reason': ''})
        stu_skill.refresh_from_db()
        assert stu_skill.status == StudentSkillStatus.UNVERIFIED

        # With mandatory reason -> succeeds
        resp = client.post(url, {'rejection_reason': 'Insufficient project proof for Advanced level.'})
        assert resp.status_code == 302
        stu_skill.refresh_from_db()
        assert stu_skill.status == StudentSkillStatus.REJECTED
        assert stu_skill.verified_by == faculty
        assert stu_skill.rejection_reason == 'Insufficient project proof for Advanced level.'

    def test_faculty_can_adjust_skill_level(self, client, env_setup):
        profile = env_setup['profile']
        skill = env_setup['skill']
        faculty = env_setup['faculty_iitd']

        # Student claimed Expert (4)
        stu_skill = StudentSkill.objects.create(student=profile, skill=skill, level=SkillLevel.EXPERT)

        client.force_login(faculty)
        url = reverse('profiles:adjust_skill', kwargs={'pk': stu_skill.pk})
        # Faculty adjusts to Intermediate (2)
        resp = client.post(url, {'adjusted_level': '2'})
        assert resp.status_code == 302

        stu_skill.refresh_from_db()
        assert stu_skill.level == SkillLevel.INTERMEDIATE
        assert stu_skill.status == StudentSkillStatus.VERIFIED
        assert stu_skill.verified_by == faculty

    def test_rule_4_editing_verified_skill_resets_to_unverified(self, env_setup):
        profile = env_setup['profile']
        skill = env_setup['skill']
        faculty = env_setup['faculty_iitd']

        stu_skill = StudentSkill.objects.create(
            student=profile,
            skill=skill,
            level=SkillLevel.INTERMEDIATE,
            status=StudentSkillStatus.VERIFIED,
            verified_by=faculty,
        )

        # Student edits level from 2 to 3
        stu_skill.level = SkillLevel.ADVANCED
        stu_skill.save()

        stu_skill.refresh_from_db()
        assert stu_skill.level == SkillLevel.ADVANCED
        # Must reset to unverified!
        assert stu_skill.status == StudentSkillStatus.UNVERIFIED
        assert stu_skill.verified_by is None
        assert stu_skill.rejection_reason == ''

    def test_institutional_isolation_cross_college_verification_denied(self, client, env_setup):
        profile = env_setup['profile']  # IIT Delhi student
        skill = env_setup['skill']
        faculty_iitb = env_setup['faculty_iitb']  # IIT Bombay faculty

        stu_skill = StudentSkill.objects.create(student=profile, skill=skill, level=SkillLevel.INTERMEDIATE)

        # IIT Bombay faculty attempts to verify IIT Delhi student -> 403 Forbidden
        client.force_login(faculty_iitb)
        url = reverse('profiles:approve_skill', kwargs={'pk': stu_skill.pk})
        resp = client.post(url)
        assert resp.status_code == 403

        stu_skill.refresh_from_db()
        assert stu_skill.status == StudentSkillStatus.UNVERIFIED


@pytest.mark.django_db
class TestProjectsAndCertifications:
    def test_projects_and_certifications_crud(self, client):
        inst = Institution.objects.create(name='BITS Pilani', city='Pilani', is_approved=True)
        student = User.objects.create_user(email='bitsian@pilani.bits-pilani.ac.in', password='Password123', role=UserRole.STUDENT, institution=inst)
        profile = StudentProfile.objects.create(user=student, institution=inst, roll_no='2022A7PS001', programme='B.E. CS', batch='2026')

        client.force_login(student)

        # Add project
        resp = client.post(reverse('profiles:project_add'), {
            'title': 'Nuvelle Platform',
            'description': 'Full-stack skill mapping web application in Django',
            'link': 'https://github.com/django/nuvelle',
        })
        assert resp.status_code == 302
        project = Project.objects.get(student=profile, title='Nuvelle Platform')
        assert project.student == profile

        # Add certification
        resp = client.post(reverse('profiles:certification_add'), {
            'name': 'AWS Certified Cloud Practitioner',
            'issuer': 'Amazon Web Services',
            'credential_url': 'https://aws.amazon.com/verify/12345',
        })
        assert resp.status_code == 302
        cert = Certification.objects.get(student=profile, name='AWS Certified Cloud Practitioner')
        assert cert.issuer == 'Amazon Web Services'

        # Delete project
        resp = client.post(reverse('profiles:project_delete', kwargs={'pk': project.pk}))
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=project.pk).exists()
