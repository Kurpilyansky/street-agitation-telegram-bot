from time import sleep
import re
import urllib.request
import urllib.parse

from django.core.management import base as management_base

from street_agitation_bot import models, bot_settings

import telegram_client


def create_region_chat(client, region, admin_usernames, chat_num):
    bot_name = client.make_request("resolve_username %s" % bot_settings.BOT_USERNAME)["print_name"]
    admin_names = [client.make_request("resolve_username " + username)["print_name"] for username in admin_usernames]

    chat_name = 'Кубы %s. Регистрации' % region.name
    client.make_request("create_group_chat '%s' %s %s" % (chat_name, bot_name, ' '.join(admin_names)))
    chat_name = chat_name.replace(' ', '_')  # convert to 'print_name'
    client.make_request("chat_upgrade %s" % chat_name)
    chat_name += '#1'  # upgraded chat is a new chat with this name
    client.make_request("msg %s '/set_region_chat@%s %d %s'"
                        % (chat_name, bot_settings.BOT_USERNAME, chat_num, region.name))
    for i in range(100):
        sleep(0.05)
        region.refresh_from_db()
        if region.registrations_chat_id:
            break
    if not region.registrations_chat_id:
        raise ValueError("chat is not created for '%s' :(" % region.name)
    for admin_name in admin_names:
        client.make_request("channel_invite %s %s" % (chat_name, admin_name))


def guess_timezone(city_name):
    params = urllib.parse.urlencode({'q': str.encode('время %s' % city_name)})
    url = "https://www.google.com/search?" + params
    req = urllib.request.Request(url)
    req.add_header('User-agent', "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/51.0.2704.103 Safari/537.36")
    content = urllib.request.urlopen(req).read().decode()
    match = re.search('\(GMT([+-]\d+)\)', content)
    return int(match.group(1)) * 3600


class Command(management_base.BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='csv-file with region description')
        parser.add_argument('--super-admin-username', type=str, help='superadmin username')
        parser.add_argument('--telegram-cli-port', type=int, help='telegram-cli port on the localhost')

    def handle(self, *args, **options):
        client = telegram_client.TelegramClient("localhost", options['telegram_cli_port'])
        all_regions = {region.name: region for region in models.Region.objects.select_related('settings').all()}
        super_admin_username = options['super_admin_username']
        with open(options['file'], 'r') as f:
            for line in f.readlines():
                tokens = line.rstrip().split('\t')
                region_name = tokens[0]
                admin_username = tokens[1]
                if region_name in all_regions:
                    region = all_regions[region_name]
                else:
                    timezone = guess_timezone(region_name)
                    region = models.Region(name=region_name,
                                           timezone_delta=timezone)
                    region.save()
                    models.RegionSettings.objects.create(region=region)
                    all_regions[region_name] = region
                admin_user = models.User.update_or_create({'telegram': admin_username})[0]
                if not region.settings.is_public:
                    models.AgitatorInRegion.save_abilities(region.id, admin_user, {})
                if not models.AdminRights.objects.filter(user_id=admin_user.id, region_id=region.id).first():
                    models.AdminRights.objects.create(user_id=admin_user.id,
                                                      region_id=region.id,
                                                      level=models.AdminRights.SUPER_ADMIN_LEVEL)
                if not region.registrations_chat_id:
                    create_region_chat(client, region, [super_admin_username, admin_username], 0)
