
from django.core.management import base as management_base
from django.db import transaction

from street_agitation_bot import models
from street_agitation_bot.management.commands import change_region_timezone


class Command(management_base.BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='csv-file with region description')

    def handle(self, *args, **options):
        old_regions_dict = {region.name: region for region in models.Region.objects.all()}
        with transaction.atomic():
            with open(options['file'], 'r') as f:
                for line in f.readlines():
                    tokens = line.rstrip().split('\t')
                    name = tokens[0]
                    chat_id = int(tokens[1])
                    timezone = int(tokens[2])
                    if name in old_regions_dict:
                        old_region = old_regions_dict[name]
                        if old_region.registrations_chat_id != chat_id:
                            old_region.registrations_chat_id = chat_id
                            old_region.save()
                        if old_region.timezone_delta != timezone:
                            change_region_timezone.apply_change(old_region, timezone)
                    else:
                        models.Region(name=name,
                                      registrations_chat_id=chat_id,
                                      timezone_delta=timezone,
                                      is_public=True).save()
