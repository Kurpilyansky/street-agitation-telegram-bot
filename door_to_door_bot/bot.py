from django.db.models import Q

from door_to_door_bot import bot_settings, models
from door_to_door_bot.common import *
from street_agitation_bot.emoji import *
from street_agitation_bot import utils

import traceback

import re
import collections
from datetime import datetime, date, timedelta
from telegram import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)
from door_to_door_bot.bot_constants import *
from street_agitation_bot.handlers import (ConversationHandler, EmptyHandler)
import logging

from door_to_door_bot.handlers import team_list as teams_handlers
from door_to_door_bot.handlers import admin_commands as admin_handlers
from door_to_door_bot.handlers import agitation_process as agitation_process_handlers

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


def register_user_start(bot, update, user_data):
    send_message_text(bot, update,
                      'Здравствуйте! Пожалуйста, пройдите регистрацию, отправив свой контакт.',
                      user_data=user_data,
                      reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Зарегистрироваться', request_contact=True)]]))


def register_user(bot, update, user_data):
    contact = update.message.contact
    user = update.effective_user
    if not contact.user_id or contact.user_id != user.id:
        return
    user, created = models.User.update_or_create(
        params={'telegram_id': user.id,
                'first_name': contact.first_name,
                'last_name': contact.last_name,
                'phone': contact.phone_number,
                'telegram': user.username})
    send_message_text(bot, update, 'Вы зарегистрированы!', user_data=user_data, reply_markup=ReplyKeyboardRemove())
    return SELECT_REGION


def _in_range(range, region):
    return range[0] <= region.name[0] <= range[1]


def _build_add_region_keyboard(update, user_data):
    show_all = user_data.get('show_all_regions', False)
    user_telegram_id = update.effective_user.id
    public_regions = list(models.Region.objects.filter(settings__is_public=True))
    my_regions = list(models.Region.objects.filter(agitatorinregion__agitator__telegram_id=user_telegram_id))
    regions = list({r.id: r for r in public_regions + my_regions}.values())
    # TODO why it is not working? :( result contain duplicates
    # regions = list(models.Region.objects.filter(Q(settings__is_public=True)
    #                                             | Q(agitatorinregion__agitator__telegram_id=user_telegram_id)))
    if 'region_range' in user_data:
        range = user_data['region_range']
        regions = list(filter(lambda r: _in_range(range, r), regions))
        my_regions = list(filter(lambda r: _in_range(range, r), my_regions))
    if not show_all and not my_regions:
        show_all = True
    if show_all:
        added_regions = {region.id for region in my_regions}
    else:
        regions = my_regions
        added_regions = set()
    if len(regions) > 20:
        ranges = (('A', 'Б'), ('В', 'Ж'), ('И', 'К'), ('М', 'Р'), ('С', 'Т'), ('У', 'Я'))
        keyboard = [InlineKeyboardButton('-'.join(range), callback_data='-'.join(range))
                    for range in ranges]
        keyboard = utils.chunks(keyboard, 2)
    else:
        keyboard = []
        for region in regions:
            text = region.show(markdown=False)
            if region.id in added_regions:
                text = EMOJI_OK + ' ' + text
            keyboard.append(InlineKeyboardButton(text, callback_data=str(region.id)))
        keyboard = utils.chunks(keyboard, 2)
    if 'region_range' in user_data:
        keyboard.append([InlineKeyboardButton("<< Назад", callback_data=BACK)])
    if show_all:
        keyboard.append([InlineKeyboardButton('Оставить только мои штабы', callback_data=NO)])
    else:
        keyboard.append([InlineKeyboardButton('Показать все штабы', callback_data=YES)])
    return keyboard


def select_region_start(bot, update, user_data):
    user = models.User.find_by_telegram_id(update.effective_user.id)
    if not user:
        return REGISTER_USER
    keyboard = _build_add_region_keyboard(update, user_data)
    send_message_text(bot, update,
                      'Выберите региональный штаб',
                      user_data=user_data,
                      reply_markup=InlineKeyboardMarkup(keyboard))


def select_region_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == YES:
        user_data['show_all_regions'] = True
    elif query.data == NO:
        user_data['show_all_regions'] = False
    elif query.data == BACK:
        del user_data['region_range']
    else:
        if query.data[0].isdigit():
            user_data['region_id'] = int(query.data)
            return MENU
        else:
            user_data['region_range'] = tuple(query.data.split('-'))


def show_menu(bot, update, user_data):
    keyboard = list()
    if 'region_id' not in user_data:
        return SELECT_REGION
    elif 'cur_team_id' not in user_data:
        region_id = user_data['region_id']
        region = models.Region.get_by_id(region_id)
        user_telegram_id = update.effective_user.id
        user = models.User.find_by_telegram_id(user_telegram_id)
        abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
        if not abilities:
            models.AgitatorInRegion.save_abilities(region.id, user, {})
        keyboard.append([InlineKeyboardButton('Записаться', callback_data=SHOW_TEAM_LIST)])
        keyboard.append([InlineKeyboardButton('Начать обход', callback_data=START_AGITATION_PROCESS)])
        if models.AdminRights.has_admin_rights(user_telegram_id, region_id):
            keyboard.append([InlineKeyboardButton('Все команды и отчёты', callback_data=SHOW_ALL_TEAMS)])
            keyboard.append([InlineKeyboardButton('Сделать рассылку', callback_data=MAKE_BROADCAST)])
            keyboard.append([InlineKeyboardButton('Настройки штаба', callback_data=SHOW_REGION_SETTINGS)])
        send_message_text(bot, update, '*Меню - %s*\nВыберите действие для продолжения работы' % region.name,
                          user_data=user_data,
                          parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        return agitation_process_handlers.show_menu(bot, update, user_data)


@region_decorator
@has_admin_rights
def make_broadcast_start(bot, update, user_data, region_id):
    region = models.Region.get_by_id(region_id)
    send_message_text(bot, update,
                      '*%s*\nОтправьте сообщение, и оно будет отправлено всем пользователям' % region.name,
                      user_data=user_data,
                      parse_mode='Markdown')


@has_admin_rights
def make_broadcast(bot, update, user_data):
    user_data['broadcast_text'] = update.message.text
    return MAKE_BROADCAST_CONFIRM


@region_decorator
@has_admin_rights
def make_broadcast_confirm(bot, update, user_data, region_id):
    region = models.Region.get_by_id(region_id)
    broadcast_text = user_data['broadcast_text']
    text = '*%s*\nВы уверены, что хотите отправить *всем пользователям вашего региона* следующее сообщение:\n\n%s' % (region.name, broadcast_text)
    keyboard = [[InlineKeyboardButton('Отправить', callback_data=YES),
                 InlineKeyboardButton('Отмена', callback_data=NO)]]
    send_message_text(bot, update, text, user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
@has_admin_rights
def make_broadcast_confirm_button(bot, update, user_data, region_id):
    if 'broadcast_text' not in user_data:
        return MENU

    broadcast_text = user_data['broadcast_text']
    del user_data['broadcast_text']
    region = models.Region.get_by_id(region_id)
    broadcast_text2 = '*%s*\n%s' % (region.show(), broadcast_text)

    query = update.callback_query
    query.answer()
    if query.data == YES:
        errors = list()
        for u in models.User.objects.filter(agitatorinregion__region_id=region_id).all():
            try:
                cur_text = broadcast_text
                if models.AgitatorInRegion.objects.filter(agitator_id=u.id).count() > 1:
                    cur_text = broadcast_text2
                bot.send_message(u.telegram_id, cur_text, parse_mode='Markdown')
            except TelegramError as e:
                logger.error(e, exc_info=1)
                errors.append(e)
        return MENU
    else:
        return MENU


@region_decorator
@has_admin_rights
def show_region_settings_start(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    region = models.Region.get_by_id(region_id)
    text = 'Штаб *%s*' % region.show()
    keyboard = []
    if models.AdminRights.has_admin_rights(user_telegram_id, region_id, models.AdminRights.SUPER_ADMIN_LEVEL):
        text += '\nАдмины штаба:\n' + '\n'.join(map(lambda kvp: kvp[0].show(private=True),
                                                    models.AdminRights.get_region_admins(region_id).items()))
        keyboard.append([InlineKeyboardButton('Управление админами', callback_data=MANAGE_ADMIN_RIGHTS)])
    if region.settings.is_public:
        keyboard.append([InlineKeyboardButton('Скрыть штаб от пользователей', callback_data=CHANGE_REGION_PUBLICITY)])
    else:
        text += '\n\n_Штаб скрыт от пользователей_'
        keyboard.append([InlineKeyboardButton('Показать штаб пользователям', callback_data=CHANGE_REGION_PUBLICITY)])
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, text, user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
@has_admin_rights
def manage_admin_rights_start(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    level = models.AdminRights.get_admin_rights_level(user_telegram_id, region_id)
    if level < models.AdminRights.SUPER_ADMIN_LEVEL:
        return SHOW_REGION_SETTINGS
    region = models.Region.get_by_id(region_id)
    text = 'Управление админами штаба *%s*\n' % region.show()
    keyboard = []
    for user in models.AdminRights.can_disrank(region_id, level):
        keyboard.append([InlineKeyboardButton('Разжаловать %s' % user.show(markdown=False),
                                              callback_data=DEL_ADMIN_RIGHTS + str(user.id))])
    keyboard.append([InlineKeyboardButton('Добавить админа', callback_data=ADD_ADMIN_RIGHTS)])
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=SHOW_REGION_SETTINGS)])
    send_message_text(bot, update, text, user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
@has_admin_rights
def manage_admin_rights_button(bot, update, user_data, region_id):
    query = update.callback_query
    query.answer()
    if query.data in [ADD_ADMIN_RIGHTS, SHOW_REGION_SETTINGS]:
        return query.data
    else:
        match = re.match('%s(\d+)' % DEL_ADMIN_RIGHTS, query.data)
        if bool(match):
            user_telegram_id = update.effective_user.id
            level = models.AdminRights.get_admin_rights_level(user_telegram_id, region_id)
            user_id = int(match.group(1))
            models.AdminRights.disrank(user_id, region_id, level)


@region_decorator
@has_admin_rights
def add_admin_rights_start(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    level = models.AdminRights.get_admin_rights_level(user_telegram_id, region_id)
    if level < models.AdminRights.SUPER_ADMIN_LEVEL:
        return SHOW_REGION_SETTINGS
    text = 'Укажите нового админа'
    keyboard = [[InlineKeyboardButton('<< Назад', callback_data=MANAGE_ADMIN_RIGHTS)]]
    send_message_text(bot, update, text, user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
@has_admin_rights
def add_admin_rights_text(bot, update, user_data, region_id):
    user = _extract_mentioned_user(update.message)
    if user:
        models.AdminRights.objects.create(user=user,
                                          region_id=region_id)
        return MANAGE_ADMIN_RIGHTS


@region_decorator
@has_admin_rights
def change_region_publicity_start(bot, update, user_data, region_id):
    region = models.Region.get_by_id(region_id)
    text = 'Штаб *%s*\n' % region.show()
    keyboard = []
    if region.settings.is_public:
        text += 'Штаб присутствует в общем списке штабов. ' \
                'Любой человек может зарегистрироваться в этом штабе и пользоваться ботом. ' \
                'Вы можете скрыть штаб из общего списка, тогда новые пользователи не смогут ' \
                'зарегистрироваться в этом штабе.'
        keyboard.append([InlineKeyboardButton('Скрыть штаб от пользователей', callback_data=NO)])
    else:
        text += 'Штаб скрыт из общего списка штабов.' \
                'Если вы решите использовать бота в своем регионе, то покажите штаб пользователям.'
        keyboard.append([InlineKeyboardButton('Показать штаб пользователям', callback_data=YES)])
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=SHOW_REGION_SETTINGS)])
    send_message_text(bot, update, text, user_data=user_data,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
def change_region_publicity_button(bot, update, user_data, region_id):
    query = update.callback_query
    query.answer()
    if query.data in [SHOW_REGION_SETTINGS]:
        return query.data
    elif query.data == YES:
        region = models.Region.get_by_id(region_id)
        region.settings.is_public = True
        region.settings.save()
        return SHOW_REGION_SETTINGS
    elif query.data == NO:
        region = models.Region.get_by_id(region_id)
        region.settings.is_public = False
        region.settings.save()
        return SHOW_REGION_SETTINGS


def help(bot, update):
    update.message.reply_text('Help!', reply_markup=ReplyKeyboardRemove())


def send_bug_report(bot, update, user_data):
    state = models.ConversationState.objects.filter(key=update.effective_user.id).first()
    bot.send_message(bot_settings.bug_reports_chat_id, '%s\n\n%s' % (update, repr(state)))


def error_handler(bot, update, error):
    if not update:
        return
    logger.error('Update "%s" caused error "%s"' % (update, error), exc_info=1)
    try:
        bot.send_message(bot_settings.error_chat_id, 'Update "%s" caused error\n%s' % (update, traceback.format_exc()))
    except TelegramError as e:
        logger.error("Can not send message about error to telegram chat %s", e, exc_info=1)
        pass


def run_bot():
    updater = Updater(bot_settings.BOT_TOKEN)

    dp = updater.dispatcher

    # dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    admin_handlers.register(dp)

    states_handlers = {
            REGISTER_USER: [EmptyHandler(register_user_start, pass_user_data=True),
                            MessageHandler(Filters.contact, register_user, pass_user_data=True)],
            SELECT_REGION: [EmptyHandler(select_region_start, pass_user_data=True),
                            CallbackQueryHandler(select_region_button, pass_user_data=True)],
            MENU: [EmptyHandler(show_menu, pass_user_data=True), standard_callback_query_handler],
            MAKE_BROADCAST: [EmptyHandler(make_broadcast_start, pass_user_data=True),
                             MessageHandler(Filters.text, make_broadcast, pass_user_data=True)],
            MAKE_BROADCAST_CONFIRM: [EmptyHandler(make_broadcast_confirm, pass_user_data=True),
                                     CallbackQueryHandler(make_broadcast_confirm_button, pass_user_data=True)],
            SHOW_REGION_SETTINGS: [EmptyHandler(show_region_settings_start, pass_user_data=True),
                                   standard_callback_query_handler],
            MANAGE_ADMIN_RIGHTS: [EmptyHandler(manage_admin_rights_start, pass_user_data=True),
                                  CallbackQueryHandler(manage_admin_rights_button, pass_user_data=True)],
            ADD_ADMIN_RIGHTS: [EmptyHandler(add_admin_rights_start, pass_user_data=True),
                               MessageHandler(Filters.text | Filters.contact,
                                              add_admin_rights_text, pass_user_data=True),
                               standard_callback_query_handler],
            CHANGE_REGION_PUBLICITY: [EmptyHandler(change_region_publicity_start, pass_user_data=True),
                                      CallbackQueryHandler(change_region_publicity_button, pass_user_data=True)],
        }
    states_handlers.update(teams_handlers.state_handlers)
    states_handlers.update(agitation_process_handlers.state_handlers)

    conv_handler = ConversationHandler(
        user_model=models.User,
        conversation_state_model=models.ConversationState,
        entry_points=[CommandHandler("start", start)],
        unknown_state_handler=EmptyHandler(cancel, pass_user_data=True),
        states=states_handlers,
        pre_fallbacks=[],
        fallbacks=[CommandHandler('menu', cancel, pass_user_data=True),
                   CommandHandler('cancel', cancel, pass_user_data=True),
                   CommandHandler("region", change_region, pass_user_data=True),
                   CommandHandler("send_bug_report", send_bug_report, pass_user_data=True)]
    )

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
