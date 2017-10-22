
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)

from door_to_door_bot import bot_settings, models


def set_team_chat_command(bot, update, args):
    telegram_user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if bot_settings.is_admin_user_id(telegram_user_id):
        team_id = int(args[0])
        team = models.AgitationTeam.objects.filter(id=team_id).first()
        if team:
            team.chat_id = chat_id
            team.save()
            bot.send_message(chat_id, "Чат привязан к команде %s" % team.show(markdown=True),
                             parse_mode='Markdown')


def register(dp):
    dp.add_handler(CommandHandler("set_team_chat", set_team_chat_command, pass_args=True, pass_chat_data=True))
