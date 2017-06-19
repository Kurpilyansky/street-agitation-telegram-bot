from street_agitation_bot import bot_settings, models, notifications

import operator
import re
import collections
from datetime import datetime, date, timedelta
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)
from street_agitation_bot.handlers import (ConversationHandler, EmptyHandler)
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


YES = 'YES'
NO = 'NO'
BACK = 'BACK'
FORWARD = 'FORWARD'
TRASH = 'TRASH'
SKIP = 'SKIP'
END = 'END'

SET_FULL_NAME = 'SET_FULL_NAME'
SET_PHONE = 'SET_PHONE'
SAVE_PROFILE = 'SAVE_PROFILE'

SELECT_REGION = 'SELECT_REGION'
ADD_REGION = 'ADD_REGION'
SET_ABILITIES = 'SET_ABILITIES'
SAVE_ABILITIES = 'SAVE_ABILITIES'

MENU = 'MENU'
SCHEDULE = 'SCHEDULE'
APPLY_TO_AGITATE = 'APPLY_TO_AGITATE'
SHOW_PARTICIPATIONS = 'SHOW_PARTICIPATIONS'
SET_EVENT_PLACE = 'SET_EVENT_PLACE'
SELECT_EVENT_PLACE = 'SELECT_EVENT_PLACE'
SET_PLACE_ADDRESS = 'SET_PLACE_ADDRESS'
SET_PLACE_LOCATION = 'SET_PLACE_LOCATION'
SELECT_DATES = 'SELECT_DATES'
SET_EVENT_TIME = 'SET_EVENT_TIME'
CREATE_EVENT_SERIES = 'CREATE_EVENT_SERIES'


def region_decorator(func):
    def wrapper(bot, update, user_data, *args, **kwargs):
        if 'region_id' not in user_data:
            return change_region(bot, update, user_data)
        return func(bot, update, user_data, region_id=user_data['region_id'], *args, **kwargs)

    return wrapper


def delete_inline_keyboard(bot, chat_id, message_id):
    try:
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except TelegramError:
        pass  # TODO caused error "Message is not modified"


def send_message_text(bot, update, user_data, *args, edit_last=True, **kwargs):
    if edit_last and update.callback_query:
        new_message = update.callback_query.edit_message_text(*args, **kwargs)
    else:
        if 'last_bot_message_id' in user_data:
            delete_inline_keyboard(bot, update.effective_chat.id, user_data['last_bot_message_id'])
        new_message = update.effective_message.reply_text(*args, **kwargs)
    user_data['last_bot_message_id'] = new_message.message_id


def standard_callback(bot, update):
    query = update.callback_query
    query.answer()
    return query.data


def start(bot, update):
    if models.Agitator.objects.filter(telegram_id=update.effective_user.id).exists():
        return MENU
    else:
        return SET_FULL_NAME


def set_full_name_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите ваше имя')


def set_full_name(bot, update, user_data):
    user_data["full_name"] = update.message.text
    return SET_PHONE


def set_phone_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите ваш телефон')


def set_phone(bot, update, user_data):
    user_data["phone"] = update.message.text
    return SAVE_PROFILE


def save_profile(bot, update, user_data):
    user = update.effective_user
    agitator, created = models.Agitator.objects.update_or_create(
                                telegram_id=user.id,
                                defaults={'full_name': user_data.get('full_name'),
                                          'phone': user_data.get('phone'),
                                          'telegram': user.username})

    text = 'Спасибо за регистрацию!' if created else 'Данные профиля обновлены'
    send_message_text(bot, update, user_data, text, reply_markup=_create_back_to_menu_keyboard())

    del user_data['full_name']
    del user_data['phone']


