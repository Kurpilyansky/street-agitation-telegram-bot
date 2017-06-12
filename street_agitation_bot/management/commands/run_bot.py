
from django.core.management import base as management_base

from street_agitation_bot import bot


class Command(management_base.BaseCommand):
    def handle(self, *args, **options):
        bot.run_bot()
