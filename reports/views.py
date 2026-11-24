import json

from django.views import View
from django.views.generic import TemplateView

from accounts.models import UserRole
from accounts.permissions import RoleRequiredMixin

from .services import (
    export_placement_report_csv,
    export_placement_report_pdf,
    get_placement_statistics,
)


class PlacementStatisticsView(RoleRequiredMixin, TemplateView):
    allowed_roles = [UserRole.OFFICER, UserRole.FACULTY, UserRole.RECRUITER, UserRole.ADMIN]
    template_name = 'reports/placement_statistics.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        institution = user.institution if user.role in [UserRole.OFFICER, UserRole.FACULTY] else None

        batch = self.request.GET.get('batch', '').strip()
        programme = self.request.GET.get('programme', '').strip()

        stats = get_placement_statistics(
            institution=institution,
            batch=batch or None,
            programme=programme or None,
        )
        ctx['stats'] = stats

        # Chart.js Data: Department placement rates
        dept_labels = [d['programme'] for d in stats['departments_data']]
        dept_rates = [d['placement_rate'] for d in stats['departments_data']]
        dept_placed = [d['placed_students'] for d in stats['departments_data']]
        dept_total = [d['total_students'] for d in stats['departments_data']]

        ctx['chart_dept_labels_json'] = json.dumps(dept_labels)
        ctx['chart_dept_rates_json'] = json.dumps(dept_rates)
        ctx['chart_dept_placed_json'] = json.dumps(dept_placed)
        ctx['chart_dept_total_json'] = json.dumps(dept_total)

        # Chart.js Data: Company offers
        company_labels = [c['company_name'] for c in stats['companies_data'][:10]]
        company_offers = [c['offers_count'] for c in stats['companies_data'][:10]]
        company_avg_pkg = [float(c['average_package']) for c in stats['companies_data'][:10]]

        ctx['chart_company_labels_json'] = json.dumps(company_labels)
        ctx['chart_company_offers_json'] = json.dumps(company_offers)
        ctx['chart_company_pkg_json'] = json.dumps(company_avg_pkg)

        return ctx


class ExportPlacementReportPdfView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.OFFICER, UserRole.FACULTY, UserRole.RECRUITER, UserRole.ADMIN]

    def get(self, request):
        user = request.user
        institution = user.institution if user.role in [UserRole.OFFICER, UserRole.FACULTY] else None
        batch = request.GET.get('batch', '').strip()
        programme = request.GET.get('programme', '').strip()

        stats = get_placement_statistics(
            institution=institution,
            batch=batch or None,
            programme=programme or None,
        )
        return export_placement_report_pdf(stats)


class ExportPlacementReportCsvView(RoleRequiredMixin, View):
    allowed_roles = [UserRole.OFFICER, UserRole.FACULTY, UserRole.RECRUITER, UserRole.ADMIN]

    def get(self, request):
        user = request.user
        institution = user.institution if user.role in [UserRole.OFFICER, UserRole.FACULTY] else None
        batch = request.GET.get('batch', '').strip()
        programme = request.GET.get('programme', '').strip()

        stats = get_placement_statistics(
            institution=institution,
            batch=batch or None,
            programme=programme or None,
        )
        return export_placement_report_csv(stats)
