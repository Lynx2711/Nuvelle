# Nuvelle — Higher-Ed Skill Mapping & Placement Engine

Nuvelle is a full-stack web platform connecting colleges (academia) and companies (industry) around skill mapping, internship opportunities, and placements.

Built with **Python 3.12** and **Django 5.2 LTS**, it delivers dynamic, responsive, and secure user experiences using server-rendered Django MVT, HTMX for reactive partial updates, Chart.js for data visualization, and Bootstrap 5 for UI components.

---

## Features & Core Capabilities

- **Institutional Hierarchy & Role-Based Access**:
  - 5 Distinct Roles: Administrator, Placement Officer, Faculty Mentor, Employer Recruiter, Student Candidate.
  - Multi-college, multi-company architecture with institution and company verification workflows.
  - Custom user authentication with email-based identity, brute-force lockout (5 failed attempts within 15 mins), and email verification.

- **Standardized Skills Taxonomy**:
  - Hierarchical categories and case-insensitive unique skills.
  - Role Profiles with weighted skill matrices (weight 1–5, required level 1–4).
  - Bulk student onboarding via CSV with inline validation and downloadable error reports.

- **Verified Student Profiles & Faculty Queue**:
  - Student profile completion tracker, resume upload (strictly validated PDFs <= 2 MB), and academic history.
  - Faculty verification queue: approve, reject, or adjust claimed skill levels (1–4) with automatic audit reset on level edits.

- **Opportunities & Multi-Criteria Matching**:
  - Full-time, internship, and contract postings with CGPA cutoffs, batch year restrictions, and skill requirements.
  - Pure, deterministic skill matching algorithm with weighted proficiency and penalization:
    $$\text{Skill Match Score} = \frac{\sum w_i \times \min(l_{\text{student}}, l_{\text{req}})}{\sum w_i \times l_{\text{req}}} \times 100$$
  - Real-time Chart.js radar charts visualizing candidate skill profiles against job requirements and role profiles.
  - Batch skill gap analysis for placement officers highlighting cohort strengths and top-5 weakest skills.

- **Application Pipeline & Eligibility Enforcement**:
  - Strict eligibility rules: unplaced status, minimum CGPA, eligible batch year, and approved institution.
  - Atomic status workflow: `Applied` $\to$ `Shortlisted` $\to$ `Interview Scheduled` $\to$ `Offered` $\to$ `Accepted`.
  - Recruiter privacy isolation (applicants only viewable for posted jobs).

- **Placement Drives & Reporting**:
  - Multi-round placement drive tracking (Aptitude, Technical, HR) with auto-advancement of candidates.
  - Offer extension and one-click student acceptance (which automatically flags `is_placed=True`).
  - Institutional reporting: branch-wise statistics, recruiter distribution, and PDF report export powered by `xhtml2pdf`.

- **In-App Notification Center & Background Dispatch**:
  - Real-time in-app notifications with unread counts badge across global navbar.
  - Resilient email dispatch service with exponential backoff retry.

---

## Tech Stack

| Component | Technology |
|---|---|
| **Backend** | Python 3.12, Django 5.2 LTS |
| **Database** | SQLite (development / test), PostgreSQL (production) via `django-environ` |
| **Frontend UI** | Bootstrap 5.3, Bootstrap Icons, HTMX 1.9, Chart.js 4.4 (bundled locally) |
| **Static Assets** | WhiteNoise 6.9 |
| **PDF Generation**| xhtml2pdf 0.2.17 |
| **Testing** | pytest, pytest-django 4.10, pytest-cov 7.1 |
| **Code Quality** | Ruff 0.8.2 |
| **WSGI Server** | Gunicorn 23.0 |

---

## Directory Structure

