
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


ALL_TEAMS_PAGE_SIZE = 10


@region_decorator
def show_all_teams_start(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    if not models.AdminRights.has_admin_rights(user_telegram_id, region_id):
        return MENU

    page_size = ALL_TEAMS_PAGE_SIZE
    offset = user_data.get('all_teams_offset', 0)

    query_set = models.AgitationTeam.objects.filter(region_id=region_id).order_by('-start_time').all()
    total_count = query_set.count()
    if offset < 0:
        offset = 0
    if offset >= total_count:
        offset = max(0, total_count - page_size)
    teams = list(query_set[offset:][:page_size])
    keyboard = []
    for team in teams:
        keyboard.append([InlineKeyboardButton(team.show(markdown=False), callback_data=str(team.id))])
    keyboard += build_paging_buttons(offset, total_count, page_size, True)
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=MENU)])
    send_message_text(bot, update, 'Выберите команду для обхода',
                      user_data=user_data,
                      reply_markup=InlineKeyboardMarkup(keyboard))


def show_all_teams_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data in [MENU]:
        return query.data
    elif query.data == TO_BEGIN:
        user_data['all_teams_offset'] = 0
    elif query.data == TO_END:
        user_data['all_teams_offset'] = 1000000
    elif query.data == BACK:
        user_data['all_teams_offset'] = user_data.get('all_teams_offset', 0) - ALL_TEAMS_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['all_teams_offset'] = user_data.get('all_teams_offset', 0) + ALL_TEAMS_PAGE_SIZE
    else:
        match = re.match('\d+', query.data)
        if bool(match):
            user_data['cur_team_id'] = int(query.data)
            return MENU


@region_decorator
def start_agitation_process_start(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    my_teams = list(models.AgitationTeam
                          .objects
                          .filter(region_id=region_id,
                                  start_time__gte=date.today())
                          .filter(agitators__telegram_id=user_telegram_id)
                          .order_by('start_time')
                          .all())
    keyboard = []
    for team in my_teams:
        keyboard.append([InlineKeyboardButton(team.show(markdown=False), callback_data=str(team.id))])
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])
    send_message_text(bot, update, 'Выберите команду для обхода',
                      user_data=user_data,
                      reply_markup=InlineKeyboardMarkup(keyboard))


def start_agitation_process_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        return MENU
    else:
        match = re.match('\d+', query.data)
        if bool(match):
            user_data['cur_team_id'] = int(query.data)
            return MENU


