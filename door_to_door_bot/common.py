
from telegram import (InlineKeyboardButton)
from telegram.ext import (CallbackQueryHandler)

from datetime import datetime
from door_to_door_bot import models
from door_to_door_bot.bot_constants import *
from street_agitation_bot import utils


def region_decorator(func):
    def wrapper(bot, update, user_data, *args, **kwargs):
        if 'region_id' not in user_data:
            return change_region(bot, update, user_data)
        return func(bot, update, user_data, region_id=int(user_data['region_id']), *args, **kwargs)

    return wrapper


def has_admin_rights(func):
    def wrapper(bot, update, user_data, *args, **kwargs):
        if 'region_id' not in user_data:
            return change_region(bot, update, user_data)
        region_id = user_data['region_id']
        user_telegram_id = update.effective_user.id
        if not models.AdminRights.has_admin_rights(user_telegram_id, region_id):
            return cancel(bot, update, user_data)
        return func(bot, update, user_data, *args, **kwargs)

    return wrapper


def send_message_text(bot, update, *args, **kwargs):
    if 'user_data' in kwargs:
        data = kwargs.pop('user_data')
        chat_id = update.effective_user.id
    else:
        data = kwargs.pop('chat_data')
        chat_id = update.effective_chat.id
    last_bot_message_ids = data.get('last_bot_message_id', None)
    if not last_bot_message_ids:
        last_bot_message_ids = []
    elif not isinstance(last_bot_message_ids, list):
        last_bot_message_ids = [last_bot_message_ids]

    data.pop('last_bot_message_id', None)
    data.pop('last_bot_message_ts', None)
    location = kwargs.get('location', {})
    kwargs.pop('location', None)
    cur_ts = datetime.utcnow().timestamp()
    for message_id in last_bot_message_ids:
        utils.safe_delete_message(bot, chat_id, message_id)
    new_message_ids = []
    if location:
        kwargs2 = kwargs.copy()
        if args:
            kwargs2.pop('reply_markup', None)
        new_message = bot.send_location(chat_id, location['latitude'], location['longitude'], **kwargs2)
        new_message_ids.append(new_message.message_id)
    if args:
        new_message = bot.send_message(chat_id, *args, **kwargs)
        new_message_ids.append(new_message.message_id)
    data['last_bot_message_id'] = new_message_ids
    data['last_bot_message_ts'] = cur_ts


def standard_callback(bot, update):
    query = update.callback_query
    query.answer()
    return query.data


standard_callback_query_handler = CallbackQueryHandler(standard_callback)


def start(bot, update):
    if models.User.find_by_telegram_id(update.effective_user.id):
        return MENU
    else:
        return REGISTER_USER


def clear_user_data(user_data, keep_keys=None):
    for key in list(user_data.keys()):
        if not (keep_keys and key in keep_keys):
            del user_data[key]


def cancel(bot, update, user_data):
    clear_user_data(user_data, ['last_bot_message_id', 'last_bot_message_ts', 'region_id'])
    return start(bot, update)


def change_region(bot, update, user_data):
    clear_user_data(user_data, ['last_bot_message_id', 'last_bot_message_ts'])
    return SELECT_REGION


def build_paging_buttons(offset, count, page_size, fast=False):
    paging_buttons = []
    if offset > 0:
        if fast:
            paging_buttons.append(InlineKeyboardButton('<<', callback_data=TO_BEGIN))
        paging_buttons.append(InlineKeyboardButton('<', callback_data=BACK))
    if count > offset + page_size:
        paging_buttons.append(InlineKeyboardButton('>', callback_data=FORWARD))
        if fast:
            paging_buttons.append(InlineKeyboardButton('>>', callback_data=TO_END))
    if paging_buttons:
        return [paging_buttons]
    else:
        return []
