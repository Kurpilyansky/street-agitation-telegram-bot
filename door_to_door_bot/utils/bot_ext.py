

def export_chat_invite_link(bot, chat_id):
    url = '{0}/exportChatInviteLink'.format(bot.base_url)
    result = bot._request.post(url, {'chat_id': chat_id})
    print(result)
    return result