def show_team_start(bot, update, user_data):
    team = models.AgitationTeam.objects.filter(id=user_data['show_team_id']).first()
    if not team:
        del user_data['show_team_id']
        return MENU
    keyboard = [[InlineKeyboardButton('<< Меню', callback_data=BACK)]]
    send_message_text(bot, update,
                      '*Команда*\n%s' % team.show(),
                      user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


def show_team_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        del user_data['show_team_id']
        return MENU


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
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    text = ''
    if full_teams_str:
        text += '%d команд уже сформировано целиком\n' % len(full_teams_str)
    if teams_str:
        text += 'Вы можете присоединиться к другому волонтеру или создать новую команду: \n%s' % ('\n'.join(teams_str))
    else:
        text += 'Вы можете создать новую команду'
    send_message_text(bot, update, text, user_data=user_data,
                      reply_markup=InlineKeyboardMarkup(keyboard),
                      parse_mode='Markdown')


def team_list_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data in [MENU]:
        return query.data
    if query.data == NEW:
        return CREATE_NEW_TEAM
    else:
        match = re.match('\d+', query.data)
        if bool(match):
            user_data['join_to_team_id'] = int(query.data)
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
    send_message_text(bot, update, text, user_data=user_data, reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
def create_new_team_button(bot, update, user_data, region_id):
    query = update.callback_query
    query.answer()
    if query.data == YES:
        region = models.Region.get_by_id(region_id)
        team_opts = user_data['team']
        del user_data['team']
        start_time = datetime(year=team_opts['year'],
                              month=team_opts['month'],
                              day=team_opts['day'],
                              hour=team_opts['hour'],
                              minute=team_opts['minute'])
        team = models.AgitationTeam(region_id=region_id,
                                    start_time=region.convert_from_local_time(start_time),
                                    place=team_opts['place'])
        team.save()
        user = models.User.find_by_telegram_id(update.effective_user.id)
        team.agitators.add(user)

        user_data['show_team_id'] = team.id
        return SHOW_TEAM
    del user_data['team']
    return MENU


@region_decorator
def create_new_team___set_date_start(bot, update, user_data, region_id):
    region = models.Region.get_by_id(region_id)
    today = region.convert_to_local_time(datetime.now()).date()
    buttons = []
    for i in range(3):
        text = (today + timedelta(days=i)).strftime("%d.%m")
        data = (today + timedelta(days=i)).strftime("%d.%m.%Y")
        buttons.append(InlineKeyboardButton(text, callback_data=data))
    keyboard = [buttons, [InlineKeyboardButton('<< Назад', callback_data=BACK)]]
    send_message_text(bot, update, 'Укажите дату', user_data=user_data, reply_markup=InlineKeyboardMarkup(keyboard))


def create_new_team__set_date_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        del user_data['team']
        return SHOW_TEAM_LIST
    day, month, year = map(int, query.data.split('.'))
    user_data['team']['day'] = day
    user_data['team']['month'] = month
    user_data['team']['year'] = year
    return CREATE_NEW_TEAM__SET_TIME


def create_new_team___set_time_start(bot, update, user_data):
    keyboard = [[InlineKeyboardButton('<< Назад', callback_data=CREATE_NEW_TEAM__SET_DATE)]]
    send_message_text(bot, update, 'Укажите время начала в формате ЧЧ:ММ (например, 18:00)',
                      user_data=user_data,
                      reply_markup=InlineKeyboardMarkup(keyboard))


def create_new_team__set_time_text(bot, update, user_data):
    text = update.message.text
    hour, minute = map(int, text.split(':'))
    user_data['team']['hour'] = hour
    user_data['team']['minute'] = minute
    return CREATE_NEW_TEAM__SET_PLACE


def create_new_team___set_place_start(bot, update, user_data):
    keyboard = [[InlineKeyboardButton('<< Назад', callback_data=CREATE_NEW_TEAM__SET_TIME)]]
    send_message_text(bot, update, 'Укажите краткое и понятное описание места',
                      user_data=user_data,
                      reply_markup=InlineKeyboardMarkup(keyboard))


def create_new_team__set_place_text(bot, update, user_data):
    user_data['team']['place'] = update.message.text
    return CREATE_NEW_TEAM


def join_team_start(bot, update, user_data):
    team_id = user_data['join_to_team_id']
    team = models.AgitationTeam.objects.get(id=team_id)
    keyboard = [[InlineKeyboardButton('Да', callback_data=YES),
                 InlineKeyboardButton('Нет', callback_data=NO)]]
    send_message_text(bot, update,
                      'Вы уверены, что хотите присоединиться к %s?' % team.show(markdown=True),
                      user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


def join_team_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    team_id = user_data['join_to_team_id']
    del user_data['join_to_team_id']
    if query.data == YES:
        team = models.AgitationTeam.objects.get(id=team_id)
        user = models.User.find_by_telegram_id(update.effective_user.id)
        team.agitators.add(user)
        user_data['show_team_id'] = team.id
        return SHOW_TEAM
    return SHOW_TEAM_LIST


state_handlers = {
    SHOW_TEAM_LIST: [EmptyHandler(team_list_start, pass_user_data=True),
                     CallbackQueryHandler(team_list_button, pass_user_data=True)],
    CREATE_NEW_TEAM: [EmptyHandler(create_new_team_start, pass_user_data=True),
                      CallbackQueryHandler(create_new_team_button, pass_user_data=True)],
    CREATE_NEW_TEAM__SET_DATE: [EmptyHandler(create_new_team___set_date_start, pass_user_data=True),
                                CallbackQueryHandler(create_new_team__set_date_button, pass_user_data=True)],
    CREATE_NEW_TEAM__SET_TIME: [EmptyHandler(create_new_team___set_time_start, pass_user_data=True),
                                MessageHandler(Filters.text, create_new_team__set_time_text, pass_user_data=True),
                                standard_callback_query_handler],
    CREATE_NEW_TEAM__SET_PLACE: [EmptyHandler(create_new_team___set_place_start, pass_user_data=True),
                                 MessageHandler(Filters.text, create_new_team__set_place_text, pass_user_data=True),
                                 standard_callback_query_handler],
    SHOW_TEAM: [EmptyHandler(show_team_start, pass_user_data=True),
                CallbackQueryHandler(show_team_button, pass_user_data=True)],
    JOIN_TEAM: [EmptyHandler(join_team_start, pass_user_data=True),
                CallbackQueryHandler(join_team_button, pass_user_data=True)],
    START_AGITATION_PROCESS: [EmptyHandler(start_agitation_process_start, pass_user_data=True),
                              CallbackQueryHandler(start_agitation_process_button, pass_user_data=True)],
    SHOW_ALL_TEAMS: [EmptyHandler(show_all_teams_start, pass_user_data=True),
                     CallbackQueryHandler(show_all_teams_button, pass_user_data=True)],
}
