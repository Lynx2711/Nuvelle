import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User, UserRole
from applications.models import Application, ApplicationStatus, StatusLog
from drives.models import DriveRound, DriveStatus, Offer, OfferStatus, PlacementDrive
from matching.services import calculate_skill_match_score
from opportunities.models import (
    Opportunity,
    OpportunityMode,
    OpportunitySkill,
    OpportunityStatus,
    OpportunityType,
)
from orgs.models import Company, Institution
from profiles.models import Certification, Project, StudentProfile, StudentSkill, StudentSkillStatus
from skills.models import RoleProfile, RoleSkill, Skill, SkillCategory, SkillLevel


class Command(BaseCommand):
    help = "Seeds database with demo data: 60 skills, 3 role profiles, 1 institution, 2 companies, 30 students, 10 opportunities, and 5 documented users."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Nuvelle database demo seed..."))

        with transaction.atomic():
            # 1. Partner Institution
            inst, _ = Institution.objects.get_or_create(
                name="National Institute of Technology, Trichy",
                defaults={'city': 'Tiruchirappalli', 'is_approved': True},
            )
            self.stdout.write(self.style.SUCCESS(f" [1/7] Institution: {inst.name}"))

            # 2. Approved Companies
            c1, _ = Company.objects.get_or_create(
                name="Acme Technologies",
                defaults={
                    'industry': 'Enterprise Cloud & AI',
                    'website': 'https://acme.tech',
                    'is_approved': True,
                },
            )
            c2, _ = Company.objects.get_or_create(
                name="Stripe India",
                defaults={
                    'industry': 'Fintech & Payment Infrastructure',
                    'website': 'https://stripe.com',
                    'is_approved': True,
                },
            )
            self.stdout.write(self.style.SUCCESS(" [2/7] Partner Companies: Acme Technologies, Stripe India"))

            # 3. Documented Role Users (One per role)
            dev_passwords = {
                'admin@nuvelle.edu': ('AdminPass123', UserRole.ADMIN, None, None, True),
                'officer@nitt.edu': ('OfficerPass123', UserRole.OFFICER, inst, None, False),
                'faculty@nitt.edu': ('FacultyPass123', UserRole.FACULTY, inst, None, False),
                'recruiter@acme.com': ('RecruiterPass123', UserRole.RECRUITER, None, c1, False),
                'student@nitt.edu': ('StudentPass123', UserRole.STUDENT, inst, None, False),
            }

            created_users = {}
            for email, (pwd, role, user_inst, user_comp, is_super) in dev_passwords.items():
                u, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'role': role,
                        'institution': user_inst,
                        'company': user_comp,
                        'is_verified': True,
                        'is_staff': is_super,
                        'is_superuser': is_super,
                    },
                )
                u.set_password(pwd)
                u.is_verified = True
                u.save()
                created_users[role] = u

            # Primary student profile
            p_primary, _ = StudentProfile.objects.get_or_create(
                user=created_users[UserRole.STUDENT],
                defaults={
                    'institution': inst,
                    'roll_no': 'CS2025_001',
                    'programme': 'Computer Science',
                    'batch': '2025',
                    'cgpa': Decimal('8.95'),
                    'graduation_year': 2025,
                },
            )
            self.stdout.write(self.style.SUCCESS(" [3/7] Created 5 documented role accounts with default passwords."))

            # 4. Sixty Skills Across 6 Standard Taxonomy Categories
            taxonomy = {
                'Backend & Systems': [
                    'Python', 'Django', 'FastAPI', 'Go', 'Rust',
                    'Java', 'Spring Boot', 'C++', 'Node.js', 'REST APIs',
                ],
                'Frontend & Mobile': [
                    'HTML5', 'CSS3', 'JavaScript', 'TypeScript', 'React',
                    'Vue.js', 'Next.js', 'Bootstrap', 'Flutter', 'Tailwind CSS',
                ],
                'Databases & Storage': [
                    'PostgreSQL', 'MySQL', 'Redis', 'MongoDB', 'SQLite',
                    'Cassandra', 'Elasticsearch', 'DynamoDB', 'Neo4j', 'GraphQL',
                ],
                'Cloud & DevOps': [
                    'Docker', 'Kubernetes', 'AWS', 'Google Cloud', 'Azure',
                    'Linux', 'Terraform', 'CI/CD Pipelines', 'Git', 'Nginx',
                ],
                'AI & Data Science': [
                    'Machine Learning', 'Deep Learning', 'PyTorch', 'TensorFlow', 'Pandas',
                    'NumPy', 'Scikit-learn', 'SQL Analytics', 'Computer Vision', 'Natural Language Processing',
                ],
                'Computer Science & Quality': [
                    'Data Structures & Algorithms', 'Object-Oriented Design', 'Operating Systems',
                    'Computer Networks', 'System Design', 'Cybersecurity', 'Cryptography',
                    'Agile Methodology', 'Unit Testing', 'Microservices Architecture',
                ],
            }

            all_skills = []
            for cat_name, skill_names in taxonomy.items():
                cat, _ = SkillCategory.objects.get_or_create(name=cat_name)
                for s_name in skill_names:
                    sk, _ = Skill.objects.get_or_create(category=cat, name=s_name, defaults={'is_active': True})
                    all_skills.append(sk)
            self.stdout.write(self.style.SUCCESS(f" [4/7] Skills Taxonomy: {len(all_skills)} standard skills in 6 categories."))

            # 5. Three Role Profiles with Benchmarks
            role_definitions = [
                (
                    'Junior Backend Engineer',
                    'Designs and builds microservices, REST APIs, and database schemas.',
                    [
                        ('Python', 3, 5),
                        ('Django', 2, 4),
                        ('PostgreSQL', 2, 4),
                        ('Docker', 2, 3),
                        ('Git', 2, 3),
                        ('Data Structures & Algorithms', 3, 5),
                    ],
                ),
                (
                    'Full Stack Web Developer',
                    'Develops end-to-end web applications with modern frontend frameworks and relational backends.',
                    [
                        ('JavaScript', 3, 5),
                        ('React', 3, 5),
                        ('HTML5', 3, 3),
                        ('CSS3', 3, 3),
                        ('Python', 2, 4),
                        ('Django', 2, 4),
                        ('PostgreSQL', 2, 4),
                        ('Git', 2, 3),
                    ],
                ),
                (
                    'Data Scientist / ML Engineer',
                    'Extracts predictive insights and deploys statistical and deep learning models.',
                    [
                        ('Python', 4, 5),
                        ('Machine Learning', 3, 5),
                        ('Pandas', 3, 4),
                        ('NumPy', 3, 4),
                        ('PyTorch', 2, 4),
                        ('SQL Analytics', 3, 4),
                        ('Data Structures & Algorithms', 3, 3),
                    ],
                ),
            ]

            skill_lookup = {s.name: s for s in all_skills}
            for role_name, desc, reqs in role_definitions:
                rp, _ = RoleProfile.objects.get_or_create(name=role_name, defaults={'description': desc})
                for s_name, lvl, wt in reqs:
                    if s_name in skill_lookup:
                        RoleSkill.objects.get_or_create(
                            role=rp,
                            skill=skill_lookup[s_name],
                            defaults={'required_level': lvl, 'weight': wt},
                        )
            self.stdout.write(self.style.SUCCESS(" [5/7] Created 3 standard Role Profiles with weighted skills."))

            # 6. Thirty Students with Varied Skills, Projects, and Certifications
            programmes = ['Computer Science', 'Information Technology', 'Electronics & Communication', 'Electrical Engineering']
            batches = ['2025', '2026']

            students = [p_primary]
            for i in range(2, 31):
                email = f"student{i:02d}@nitt.edu"
                roll_no = f"NITT_{2025 if i % 2 == 1 else 2026}_{i:03d}"
                u, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'role': UserRole.STUDENT,
                        'institution': inst,
                        'is_verified': True,
                    },
                )
                u.set_password('StudentPass123')
                u.is_verified = True
                u.save()

                cgpa = Decimal(str(round(random.uniform(6.5, 9.8), 2)))
                sp, _ = StudentProfile.objects.get_or_create(
                    user=u,
                    defaults={
                        'institution': inst,
                        'roll_no': roll_no,
                        'programme': random.choice(programmes),
                        'batch': random.choice(batches),
                        'cgpa': cgpa,
                        'graduation_year': 2025 if '2025' in roll_no else 2026,
                    },
                )

                # Assign 5-8 random skills
                chosen_skills = random.sample(all_skills, k=random.randint(5, 9))
                for sk in chosen_skills:
                    level = random.choice([SkillLevel.BEGINNER, SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED, SkillLevel.EXPERT])
                    status = random.choice([StudentSkillStatus.VERIFIED, StudentSkillStatus.UNVERIFIED, StudentSkillStatus.VERIFIED])
                    StudentSkill.objects.get_or_create(
                        student=sp,
                        skill=sk,
                        defaults={
                            'level': level,
                            'status': status,
                            'verified_by': created_users[UserRole.FACULTY] if status == StudentSkillStatus.VERIFIED else None,
                        },
                    )

                # Add a project
                Project.objects.get_or_create(
                    student=sp,
                    title=f"Distributed {chosen_skills[0].name} System",
                    defaults={
                        'description': 'Engineered a scalable microservice with concurrent caching and high availability.',
                        'link': 'https://github.com/example/demo-project',
                    },
                )

                # Add a certification
                if i % 3 == 0:
                    Certification.objects.get_or_create(
                        student=sp,
                        name=f"Certified {chosen_skills[1].name} Specialist",
                        defaults={
                            'issuer': 'Global Tech Council',
                            'issued_on': timezone.now().date() - timedelta(days=60),
                            'is_verified': True,
                        },
                    )

                students.append(sp)
            self.stdout.write(self.style.SUCCESS(f" [6/7] Seeded {len(students)} students with claimed skills, projects, and CGPAs."))

            # 7. Ten Opportunities (5 Acme, 5 Stripe) + Drives + Applications
            opp_definitions = [
                # Acme Technologies
                (c1, 'Cloud Backend Intern', OpportunityType.INTERNSHIP, OpportunityMode.HYBRID, 'Bengaluru', 30000, 45000, 3, 7.5, 'Computer Science', '2025', [('Python', 3, 5), ('Django', 2, 4), ('Docker', 2, 3), ('PostgreSQL', 2, 4)]),
                (c1, 'Software Engineer - Distributed Systems', OpportunityType.JOB, OpportunityMode.ON_SITE, 'Hyderabad', 1400000, 1800000, 2, 8.0, 'Computer Science', '2025', [('Go', 3, 5), ('Kubernetes', 2, 4), ('PostgreSQL', 3, 4), ('System Design', 3, 5)]),
                (c1, 'Full Stack Web Intern', OpportunityType.INTERNSHIP, OpportunityMode.REMOTE, 'Remote', 25000, 35000, 4, 7.0, '', '2025', [('JavaScript', 3, 5), ('React', 3, 5), ('HTML5', 2, 3), ('Node.js', 2, 4)]),
                (c1, 'Site Reliability Engineer', OpportunityType.JOB, OpportunityMode.HYBRID, 'Pune', 1200000, 1600000, 1, 7.5, '', '2025', [('Linux', 3, 5), ('Docker', 3, 4), ('Terraform', 2, 4), ('CI/CD Pipelines', 3, 4)]),
                (c1, 'Machine Learning Research Intern', OpportunityType.INTERNSHIP, OpportunityMode.ON_SITE, 'Bengaluru', 40000, 60000, 2, 8.5, 'Computer Science', '2026', [('Python', 4, 5), ('PyTorch', 3, 5), ('Pandas', 3, 4), ('Machine Learning', 3, 5)]),

                # Stripe India
                (c2, 'Payment Platform Engineer', OpportunityType.JOB, OpportunityMode.ON_SITE, 'Bengaluru', 2200000, 3000000, 2, 8.5, 'Computer Science', '2025', [('Java', 3, 5), ('Spring Boot', 3, 4), ('PostgreSQL', 3, 5), ('Microservices Architecture', 3, 5)]),
                (c2, 'Frontend Infrastructure Engineer', OpportunityType.JOB, OpportunityMode.HYBRID, 'Bengaluru', 1800000, 2400000, 2, 7.8, '', '2025', [('TypeScript', 3, 5), ('React', 3, 5), ('Next.js', 2, 4), ('Unit Testing', 3, 4)]),
                (c2, 'Data Analytics Intern', OpportunityType.INTERNSHIP, OpportunityMode.HYBRID, 'Mumbai', 35000, 50000, 3, 7.5, '', '2025', [('SQL Analytics', 3, 5), ('Python', 3, 4), ('Pandas', 3, 4), ('PostgreSQL', 2, 4)]),
                (c2, 'Security Operations Specialist', OpportunityType.JOB, OpportunityMode.ON_SITE, 'Bengaluru', 1600000, 2200000, 1, 8.0, '', '2025', [('Cybersecurity', 3, 5), ('Operating Systems', 3, 4), ('Computer Networks', 3, 4), ('Linux', 3, 4)]),
                (c2, 'Backend Infrastructure Intern', OpportunityType.INTERNSHIP, OpportunityMode.REMOTE, 'Remote', 35000, 45000, 2, 7.0, '', '2026', [('Python', 3, 5), ('FastAPI', 2, 4), ('Docker', 2, 3), ('Redis', 2, 4)]),
            ]

            opportunities = []
            for comp, title, o_type, mode, loc, p_min, p_max, openings, min_cgpa, prog, batch, req_skills in opp_definitions:
                opp, _ = Opportunity.objects.get_or_create(
                    company=comp,
                    title=title,
                    defaults={
                        'type': o_type,
                        'mode': mode,
                        'location': loc,
                        'pay_min': p_min,
                        'pay_max': p_max,
                        'openings': openings,
                        'min_cgpa': Decimal(str(min_cgpa)) if min_cgpa else None,
                        'programme': prog,
                        'batch': batch,
                        'deadline': timezone.now() + timedelta(days=20),
                        'status': OpportunityStatus.PUBLISHED,
                    },
                )
                for s_name, lvl, wt in req_skills:
                    if s_name in skill_lookup:
                        OpportunitySkill.objects.get_or_create(
                            opportunity=opp,
                            skill=skill_lookup[s_name],
                            defaults={'required_level': lvl, 'weight': wt},
                        )
                opportunities.append(opp)
            self.stdout.write(self.style.SUCCESS(f" [7/7] Created {len(opportunities)} published opportunities (Acme & Stripe)."))

            # Seed placement drives, applications and offers
            drive1, _ = PlacementDrive.objects.get_or_create(
                opportunity=opportunities[0],
                institution=inst,
                drive_date=timezone.now().date() + timedelta(days=7),
                defaults={
                    'venue': 'CSE Seminar Hall & Virtual Interview Links',
                    'rules': 'Dress code: Formal attire. Keep original marksheets handy.',
                    'status': DriveStatus.SCHEDULED,
                },
            )
            DriveRound.objects.get_or_create(drive=drive1, name='Online Coding Assessment', defaults={'sequence': 1, 'round_date': drive1.drive_date})
            DriveRound.objects.get_or_create(drive=drive1, name='System Technical Interview', defaults={'sequence': 2, 'round_date': drive1.drive_date + timedelta(days=1)})

            # Submit applications for students
            for idx, stu in enumerate(students[:20]):
                target_opp = opportunities[idx % len(opportunities)]
                stu_skills = {ss.skill_id: ss.level for ss in stu.skills.all()}
                req_list = [{'skill_id': rs.skill_id, 'required_level': rs.required_level, 'weight': rs.weight} for rs in target_opp.required_skills.all()]
                score = calculate_skill_match_score(stu_skills, req_list)

                app, _ = Application.objects.get_or_create(
                    student=stu,
                    opportunity=target_opp,
                    defaults={
                        'status': ApplicationStatus.APPLIED,
                        'match_score_at_apply': score,
                    },
                )
                StatusLog.objects.get_or_create(
                    application=app,
                    new_status=app.status,
                    defaults={'old_status': '', 'changed_by': stu.user},
                )

                # Extend offers to some top scoring students
                if idx in [0, 1, 2, 3, 5]:
                    app.status = ApplicationStatus.ACCEPTED
                    app.save(update_fields=['status'])
                    pkg = Decimal('1400000.00') if target_opp.type == OpportunityType.JOB else Decimal('450000.00')
                    Offer.objects.get_or_create(
                        application=app,
                        defaults={
                            'package': pkg,
                            'status': OfferStatus.ACCEPTED,
                            'notes': 'Joining letter issued.',
                        },
                    )
                    stu.is_placed = True
                    stu.save(update_fields=['is_placed'])

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 65))
        self.stdout.write(self.style.SUCCESS("  NUVELLE DEMO DATABASE SEEDED SUCCESSFULLY!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write("Documented Dev Credentials (All passwords: '<Role>Pass123'):")
        self.stdout.write("  - Administrator:     admin@nuvelle.edu       (AdminPass123)")
        self.stdout.write("  - Placement Officer: officer@nitt.edu        (OfficerPass123)")
        self.stdout.write("  - Faculty Mentor:    faculty@nitt.edu        (FacultyPass123)")
        self.stdout.write("  - Employer Recruiter:recruiter@acme.com      (RecruiterPass123)")
        self.stdout.write("  - Student Candidate: student@nitt.edu        (StudentPass123)")
        self.stdout.write("=" * 65 + "\n")
