from time import sleep
import json
import socket
import re
import urllib.request
import urllib.parse

from django.core.management import base as management_base

from street_agitation_bot import models, bot_settings


class TelegramClient:
    def __init__(self, hostname, port):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((hostname, port))

    def make_request(self, request):
        self.socket.send(str.encode(request + '\n'))
        response = self.socket.recv(2048).decode()
        match = re.match('ANSWER (\d+)\n(.*)', response)
        if bool(match):
            return json.loads(match.group(2))
        return None


def create_region_chat(telegram_client, region, admin_usernames, chat_num):
    bot_name = telegram_client.make_request("resolve_username %s" % bot_settings.BOT_USERNAME)["print_name"]
    admin_names = [telegram_client.make_request("resolve_username " + username)["print_name"] for username in admin_usernames]

    chat_name = 'Кубы %s. Регистрации' % region.name
    telegram_client.make_request("create_group_chat '%s' %s %s" % (chat_name, bot_name, ' '.join(admin_names)))
    chat_name = chat_name.replace(' ', '_')  # convert to 'print_name'
    telegram_client.make_request("chat_upgrade %s" % chat_name)
    chat_name += '#1'  # upgraded chat is a new chat with this name
    telegram_client.make_request("msg %s '/set_region_chat@%s %d %s'"
                                 % (chat_name, bot_settings.BOT_USERNAME, chat_num, region.name))
    for i in range(100):
        sleep(0.05)
        region.refresh_from_db()
        if region.registrations_chat_id:
            break
    if not region.registrations_chat_id:
        raise ValueError("chat is not created for '%s' :(" % region.name)
    for admin_name in admin_names:
        telegram_client.make_request("channel_invite %s %s" % (chat_name, admin_name))


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
        telegram_client = TelegramClient("localhost", options['telegram_cli_port'])
        all_regions = {region.name: region for region in models.Region.objects.all()}
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
                                           timezone_delta=timezone,
                                           is_public=False)
                    region.save()
                    all_regions[region_name] = region
                if not region.registrations_chat_id:
                    create_region_chat(telegram_client, region, [super_admin_username, admin_username], 0)
