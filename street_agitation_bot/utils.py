import re

import telegram


def escape_markdown(text):
    """Helper function to escape telegram markup symbols"""
    escape_chars = '\*_`\['
    return re.sub(r'([%s])' % escape_chars, r'\\\1', text or "")


def chunks(arr, chunk_len):
    return [arr[i:i + chunk_len] for i in range(0, len(arr), chunk_len)]


def safe_delete_message(bot, chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except telegram.error.BadRequest:
        pass  # ignore 'Message can't be deleted'


def clean_phone_number(phone_number):
    res = ''.join(filter(lambda x: x.isdigit(), phone_number))
    if not res:
        return '-'
    if len(res) == 10:
        res = '7' + res
    if len(res) == 11 and res[0] == '8':
        res = '7' + res[1:]
    return res
