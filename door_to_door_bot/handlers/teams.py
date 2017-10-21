
import re

from telegram import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)


from street_agitation_bot.handlers import (EmptyHandler)
from door_to_door_bot import models
from door_to_door_bot.common import *
from door_to_door_bot.bot_constants import *

from datetime import date, timedelta


@region_decorator
def team_list_start(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    teams = list(models.AgitationTeam
                       .objects
                       .filter(region_id=region_id,
                               start_time__gte=date.today())
                       .order_by('start_time')
                       .all())
    full_teams_str = []
    teams_str = []
    keyboard = []
    for team in teams:
        if team.is_full():
            full_teams_str.append(team.show(markdown=True))
        else:
            teams_str.append(team.show(markdown=True))
            if not team.agitators.filter(telegram_id=user_telegram_id).exists():
                keyboard.append([InlineKeyboardButton(team.show(markdown=False), callback_data=str(team.id))])
    keyboard.append([InlineKeyboardButton('Создать новую команду', callback_data=NEW)])
    text = ''
    if full_teams_str:
        text += '%d команд уже сформировано целиком\n' % len(full_teams_str)
    if teams_str:
        text += 'Вы можете присоединиться к другому волонтеру или создать новую команду: \n%s' % ('\n'.join(teams_str))
    else:
        text += 'Вы можете создать новую команду'
    send_message_text(bot, update, user_data, text,
                      reply_markup=InlineKeyboardMarkup(keyboard),
                      parse_mode='Markdown')


def team_list_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == NEW:
        return CREATE_NEW_TEAM
    else:
        match = re.match('\d+', query.data)
        if bool(match):
            user_data['team_id'] = int(query.data)
            return JOIN_TEAM


def create_new_team_start(bot, update, user_data):
    if 'team' not in user_data:
        user_data['team'] = {}
        return CREATE_NEW_TEAM__SET_DATE
    team_opts = user_data['team']
    text = 'Вы уверены, что хотите создать команду %02d.%02d %02d:%02d %s?' % \
           (team_opts['day'], team_opts['month'], team_opts['hour'], team_opts['minute'], team_opts['place'])
    keyboard = [[InlineKeyboardButton('Да', callback_data=YES),
                 InlineKeyboardButton('Нет', callback_data=NO)]]
    send_message_text(bot, update, user_data, text, reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
def create_new_team_button(bot, update, user_data, region_id):
    query = update.callback_query
    query.answer()
    if query.data == YES:
        region = models.Region.get_by_id(region_id)
        team_opts = user_data['team']
        team = models.AgitationTeam(region_id=region_id,
                                    start_time=datetime(year=team_opts['year'],
                                                        month=team_opts['month'],
                                                        day=team_opts['day'],
                                                        hour=team_opts['hour'])
                                               - timedelta(seconds=region.timezone_delta),
                                    place=team_opts['place'])
        team.save()
        user = models.User.find_by_telegram_id(update.effective_user.id)
        team.agitators.add(user)
    del user_data['team']
    return MENU


def create_new_team___set_date_start(bot, update, user_data):
    buttons = []
    today = date.today()
    for i in range(3):
        text = (today + timedelta(days=i)).strftime("%d.%m")
        data = (today + timedelta(days=i)).strftime("%d.%m.%Y")
        buttons.append(InlineKeyboardButton(text, callback_data=data))
    send_message_text(bot, update, user_data, 'Укажите дату', reply_markup=InlineKeyboardMarkup([buttons]))


def create_new_team__set_date_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    day, month, year = map(int, query.data.split('.'))
    user_data['team']['day'] = day
    user_data['team']['month'] = month
    user_data['team']['year'] = year
    return CREATE_NEW_TEAM__SET_TIME


def create_new_team___set_time_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите время начала в формате ЧЧ:ММ (например, 18:00)')


def create_new_team__set_time_text(bot, update, user_data):
    text = update.message.text
    hour, minute = map(int, text.split(':'))
    user_data['team']['hour'] = hour
    user_data['team']['minute'] = minute
    return CREATE_NEW_TEAM__SET_PLACE


def create_new_team___set_place_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите краткое и понятное описание места')


def create_new_team__set_place_text(bot, update, user_data):
    user_data['team']['place'] = update.message.text
    return CREATE_NEW_TEAM


def join_team_start(bot, update, user_data):
    team_id = user_data['team_id']
    team = models.AgitationTeam.objects.get(id=team_id)
    keyboard = [[InlineKeyboardButton('Да', callback_data=YES),
                 InlineKeyboardButton('Нет', callback_data=NO)]]
    send_message_text(bot, update, user_data,
                      'Вы уверены, что хотите присоединиться к %s?' % team.show(markdown=True),
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


def join_team_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    team_id = user_data['team_id']
    del user_data['team_id']
    if query.data == YES:
        team = models.AgitationTeam.objects.get(id=team_id)
        user = models.User.find_by_telegram_id(update.effective_user.id)
        team.agitators.add(user)
        return MENU
    return SHOW_TEAM_LIST


state_handlers = {
    SHOW_TEAM_LIST: [EmptyHandler(team_list_start, pass_user_data=True),
                     CallbackQueryHandler(team_list_button, pass_user_data=True)],
    CREATE_NEW_TEAM: [EmptyHandler(create_new_team_start, pass_user_data=True),
                      CallbackQueryHandler(create_new_team_button, pass_user_data=True)],
    CREATE_NEW_TEAM__SET_DATE: [EmptyHandler(create_new_team___set_date_start, pass_user_data=True),
                                CallbackQueryHandler(create_new_team__set_date_button, pass_user_data=True)],
    CREATE_NEW_TEAM__SET_TIME: [EmptyHandler(create_new_team___set_time_start, pass_user_data=True),
                                MessageHandler(Filters.text, create_new_team__set_time_text, pass_user_data=True)],
    CREATE_NEW_TEAM__SET_PLACE: [EmptyHandler(create_new_team___set_place_start, pass_user_data=True),
                                 MessageHandler(Filters.text, create_new_team__set_place_text, pass_user_data=True)],
    JOIN_TEAM: [EmptyHandler(join_team_start, pass_user_data=True),
                CallbackQueryHandler(join_team_button, pass_user_data=True)],
}