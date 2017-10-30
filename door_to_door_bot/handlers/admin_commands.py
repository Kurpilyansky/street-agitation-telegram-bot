
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)

from door_to_door_bot import bot_settings, models
from door_to_door_bot.utils import bot_ext, team_chat_management


def create_team_chat_command(bot, update, args):
    telegram_user_id = update.effective_user.id
    if bot_settings.is_admin_user_id(telegram_user_id):
        team_id = int(args[0])
        team = models.AgitationTeam.objects.filter(id=team_id).first()
        if team:
            team_chat_management.create_team_chat(team)


def set_team_chat_command(bot, update, args):
    telegram_user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if bot_settings.is_admin_user_id(telegram_user_id):
        team_id = int(args[0])
        team = models.AgitationTeam.objects.filter(id=team_id).first()
        if team:
            team.chat_id = chat_id
            team.save()
            bot.send_message(chat_id, 'Чат привязан к команде %s' % team.show(markdown=True),
                             parse_mode='Markdown')
            invite_link = bot_ext.export_chat_invite_link(bot, team.chat_id)
            for agitator in team.agitators.all():
                bot.send_message(agitator.telegram_id,
                                 'Для команды %s создан чат. Присоединяйтесь %s' % (team.show(), invite_link))


def register(dp):
    pass
    #dp.add_handler(CommandHandler("set_team_chat", set_team_chat_command, pass_args=True))
    #dp.add_handler(CommandHandler("create_team_chat", create_team_chat_command, pass_args=True))
