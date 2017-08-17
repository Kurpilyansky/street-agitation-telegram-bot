from telegram import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)

from street_agitation_bot import bot_settings, models, cron


def set_region_chat_command(bot, update, args):
    telegram_user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if bot_settings.is_admin_user_id(telegram_user_id):
        region_name = ' '.join(args[1:])
        region = models.Region.find_by_name(region_name, telegram_user_id)
        if not region:
            bot.send_message(chat_id, "Регион '%s' не найден" % region_name)
        elif args[0] == '0':
            region.registrations_chat_id = chat_id
            region.save()
            bot.send_message(chat_id, "Привязан новый чат 'Регистрации' в регионе '%s'" % region_name)
        else:
            bot.send_message(chat_id, "Неизвестный номер чата (первый аргумент должен быть 0)")


def restart_cron(bot, update):
    telegram_user_id = update.effective_user.id
    if bot_settings.is_admin_user_id(telegram_user_id):
        cron.restart_cron(bot)


def register_handlers(dispatcher):
    dispatcher.add_handler(CommandHandler("set_region_chat", set_region_chat_command, pass_args=True))
    dispatcher.add_handler(CommandHandler("restart_cron", set_region_chat_command, pass_args=True))
