import csv
import io
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Max
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from drives.models import Offer, OfferStatus
from profiles.models import StudentProfile


def get_placement_statistics(
    institution=None,
    batch: str | None = None,
    programme: str | None = None,
) -> dict[str, Any]:
    """
    Computes placement statistics:
    - Overall placement rate, placed students, total cohort size
    - Salary packages (Highest, Average)
    - Statistics by Department/Programme
    - Statistics by Company
    - Statistics by Batch/Year
    """
    students_qs = StudentProfile.objects.all()
    accepted_offers_qs = Offer.objects.filter(status=OfferStatus.ACCEPTED)

    if institution:
        students_qs = students_qs.filter(institution=institution)
        accepted_offers_qs = accepted_offers_qs.filter(application__student__institution=institution)

    if batch:
        students_qs = students_qs.filter(batch__iexact=batch.strip())
        accepted_offers_qs = accepted_offers_qs.filter(application__student__batch__iexact=batch.strip())

    if programme:
        students_qs = students_qs.filter(programme__icontains=programme.strip())
        accepted_offers_qs = accepted_offers_qs.filter(application__student__programme__icontains=programme.strip())

    total_students = students_qs.count()
    placed_students = students_qs.filter(is_placed=True).count()
    placement_rate = round((placed_students / total_students * 100), 1) if total_students > 0 else 0.0

    total_offers = accepted_offers_qs.count()
    pkg_aggregates = accepted_offers_qs.aggregate(
        max_pkg=Max('package'),
        avg_pkg=Avg('package'),
    )
    highest_package = pkg_aggregates['max_pkg'] or Decimal('0.00')
    average_package = round(pkg_aggregates['avg_pkg'] or Decimal('0.00'), 2)

    # 1. Statistics by Department / Programme
    departments_data = []
    distinct_programmes = students_qs.values_list('programme', flat=True).distinct().order_by('programme')
    for prog in distinct_programmes:
        if not prog:
            continue
        p_students = students_qs.filter(programme=prog)
        p_total = p_students.count()
        p_placed = p_students.filter(is_placed=True).count()
        p_rate = round((p_placed / p_total * 100), 1) if p_total > 0 else 0.0

        p_offers = accepted_offers_qs.filter(application__student__programme=prog)
        p_agg = p_offers.aggregate(max_pkg=Max('package'), avg_pkg=Avg('package'))

        departments_data.append({
            'programme': prog,
            'total_students': p_total,
            'placed_students': p_placed,
            'placement_rate': p_rate,
            'highest_package': p_agg['max_pkg'] or Decimal('0.00'),
            'average_package': round(p_agg['avg_pkg'] or Decimal('0.00'), 2),
            'offers_count': p_offers.count(),
        })

    # 2. Statistics by Company
    companies_agg = (
        accepted_offers_qs.values('application__opportunity__company__name')
        .annotate(
            offers_count=Count('id'),
            highest_package=Max('package'),
            average_package=Avg('package'),
        )
        .order_by('-offers_count', '-highest_package')
    )

    companies_data = []
    for c in companies_agg:
        companies_data.append({
            'company_name': c['application__opportunity__company__name'] or 'Unknown Company',
            'offers_count': c['offers_count'],
            'highest_package': c['highest_package'] or Decimal('0.00'),
            'average_package': round(c['average_package'] or Decimal('0.00'), 2),
        })

    # 3. Statistics by Batch / Year
    batches_data = []
    distinct_batches = students_qs.values_list('batch', flat=True).distinct().order_by('-batch')
    for b in distinct_batches:
        if not b:
            continue
        b_students = students_qs.filter(batch=b)
        b_total = b_students.count()
        b_placed = b_students.filter(is_placed=True).count()
        b_rate = round((b_placed / b_total * 100), 1) if b_total > 0 else 0.0
        batches_data.append({
            'batch': b,
            'total_students': b_total,
            'placed_students': b_placed,
            'placement_rate': b_rate,
        })

    return {
        'institution': institution,
        'selected_batch': batch,
        'selected_programme': programme,
        'total_students': total_students,
        'placed_students': placed_students,
        'placement_rate': placement_rate,
        'total_offers': total_offers,
        'highest_package': highest_package,
        'average_package': average_package,
        'departments_data': departments_data,
        'companies_data': companies_data,
        'batches_data': batches_data,
        'generated_at': timezone.now(),
    }


def export_placement_report_csv(stats: dict[str, Any]) -> HttpResponse:
    """Exports structured placement statistics to CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="placement_statistics_report.csv"'
    writer = csv.writer(response)

    # Summary
    writer.writerow(['NUVELLE PLACEMENT & RECRUITMENT REPORT'])
    writer.writerow(['Institution', stats['institution'].name if stats.get('institution') else 'All Partner Institutions'])
    writer.writerow(['Total Cohort Evaluated', stats['total_students']])
    writer.writerow(['Total Placed Students', stats['placed_students']])
    writer.writerow(['Overall Placement Rate (%)', stats['placement_rate']])
    writer.writerow(['Highest Package (INR)', stats['highest_package']])
    writer.writerow(['Average Package (INR)', stats['average_package']])
    writer.writerow([])

    # Department Breakdown
    writer.writerow(['--- DEPARTMENT / PROGRAMME BREAKDOWN ---'])
    writer.writerow(['Department / Programme', 'Total Students', 'Placed Students', 'Placement Rate (%)', 'Highest Package (INR)', 'Average Package (INR)', 'Offers Count'])
    for d in stats['departments_data']:
        writer.writerow([
            d['programme'],
            d['total_students'],
            d['placed_students'],
            d['placement_rate'],
            d['highest_package'],
            d['average_package'],
            d['offers_count'],
        ])
    writer.writerow([])

    # Company Breakdown
    writer.writerow(['--- RECRUITING COMPANIES BREAKDOWN ---'])
    writer.writerow(['Company Name', 'Offers Count', 'Highest Package (INR)', 'Average Package (INR)'])
    for c in stats['companies_data']:
        writer.writerow([
            c['company_name'],
            c['offers_count'],
            c['highest_package'],
            c['average_package'],
        ])
    writer.writerow([])

    # Batch Breakdown
    writer.writerow(['--- BATCH / YEAR BREAKDOWN ---'])
    writer.writerow(['Batch Year', 'Total Students', 'Placed Students', 'Placement Rate (%)'])
    for b in stats['batches_data']:
        writer.writerow([
            b['batch'],
            b['total_students'],
            b['placed_students'],
            b['placement_rate'],
        ])

    return response


def export_placement_report_pdf(stats: dict[str, Any]) -> HttpResponse:
    """
    Renders an HTML template into a PDF using xhtml2pdf.
    """
    html_string = render_to_string('reports/placement_report_pdf.html', {'stats': stats})
    pdf_buffer = io.BytesIO()

    pisa_status = pisa.CreatePDF(
        src=html_string,
        dest=pdf_buffer,
        encoding='utf-8',
    )

    if pisa_status.err:
        return HttpResponse("Error generating PDF report.", status=500)

    pdf_buffer.seek(0)
    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="placement_report.pdf"'
    return response
