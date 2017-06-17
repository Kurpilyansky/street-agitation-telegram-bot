from street_agitation_bot import bot_settings, models

import operator
import re
import collections
from datetime import datetime, date, timedelta
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)
from street_agitation_bot.handlers import (ConversationHandler, EmptyHandler)
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

(MENU,
 BACK, FORWARD, TRASH,
 SCHEDULE,
 SET_EVENT_PLACE, SELECT_EVENT_PLACE,
 SET_PLACE_ADDRESS,
 SET_PLACE_LOCATION, SKIP_PLACE_LOCATION,
 SELECT_DATES, SELECT_DATES_END,
 SET_EVENT_TIME,
 CREATE_EVENT_SERIES) = map(lambda x: "s"+str(x), range(14))


def standard_callback(bot, update):
    query = update.callback_query
    query.answer()
    return query.data


def standard_callback_hide(bot, update):
    query = update.callback_query
    query.edit_message_reply_markup(reply_markup=None)
    query.answer()
    return query.data


def start(bot, update):
    return MENU


def show_menu(bot, update):
    keyboard = list()
    keyboard.append([InlineKeyboardButton('Добавить ивент', callback_data=SET_EVENT_PLACE)])
    keyboard.append([InlineKeyboardButton('Расписание', callback_data=SCHEDULE)])
    update.effective_message.reply_text('Меню', reply_markup=InlineKeyboardMarkup(keyboard))


def show_schedule(bot, update):
    events = list(models.AgitationEvent.objects.all())
    print(events)
    if events:
        schedule_text = "\n".join(map(operator.methodcaller("show"), events))
    else:
        schedule_text = "В ближайшее время пока ничего не запланировано"
    print(schedule_text)
    inline_keyboard_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Меню', callback_data=MENU)]])
    update.callback_query.edit_message_text(schedule_text,
                              parse_mode="Markdown",
                              reply_markup=inline_keyboard_markup)


def set_event_place(bot, update):
    keyboard = [[InlineKeyboardButton('Выбрать место из старых', callback_data=SELECT_EVENT_PLACE)],
                [InlineKeyboardButton('Создать новое место', callback_data=SET_PLACE_ADDRESS)]]
    update.effective_message.edit_text(text="Укажите место", reply_markup=InlineKeyboardMarkup(keyboard))


PLACE_PAGE_SIZE = 5


def select_event_place(bot, update, user_data):
    if "place_offset" not in user_data:
        user_data["place_offset"] = 0
    offset = user_data["place_offset"]
    places = models.AgitationPlace.objects.order_by('-last_update_time')[offset:offset+PLACE_PAGE_SIZE]
    keyboard = [[InlineKeyboardButton("Назад", callback_data=BACK)]]
    for place in places:
        keyboard.append([InlineKeyboardButton(place.address, callback_data=str(place.id))])
    if models.AgitationPlace.objects.count() > offset + PLACE_PAGE_SIZE:
        keyboard.append([InlineKeyboardButton("Вперед", callback_data=FORWARD)])
    update.effective_message.edit_text("Выберите место", reply_markup=InlineKeyboardMarkup(keyboard))


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


def set_place_address_start(bot, update):
    keyboard = [[InlineKeyboardButton("Назад", callback_data=SET_EVENT_PLACE)]]
    update.effective_message.edit_text('Введите адрес', reply_markup=InlineKeyboardMarkup(keyboard))


def set_place_address(bot, update, user_data):
    user_data['address'] = update.message.text
    return SET_PLACE_LOCATION


def set_place_location_start(bot, update):
    keyboard = [[InlineKeyboardButton("Не указывать", callback_data=SKIP_PLACE_LOCATION)]]
    update.message.reply_text('Отправь геопозицию',
                              reply_markup=InlineKeyboardMarkup(keyboard))


def set_place_location(bot, update, user_data):
    user_data['location'] = update.message.location
    return SELECT_DATES


