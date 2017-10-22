import re

from telegram import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)

from street_agitation_bot.handlers import ConversationHandler, EmptyHandler
from door_to_door_bot import models
from door_to_door_bot.common import send_message_text
from door_to_door_bot.bot_constants import *


def team_decorator(func):
    def wrapper(bot, update, chat_data, *args, **kwargs):
        if 'team_id' not in chat_data:
            chat_id = update.effective_chat.id
            team = models.AgitationTeam.objects.get(chat_id=chat_id)
            chat_data['team_id'] = team.id
        else:
            team_id = int(chat_data['team_id'])
            team = models.AgitationTeam.objects.get(id=team_id)
        return func(bot, update, chat_data, team=team, *args, **kwargs)

    return wrapper


def clear_chat_data(chat_data, keep_keys=None):
    for key in list(chat_data.keys()):
        if not (keep_keys and key in keep_keys):
            del chat_data[key]


def cancel(bot, update, chat_data):
    clear_chat_data(chat_data, ['last_bot_message_id', 'last_bot_message_ts'])
    return start(bot, update)


def start(bot, update):
    return MENU


@team_decorator
def show_menu(bot, update, chat_data, team):
    send_message_text(bot, update, team.show(markdown=True),
                      chat_data=chat_data,
                      parse_mode='Markdown')


def register(dp):
    states_handlers = {
        MENU: [EmptyHandler(show_menu, pass_chat_data=True)],
        }
    conv_handler = ConversationHandler(
        per_user=False,
        per_chat=True,
        user_model=models.User,
        conversation_state_model=models.ConversationState,
        entry_points=[CommandHandler("start", start)],
        unknown_state_handler=EmptyHandler(cancel, pass_chat_data=True),
        states=states_handlers,
        pre_fallbacks=[],
        fallbacks=[]
    )
    dp.add_handler(conv_handler)