```
Nuvelle/
├── accounts/         # User model, authentication, password reset, role dashboards
├── applications/     # Application workflow, eligibility engine, status audit log
├── drives/           # Placement drives, interview rounds, offers, placement tracking
├── matching/         # Skill matching engine, gap reports, cohort radar visualizations
├── notifications/    # In-app notifications, retry email service, context processors
├── opportunities/    # Job postings, skill requirements, auto-closing engine
├── orgs/             # Institution and Company approval workflows, officer student imports
├── profiles/         # Student profiles, projects, certifications, faculty verification queue
├── reports/          # Placement reports, CSV export, xhtml2pdf PDF generation
├── skills/           # Skill categories, skills taxonomy, industry role profiles
├── nuvelle/          # Django project configuration (split settings: base, dev, prod)
├── static/           # Static CSS, JS, vendor libs (Bootstrap, HTMX, Chart.js)
├── templates/        # Server-rendered Django HTML templates
├── tests/            # Integration and end-to-end test suites
├── build.sh          # Deployment build script for PaaS (Render, Railway)
├── Procfile          # Process definition for Gunicorn
├── requirements.txt  # Pinned dependencies
└── runtime.txt       # Python runtime version
```

---

## Local Setup & Quickstart

### 1. Prerequisites
- Python 3.12+ installed
- Git installed

### 2. Clone and Setup Environment
```bash
git clone https://github.com/your-username/nuvelle.git
cd nuvelle

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
# Windows:
copy .env.example .env
# Linux/macOS:
cp .env.example .env
```

### 4. Database Migrations
```bash
python manage.py migrate
```

### 5. Seed Demo Database
Populate the database with complete mock data (60 standard skills across 6 categories, 3 role profiles, 1 institution, 2 companies, 30 students, 10 opportunities, applications, and placement drives):
```bash
python manage.py seed_demo
```

### 6. Run Development Server
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000` in your browser.

---

## Demo Accounts

The `seed_demo` command automatically creates five pre-configured role accounts:

| Role | Email | Password | Access Highlights |
|---|---|---|---|
| **Administrator** | `admin@nuvelle.edu` | `AdminPass123` | System-wide statistics, institution/company approval, user management |
| **Placement Officer**| `officer@nitt.edu` | `OfficerPass123` | Batch skill gap maps, drive scheduling, student CSV import, cohort placement reports |
| **Faculty Mentor** | `faculty@nitt.edu` | `FacultyPass123` | Student skill verification queue, skill level adjustments, student project inspection |
| **Employer Recruiter**| `recruiter@acme.com` | `RecruiterPass123` | Opportunity posting, applicant skill matching, interview rounds, offer extension |
| **Student Candidate**| `student@nitt.edu` | `StudentPass123` | Profile completion, skill claims, job searching with live match scores, offer acceptance |

---

## Testing & Quality Assurance

### Run Unit & Integration Tests
```bash
pytest
```

### Run Test Coverage Report
Nuvelle enforces high test coverage across core calculation and workflow packages:
```bash
pytest --cov=accounts --cov=applications --cov=matching --cov-report=term-missing
```
*(Currently at **86% coverage**, exceeding the 70% threshold)*.

### Linting
```bash
ruff check .
```

---

## Deployment (Render, Railway, Heroku)

Nuvelle is configured out-of-the-box for 12-factor cloud deployment:

1. **Gunicorn WSGI**: Declared in `Procfile` (`web: gunicorn nuvelle.wsgi:application --log-file -`).
2. **Build Automation**: `build.sh` automates dependency installation, `collectstatic`, and database migrations.
3. **Static File Serving**: Handled by WhiteNoise (`CompressedManifestStaticFilesStorage`).
4. **Environment Variables**:
   - `DJANGO_SETTINGS_MODULE=nuvelle.settings.prod`
   - `SECRET_KEY=<strong-random-key>`
   - `ALLOWED_HOSTS=your-app.onrender.com,your-custom-domain.com`
   - `DATABASE_URL=postgres://user:password@host:port/dbname`
   - `SITE_URL=https://your-app.onrender.com`
   - `SECURE_SSL_REDIRECT=True`