def select_region(bot, update, user_data):
    agitator = models.Agitator.find_by_id(update.effective_user.id)
    if not agitator:
        return SET_FULL_NAME
    regions = agitator.regions
    if not regions:
        return ADD_REGION
    keyboard = list()
    for region in regions:
        keyboard.append([InlineKeyboardButton(region.name, callback_data=str(region.id))])
    keyboard.append([InlineKeyboardButton('Добавить другой регион', callback_data=ADD_REGION)])
    send_message_text(bot, update, user_data, 'Выберите регион', reply_markup=InlineKeyboardMarkup(keyboard))


def select_region_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == ADD_REGION:
        return ADD_REGION
    else:
        region = models.Region.get_by_id(query.data)
        user_data['region_id'] = query.data
        send_message_text(bot, update, user_data, 'Выбран регион «%s»' % region.name)
        return MENU


def add_region_start(bot, update, user_data):
    if 'unknown_region_name' in user_data:
        text = 'Регион «%s» не зарегистрирован в системе.\n' \
               'Введите название региона или города' % user_data['unknown_region_name']
        del user_data['unknown_region_name']
        send_message_text(bot, update, user_data, text)
    else:
        send_message_text(bot, update, user_data, 'Введите название региона или города')


def add_region(bot, update, user_data):
    user = update.effective_user
    region_name = update.message.text
    region = models.Region.find_by_name(region_name, update.effective_user.id)
    if region:
        if models.AgitatorInRegion.get(region.id, user.id):
            send_message_text(bot, update, user_data, 'Данный регион уже добавлен')
            return MENU
        user_data['region_id'] = region.id
        return SET_ABILITIES
    else:
        user_data['unknown_region_name'] = region_name


ABILITIES_TEXTS = {
    'have_registration': 'Есть постоянная или временная регистрация в данном регионе',
    'can_agitate': 'Агитировать на улице',
    'can_be_applicant': 'Быть заявителем кубов',
    'can_deliver': 'Доставить куб на машине',
    'can_hold': 'Хранить куб дома',
}


def set_abilities(bot, update, user_data):
    if 'abilities' not in user_data:
        user_data['abilities'] = collections.OrderedDict([
            ('have_registration', False),
            ('can_agitate', False),
            ('can_be_applicant', False),
            ('can_deliver', False),
            ('can_hold', False),
        ])
    keyboard = list()
    for key, val in user_data['abilities'].items():
        text = ("+ " if val else "") + ABILITIES_TEXTS[key]
        keyboard.append([InlineKeyboardButton(text, callback_data=key)])
    keyboard.append([InlineKeyboardButton('-- Закончить выбор --', callback_data=END)])
    send_message_text(bot, update, user_data, 'Чем вы готовы помочь?', reply_markup=InlineKeyboardMarkup(keyboard))


def set_abilities_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == END:
        return SAVE_ABILITIES
    elif query.data in user_data['abilities']:
        user_data['abilities'][query.data] ^= True


@region_decorator
def save_abilities(bot, update, user_data, region_id):
    agitator_id = update.effective_user.id
    text = ''
    for key, val in user_data['abilities'].items():
        text += "\n%s: %s" % (ABILITIES_TEXTS[key], "*да*" if val else "нет")
    obj, created = models.AgitatorInRegion.save_abilities(region_id, agitator_id, user_data['abilities'])
    send_message_text(bot, update, user_data,
                      'Данные сохранены' + text,
                      parse_mode="Markdown",
                      reply_markup=_create_back_to_menu_keyboard())
    if created:
        notifications.notify_about_new_registration(bot, region_id, agitator_id, text)
    del user_data['abilities']


