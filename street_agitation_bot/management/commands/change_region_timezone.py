
from django.db.models import F
from django.core.management import base as management_base
from django.db import transaction

from street_agitation_bot import models

from datetime import timedelta


def apply_change(region, new_timezone_delta):
    diff = timedelta(seconds=new_timezone_delta - region.timezone_delta)
    with transaction.atomic():
        models.AgitationEvent.objects.filter(place__region_id=region.id).update(
            start_date=F('start_date') - diff,
            end_date=F('end_date') - diff,
        )
        region.timezone_delta = new_timezone_delta
        region.save()


class Command(management_base.BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--region-name', type=str, help='region name')
        parser.add_argument('--timezone-delta', type=int, help='new value of region.timezone_delta')

    def handle(self, *args, **options):
        region_name = options['region_name']
        region = models.Region.find_by_name(region_name)
        if not region:
            raise ValueError('Unknown region_name')

        new_timezone_delta = options['timezone_delta']
        if region.timezone_delta == new_timezone_delta:
            return

        apply_change(region, new_timezone_delta)
