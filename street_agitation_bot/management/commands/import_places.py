
from django.core.management import base as management_base
from django.db import transaction

from street_agitation_bot import models


class Command(management_base.BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--region-name', type=str, help='region name')
        parser.add_argument('--file', type=str, help='file with place description')

    def handle(self, *args, **options):
        region_name = options['region_name']
        region = models.Region.find_by_name(region_name)
        if not region:
            raise ValueError('Unknown region_name')

        new_places_dict = dict()
        new_places_list = list()
        hierarchies = list()
        with open(options['file'], 'r') as f:
            prev_offset = -1
            place_stack = []
            cur_order = 0
            for line in f.readlines():
                line = line.rstrip()
                cur_offset = 0
                while line[cur_offset] == ' ':
                    cur_offset += 1
                line = line[cur_offset:]
                cur_offset /= 2
                while cur_offset <= prev_offset:
                    place_stack.pop()
                    prev_offset -= 1
                cur_place = new_places_dict.get(line, models.AgitationPlace(region=region, address=line))
                if place_stack:
                    hierarchies.append(models.AgitationPlaceHierarchy(base_place=place_stack[-1],
                                                                      sub_place=cur_place,
                                                                      order=cur_order))
                    cur_order += 1
                new_places_list.append(cur_place)
                new_places_dict[line] = cur_place
                place_stack.append(cur_place)
                prev_offset = cur_offset

        with transaction.atomic():
            for place in new_places_list:
                place.save()
            for h in hierarchies:
                h.base_place_id = h.base_place.pk
                h.sub_place_id = h.sub_place.pk
                h.save()