def show_menu(bot, update, user_data):
    if update.callback_query:
        try:
            update.callback_query.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass  # TODO caused error "Message is not modified"
    keyboard = list()
    if 'region_id' in user_data:
        keyboard.append([InlineKeyboardButton('Расписание', callback_data=SCHEDULE)])
        keyboard.append([InlineKeyboardButton('Записаться на куб', callback_data=APPLY_TO_AGITATE)])
        region_id = user_data['region_id']
        agitator_id = update.effective_user.id
        if models.AgitationEventParticipant.objects.filter(
                                        agitator_id=agitator_id,
                                        event__start_date__gte=date.today()).exists():
            keyboard.append([InlineKeyboardButton('Мои кубы', callback_data=SHOW_PARTICIPATIONS)])
        abilities = models.AgitatorInRegion.get(region_id, agitator_id)
        if abilities.is_admin:
            keyboard.append([InlineKeyboardButton('Добавить ивент', callback_data=SET_EVENT_PLACE)])
    else:
        keyboard.append([InlineKeyboardButton('Выбрать регион', callback_data=SELECT_REGION)])
    send_message_text(bot, update, user_data, '*Меню*\nВыберите действие для продолжения работы', parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
def show_schedule(bot, update, user_data, region_id):
    events = list(models.AgitationEvent.objects.filter(
        start_date__gte=date.today(),
        place__region_id=region_id
    ).select_related('place'))
    if events:
        schedule_text = "\n".join(map(operator.methodcaller("show"), events))
    else:
        schedule_text = "В ближайшее время пока ничего не запланировано"
    schedule_text = "*Расписание*\n" + schedule_text
    keyboard = _create_back_to_menu_keyboard()
    if events:
        keyboard.inline_keyboard[0:0] = [[InlineKeyboardButton('Записаться на куб', callback_data=APPLY_TO_AGITATE)]]
    send_message_text(bot, update, user_data,
                      schedule_text,
                      parse_mode="Markdown",
                      reply_markup=keyboard)


@region_decorator
def show_participations(bot, update, user_data, region_id):
    region = models.Region.get_by_id(region_id)
    agitator_id = update.effective_user.id
    participations = models.AgitationEventParticipant.objects.filter(
        agitator_id=agitator_id,
        event__start_date__gte=date.today(),
    ).select_related('event', 'event__place').all()
    if participations:
        lines = list()
        for p in participations:
            status = u'\U00002705' if p.approved else (u'\U0000274c' if p.declined else u'\U00002753')
            line = p.event.show() + " " + status
            if p.event.place.region_id != region.id:
                line = '*%s* %s' % (region.name, line)
            lines.append(line)
        text = "\n".join(lines)
    else:
        text = "Вы не записались ни на один будущий куб"
    text = "*Ваши кубы*\n" + text
    keyboard = _create_back_to_menu_keyboard()
    send_message_text(bot, update, user_data,
                      text,
                      parse_mode="Markdown",
                      reply_markup=keyboard)

EVENT_PAGE_SIZE = 5


@region_decorator
def apply_to_agitate(bot, update, user_data, region_id):
    if 'event_id' in user_data:
        event = models.AgitationEvent.objects.filter(id=user_data['event_id']).first()
        if event:
            keyboard = [[InlineKeyboardButton('Да', callback_data=YES),
                         InlineKeyboardButton('Нет', callback_data=NO)]]
            send_message_text(bot, update, user_data,
                              '*Подтвердите, что ваш выбор*\n'
                              'Вы хотитие волонтерить на кубе %s?' % event.show(),
                              parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(keyboard))
            return
        else:
            del user_data['event_id']

    if 'events_offset' not in user_data:
        user_data['events_offset'] = 0

    offset = user_data['events_offset']
    query_set = models.AgitationEvent.objects.filter(start_date__gte=date.today(), place__region_id=region_id)
    events = list(query_set.select_related('place')[offset:offset + EVENT_PAGE_SIZE])
    keyboard = list()
    if offset > 0:
        keyboard.append([InlineKeyboardButton('Назад', callback_data=BACK)])
    for event in events:
        keyboard.append([InlineKeyboardButton(event.show(), callback_data=str(event.id))])
    if query_set.count() > offset + EVENT_PAGE_SIZE:
        keyboard.append([InlineKeyboardButton('Вперед', callback_data=FORWARD)])
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      '*В каких кубах вы хотите поучаствовать в качестве уличного агитатора?*',
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def apply_to_agitate_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        user_data['events_offset'] -= EVENT_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['events_offset'] += EVENT_PAGE_SIZE
    elif query.data == NO:
        del user_data['event_id']
    elif query.data == YES:
        event_id = user_data['event_id']
        agitator_id = update.effective_user.id
        created = models.AgitationEventParticipant.create(agitator_id, event_id)
        if created:
            notifications.notify_about_new_participant(bot, event_id, agitator_id)
        del user_data['event_id']
    elif query.data == MENU:
        return MENU
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['event_id'] = int(query.data)


def set_event_place(bot, update, user_data):
    keyboard = [[InlineKeyboardButton('Выбрать место из старых', callback_data=SELECT_EVENT_PLACE)],
                [InlineKeyboardButton('Создать новое место', callback_data=SET_PLACE_ADDRESS)]]
    send_message_text(bot, update, user_data,
                      "Укажите место",
                      reply_markup=InlineKeyboardMarkup(keyboard))


PLACE_PAGE_SIZE = 5


@region_decorator
def select_event_place(bot, update, user_data, region_id):
    if "place_offset" not in user_data:
        user_data["place_offset"] = 0
    offset = user_data["place_offset"]
    query_set = models.AgitationPlace.objects.filter(region_id=region_id)
    places = query_set.order_by('-last_update_time')[offset:offset + PLACE_PAGE_SIZE]
    keyboard = [[InlineKeyboardButton("Назад", callback_data=BACK)]]
    for place in places:
        keyboard.append([InlineKeyboardButton(place.address, callback_data=str(place.id))])
    if query_set.count() > offset + PLACE_PAGE_SIZE:
        keyboard.append([InlineKeyboardButton("Вперед", callback_data=FORWARD)])
    send_message_text(bot, update, user_data, "Выберите место", reply_markup=InlineKeyboardMarkup(keyboard))


def select_event_place_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        if user_data['place_offset'] == 0:
            del user_data['place_offset']
            return SET_EVENT_PLACE
        else:
            user_data['place_offset'] -= PLACE_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['place_offset'] += PLACE_PAGE_SIZE
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['place_id'] = int(query.data)
            del user_data['place_offset']
            return SELECT_DATES


def set_place_address_start(bot, update, user_data):
    keyboard = [[InlineKeyboardButton("Назад", callback_data=SET_EVENT_PLACE)]]
    send_message_text(bot, update, user_data, 'Введите адрес', reply_markup=InlineKeyboardMarkup(keyboard))


def set_place_address(bot, update, user_data):
    user_data['address'] = update.message.text
    return SET_PLACE_LOCATION


def set_place_location_start(bot, update, user_data):
    keyboard = [[InlineKeyboardButton("Не указывать", callback_data=SKIP)]]
    send_message_text(bot, update, user_data, 'Отправь геопозицию', reply_markup=InlineKeyboardMarkup(keyboard))


def set_place_location(bot, update, user_data):
    location = update.message.location
    user_data['location'] = {
        'latitude': location.latitude,
        'longitude': location.longitude,
    }
    return SELECT_DATES


def skip_place_location(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == SKIP:
        user_data['location'] = {}
        return SELECT_DATES


def chunks(arr, chunk_len):
    return [arr[i:i + chunk_len] for i in range(0, len(arr), chunk_len)]


def _build_dates_keyboard(user_data):
    dates_dict = user_data['dates_dict']
    buttons = [InlineKeyboardButton(("+ " if value["selected"] else "") + key, callback_data=key)
               for key, value in dates_dict.items()]
    keyboard = chunks(buttons, 5)
    if any([value for value in dates_dict.values() if value["selected"]]):
        keyboard.append([InlineKeyboardButton("Закончить", callback_data=END)])
    else:
        keyboard.append([InlineKeyboardButton("Нужно выбрать хотя бы одну дату", callback_data=TRASH)])
    return InlineKeyboardMarkup(keyboard)


def select_event_dates(bot, update, user_data):
    if 'dates_dict' not in user_data:
        today = date.today()
        dates_dict = collections.OrderedDict()
        for i in range(10):
            cur_date = today + timedelta(days=i)
            cur_date_str = "%02d.%02d" % (cur_date.day, cur_date.month)
            dates_dict[cur_date_str] = {'date': (cur_date.year, cur_date.month, cur_date.day),
                                        'selected': False}
        user_data['dates_dict'] = dates_dict
    send_message_text(bot, update, user_data, 'Выберите дату', reply_markup=_build_dates_keyboard(user_data))


def select_event_dates_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    dates_dict = user_data['dates_dict']
    if query.data == END:
        user_data['dates'] = [value["date"] for value in dates_dict.values() if value["selected"]]
        del user_data['dates_dict']
        return SET_EVENT_TIME
    elif query.data in dates_dict:
        dates_dict[query.data]['selected'] ^= True


def set_event_time_start(bot, update, user_data):
    keyboard = list()
    for c in ['16:00-19:00', '17:00-20:00']:
        keyboard.append([InlineKeyboardButton(c, callback_data=c)])
    send_message_text(bot, update, user_data,
                      'Выберите время (например, "7:00 - 09:59" или "17:00-20:00")',
                      reply_markup=InlineKeyboardMarkup(keyboard))


def set_event_time(bot, update, user_data):
    if update.message:
        text = update.message.text
    else:
        text = update.callback_query.data
    match = re.match("([01]?[0-9]|2[0-3]):([0-5][0-9])\s*-\s*([01]?[0-9]|2[0-3]):([0-5][0-9])", text)
    if bool(match):
        user_data['time_range'] = list(map(int, match.groups()))
        return CREATE_EVENT_SERIES


@region_decorator
def create_event_series(bot, update, user_data, region_id):
    if 'place_id' in user_data:
        place = models.AgitationPlace.objects.get(id=user_data['place_id'])
        place.save()  # for update last_update_time
        del user_data['place_id']
    else:
        location = user_data['location']
        place = models.AgitationPlace(
            region_id=region_id,
            address=user_data['address'],
            geo_latitude=location.get('latitude'),
            geo_longitude=location.get('longitude'),
        )
        place.save()
        del user_data['address']
        del user_data['location']

    if place.region_id != region_id:
        return cancel(bot, update, user_data)

    time_range = user_data['time_range']
    from_seconds = (time_range[0] * 60 + time_range[1]) * 60
    to_seconds = (time_range[2] * 60 + time_range[3]) * 60
    if to_seconds < from_seconds:
        to_seconds += 86400

    events = list()
    for date_tuple in user_data['dates']:
        # TODO timezone
        event_date = date(year=date_tuple[0], month=date_tuple[1], day=date_tuple[2])
        event_datetime = datetime.combine(event_date, datetime.min.time())
        event = models.AgitationEvent(
            place=place,
            start_date=event_datetime + timedelta(seconds=from_seconds),
            end_date=event_datetime + timedelta(seconds=to_seconds),
        )
        event.save()
        events.append(event)
    text = "\n".join(["Добавлено:"] + list(map(operator.methodcaller("show"), events)))
    send_message_text(bot, update, user_data, text, parse_mode="Markdown", reply_markup=_create_back_to_menu_keyboard())

    del user_data['dates']
    del user_data['time_range']


def clear_user_data(user_data, keep_keys=None):
    for key in list(user_data.keys()):
        if not (keep_keys and key in keep_keys):
            del user_data[key]


def cancel(bot, update, user_data):
    clear_user_data(user_data, ['last_bot_message_id', 'region_id'])
    return start(bot, update)


def change_region(bot, update, user_data):
    clear_user_data(user_data, ['last_bot_message_id'])
    return SELECT_REGION


def _create_back_to_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("<< Меню", callback_data=MENU)]])


