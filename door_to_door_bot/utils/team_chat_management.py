import telegram_client as tc

from door_to_door_bot import bot_settings

def create_team_chat(team):
    def create_group_chat(make):
        bot_name = make("resolve_username %s" % bot_settings.BOT_USERNAME)["print_name"]
        make("create_group_chat '%s' %s" % (human_chat_name, bot_name))

    def chat_upgrade(make):
        chat_name = make("dialog_list 1")[0]["print_name"]
        print('chat_print_name = %s' % chat_name)
        return make("chat_upgrade %s" % chat_name)

    def channel_set_admin(make):
        bot_name = make("resolve_username %s" % bot_settings.BOT_USERNAME)["print_name"]
        channel_name = [x["print_name"]
                        for x in make("dialog_list 2")
                        if x["peer_type"] == 'channel' and x['title'] == human_chat_name][0]
        print('channel_print_name = %s' % channel_name)
        make("channel_set_admin %s %s" % (channel_name, bot_name))

    def send_msg(make):
        channel_name = [x["print_name"]
                        for x in make("dialog_list 2")
                        if x["peer_type"] == 'channel' and x['title'] == human_chat_name][0]
        print('channel_print_name = %s' % channel_name)
        make("msg %s '/set_team_chat@%s %d'"
             % (channel_name, bot_settings.BOT_USERNAME, team.id))

    human_chat_name = 'ОДД#%d. %s %s' % (team.id,
                                         team.region.convert_to_local_time(team.start_time)
                                         .strftime('%d.%m'),
                                         team.place)
    print('human_chat_name = %s' % human_chat_name)

    telegram_client = tc.TelegramClient(bot_settings.TELEGRAM_CLI_HOSTNAME, bot_settings.TELEGRAM_CLI_PORT)
    telegram_client.make_complex_request(create_group_chat)
    telegram_client.make_complex_request(chat_upgrade)
    telegram_client.make_complex_request(channel_set_admin)
    telegram_client.make_complex_request(send_msg)
    telegram_client.close()
