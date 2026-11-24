from django.core.management.base import BaseCommand
from django.utils import timezone

from opportunities.models import Opportunity, OpportunityStatus


class Command(BaseCommand):
    help = 'Auto-closes published opportunities whose application deadlines have passed.'

    def handle(self, *args, **options):
        now = timezone.now()
        expired = Opportunity.objects.filter(
            status=OpportunityStatus.PUBLISHED,
            deadline__lt=now,
        )
        count = expired.count()
        if count > 0:
            updated = expired.update(
                status=OpportunityStatus.CLOSED,
                updated_at=now,
            )
            self.stdout.write(self.style.SUCCESS(f"Successfully auto-closed {updated} expired opportunity/ies."))
        else:
            self.stdout.write("No expired opportunities to close.")