def help(bot, update):
    update.message.reply_text('Help!', reply_markup=ReplyKeyboardRemove())


def error_handler(bot, update, error):
    logger.error('Update "%s" caused error "%s"' % (update, error))


def run_bot():
    updater = Updater(bot_settings.BOT_TOKEN)

    dp = updater.dispatcher

    # dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    standard_callback_query_handler = CallbackQueryHandler(standard_callback)

    conv_handler = ConversationHandler(
        filters=~Filters.group,
        entry_points=[CommandHandler("start", start)],

        states={
            SET_FULL_NAME: [EmptyHandler(set_full_name_start, pass_user_data=True),
                            MessageHandler(Filters.text, set_full_name, pass_user_data=True)],
            SET_PHONE: [EmptyHandler(set_phone_start, pass_user_data=True),
                        MessageHandler(Filters.text, set_phone, pass_user_data=True)],
            SAVE_PROFILE: [EmptyHandler(save_profile, pass_user_data=True),
                           standard_callback_query_handler],
            SELECT_REGION: [EmptyHandler(select_region, pass_user_data=True),
                            CallbackQueryHandler(select_region_button, pass_user_data=True)],
            ADD_REGION: [EmptyHandler(add_region_start, pass_user_data=True),
                         MessageHandler(Filters.text, add_region, pass_user_data=True)],
            SET_ABILITIES: [EmptyHandler(set_abilities, pass_user_data=True),
                            CallbackQueryHandler(set_abilities_button, pass_user_data=True)],
            SAVE_ABILITIES: [EmptyHandler(save_abilities, pass_user_data=True),
                             standard_callback_query_handler],
            MENU: [EmptyHandler(show_menu, pass_user_data=True), standard_callback_query_handler],
            SCHEDULE: [EmptyHandler(show_schedule, pass_user_data=True), standard_callback_query_handler],
            SHOW_PARTICIPATIONS: [EmptyHandler(show_participations, pass_user_data=True),
                                  standard_callback_query_handler],
            APPLY_TO_AGITATE: [EmptyHandler(apply_to_agitate, pass_user_data=True),
                               CallbackQueryHandler(apply_to_agitate_button, pass_user_data=True)],
            SET_EVENT_PLACE: [EmptyHandler(set_event_place, pass_user_data=True),
                              standard_callback_query_handler],
            SELECT_EVENT_PLACE: [EmptyHandler(select_event_place, pass_user_data=True),
                                 CallbackQueryHandler(select_event_place_button, pass_user_data=True)],
            SET_PLACE_ADDRESS: [EmptyHandler(set_place_address_start, pass_user_data=True),
                                MessageHandler(Filters.text, set_place_address, pass_user_data=True),
                                standard_callback_query_handler],
            SET_PLACE_LOCATION: [EmptyHandler(set_place_location_start, pass_user_data=True),
                                 MessageHandler(Filters.location, set_place_location, pass_user_data=True),
                                 CallbackQueryHandler(skip_place_location, pass_user_data=True)],
            SELECT_DATES: [EmptyHandler(select_event_dates, pass_user_data=True),
                           CallbackQueryHandler(select_event_dates_button, pass_user_data=True)],
            SET_EVENT_TIME: [EmptyHandler(set_event_time_start, pass_user_data=True),
                             MessageHandler(Filters.text, set_event_time, pass_user_data=True),
                             CallbackQueryHandler(set_event_time, pass_user_data=True)],
            CREATE_EVENT_SERIES: [EmptyHandler(create_event_series, pass_user_data=True),
                                  standard_callback_query_handler]
        },
        fallbacks=[CommandHandler('cancel', cancel, pass_user_data=True),
                   CommandHandler("region", change_region, pass_user_data=True)]
    )

    # dp.add_handler(InlineQueryHandler(select_event_place, pass_user_data=True))

    dp.add_handler(conv_handler)

    notifications.register_handlers(dp)

    # log all errors
    dp.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