def skip_place_location(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == SKIP_PLACE_LOCATION:
        user_data['location'] = None
        return SELECT_DATES


def chunks(arr, chunk_len):
    return [arr[i:i + chunk_len] for i in range(0, len(arr), chunk_len)]


def _build_dates_keyboard(user_data):
    dates_dict = user_data['dates_dict']
    buttons = [InlineKeyboardButton(("- " if value["selected"] else "") + key, callback_data=key)
               for key, value in dates_dict.items()]
    keyboard = chunks(buttons, 5)
    if any([value for value in dates_dict.values() if value["selected"]]):
        keyboard.append([InlineKeyboardButton("Закончить", callback_data=SELECT_DATES_END)])
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
    if update.callback_query:
        update.effective_message.edit_text('Выберите дату', reply_markup=_build_dates_keyboard(user_data))
    else:
        update.effective_message.reply_text('Выберите дату', reply_markup=_build_dates_keyboard(user_data))


def select_event_dates_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    dates_dict = user_data['dates_dict']
    if query.data == SELECT_DATES_END:
        user_data['dates'] = [value["date"] for value in dates_dict.values() if value["selected"]]
        del user_data['dates_dict']
        return SET_EVENT_TIME
    elif query.data in dates_dict:
        dates_dict[query.data]['selected'] ^= True


def set_event_time_start(bot, update):
    keyboard = list()
    for c in ['16:00-19:00', '17:00-20:00']:
        keyboard.append([InlineKeyboardButton(c, callback_data=c)])
    update.effective_message.edit_text('Выберите время (например, "7:00 - 09:59" или "17:00-20:00")',
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


def create_event_series(bot, update, user_data):
    if 'place_id' in user_data:
        place = models.AgitationPlace.objects.get(id=user_data['place_id'])
        place.save()  # for update last_update_time
        del user_data['place_id']
    else:
        location = user_data['location']
        place = models.AgitationPlace(
            address=user_data['address'],
            geo_latitude=location.latitude if location else None,
            geo_longitude=location.longitude if location else None
        )
        place.save()
        del user_data['address']
        del user_data['location']

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
    inline_keyboard_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Меню", callback_data=MENU)]])
    update.effective_message.edit_text(text,
                                       parse_mode="Markdown",
                                       reply_markup=inline_keyboard_markup)

    del user_data['dates']
    del user_data['time_range']


def cancel(bot, update, user_data):
    user_data.clear()
    return MENU


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
    standard_callback_query_handler2 = CallbackQueryHandler(standard_callback_hide)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],

        states={
            MENU: [EmptyHandler(show_menu), standard_callback_query_handler],
            SCHEDULE: [EmptyHandler(show_schedule), standard_callback_query_handler2],
            SET_EVENT_PLACE: [EmptyHandler(set_event_place), standard_callback_query_handler],
            SELECT_EVENT_PLACE: [EmptyHandler(select_event_place, pass_user_data=True),
                                 CallbackQueryHandler(select_event_place_button, pass_user_data=True)],
            SET_PLACE_ADDRESS: [EmptyHandler(set_place_address_start),
                                MessageHandler(Filters.text, set_place_address, pass_user_data=True),
                                standard_callback_query_handler],
            SET_PLACE_LOCATION: [EmptyHandler(set_place_location_start),
                                 MessageHandler(Filters.location, set_place_location, pass_user_data=True),
                                 CallbackQueryHandler(skip_place_location, pass_user_data=True)],
            SELECT_DATES: [EmptyHandler(select_event_dates, pass_user_data=True),
                           CallbackQueryHandler(select_event_dates_button, pass_user_data=True)],
            SET_EVENT_TIME: [EmptyHandler(set_event_time_start),
                             MessageHandler(Filters.text, set_event_time, pass_user_data=True),
                             CallbackQueryHandler(set_event_time, pass_user_data=True)],
            CREATE_EVENT_SERIES: [EmptyHandler(create_event_series, pass_user_data=True),
                                  standard_callback_query_handler2]
        },
        fallbacks=[CommandHandler('cancel', cancel, pass_user_data=True)]
    )

    # dp.add_handler(InlineQueryHandler(select_event_place, pass_user_data=True))

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
