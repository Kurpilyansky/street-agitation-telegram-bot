from street_agitation_bot import bot_settings, models

import operator
import re
import collections
from datetime import datetime, date, timedelta
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler, CallbackQueryHandler, InlineQueryHandler)
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

(MENU,
 SET_EVENT_PLACE, SELECT_EVENT_PLACE,
 SET_ADDRESS, SET_LOCATION, SELECT_DATES, SELECT_DATES_END, SET_TIME) = map(str, range(8))


def start(bot, update):
    reply_markup = ReplyKeyboardMarkup([[u'Добавить ивент'], [u'Расписание']], one_time_keyboard=True)
    update.message.reply_text('Что сделать?', reply_markup=reply_markup)
    return MENU


def show_schedule(bot, update):
    events = list(models.AgitationEvent.objects.all())
    print(events)
    if events:
        schedule_text = "\n".join(map(operator.methodcaller("show"), events))
    else:
        schedule_text = "В ближайшее время пока ничего не запланировано"
    print(schedule_text)
    update.message.reply_text(schedule_text, parse_mode="Markdown")


def process_menu_command(bot, update):
    text = update.message.text
    if text == u'Добавить ивент':
        return _send_set_event_place(bot, update)
    elif text == u'Расписание':
        show_schedule(bot, update)
        return MENU


def _send_set_event_place(bot, update):
    reply_markup = ReplyKeyboardMarkup([[u'Выбрать место из старых'], [u'Создать новое место']],
                                       one_time_keyboard=True)
    update.message.reply_text(text="Укажите место", reply_markup=reply_markup)
    return SET_EVENT_PLACE


PLACE_PAGE_SIZE = 5


def _send_select_event_place(bot, update, user_data):
    offset = user_data["place_offset"]
    places = models.AgitationPlace.objects.order_by('-last_update_time')[offset:offset+PLACE_PAGE_SIZE]
    buttons = [["Назад"]] + list(map(lambda x: ["#%d. %s" % (x.id, x.address)], places))
    if models.AgitationPlace.objects.count() > offset + PLACE_PAGE_SIZE:
        buttons.append(["Вперед"])
    reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True)
    update.message.reply_text("Выберите место", reply_markup=reply_markup)


def set_event_place(bot, update, user_data):
    text = update.message.text
    if text == u'Создать новое место':
        update.message.reply_text(text="Введите адрес", reply_markup=ReplyKeyboardRemove())
        return SET_ADDRESS
    elif text == u'Выбрать место из старых':
        user_data["place_offset"] = 0
        _send_select_event_place(bot, update, user_data)
        return SELECT_EVENT_PLACE


def select_event_place(bot, update, user_data):
    text = update.message.text
    if text == 'Назад':
        if user_data['place_offset'] == 0:
            return _send_set_event_place(bot, update)
        else:
            user_data['place_offset'] -= PLACE_PAGE_SIZE
            _send_select_event_place(bot, update, user_data)
    elif text == 'Вперед':
        user_data['place_offset'] += PLACE_PAGE_SIZE
        _send_select_event_place(bot, update, user_data)
    else:
        match = re.match('^#(\d+)\.', text)
        if bool(match):
            user_data['place_id'] = int(match.group(1))
            _send_after_set_location(bot, update, user_data)
            return SELECT_DATES


# def select_event_place(bot, update, user_data):
#     query = update.inline_query.query
#     places = list(models.AgitationPlace.objects.filter(address__icontains=query)[:10])
#     results = list()
#     for place in places:
#         results.append(InlineQueryResultArticle(id=place.id,
#                                                 title=place.address,
#                                                 input_message_content='#%d. %s' % (place.id, place.address)))
#     update.inline_query.answer(results)


def set_place_address(bot, update, user_data):
    user_data['address'] = update.message.text
    update.message.reply_text('Отправь геопозицию, или пропусти этот шаг, нажав /skip.',
                              reply_markup=ReplyKeyboardRemove())
    return SET_LOCATION


def chunks(arr, chunk_len):
    return [arr[i:i + chunk_len] for i in range(0, len(arr), chunk_len)]


def _build_dates_keyboard(user_data):
    dates_dict = user_data['dates_dict']
    buttons = [InlineKeyboardButton(("- " if value["set"] else "") + key, callback_data=key)
               for key, value in dates_dict.items()]
    keyboard = chunks(buttons, 5)
    if any([value for value in dates_dict.values() if value["set"]]):
        keyboard.append([InlineKeyboardButton("Закончить", callback_data=SELECT_DATES_END)])
    else:
        keyboard.append([InlineKeyboardButton("Выберите хотя бы одну дату", callback_data="--trash--")])
    return InlineKeyboardMarkup(keyboard)


def dates_keyboard_button(bot, update, user_data):
    query = update.callback_query
    button_data = query.data

    dates_dict = user_data['dates_dict']
    if button_data == SELECT_DATES_END:
        selected = [key for key, value in dates_dict.items() if value["set"]]
        reply_markup = ReplyKeyboardMarkup([[u'Выбрать даты: ' + ' '.join(selected)],
                                            [u'Вернуться к выбору дат']],
                                           one_time_keyboard=True)
        bot.delete_message(chat_id=query.message.chat_id,
                           message_id=query.message.message_id)
        ## TODO without this additional step
        query.message.reply_text('Подтвердите выбор', reply_markup=reply_markup)
    elif button_data in dates_dict:
        dates_dict[button_data]['set'] ^= True
        bot.edit_message_reply_markup(reply_markup=_build_dates_keyboard(user_data),
                                      chat_id=query.message.chat_id,
                                      message_id=query.message.message_id)


def back_to_select_dates(bot, update, user_data):
    reply_markup = _build_dates_keyboard(user_data)
    update.message.reply_text('Выберите дату', reply_markup=reply_markup)
    return SELECT_DATES


def _send_after_set_location(bot, update, user_data):
    today = date.today()
    dates_dict = collections.OrderedDict()
    for i in range(10):
        cur_date = today + timedelta(days=i)
        cur_date_str = "%02d.%02d" % (cur_date.day, cur_date.month)
        dates_dict[cur_date_str] = {'date': cur_date, 'set': False}
    user_data['dates_dict'] = dates_dict
    reply_markup = _build_dates_keyboard(user_data)
    update.message.reply_text('Выберите дату', reply_markup=reply_markup)
    return SELECT_DATES


def set_place_location(bot, update, user_data):
    user_data['location'] = update.message.location
    return _send_after_set_location(bot, update, user_data)


def skip_place_location(bot, update, user_data):
    user_data['location'] = None
    return _send_after_set_location(bot, update, user_data)


def set_event_dates(bot, update, user_data):
    dates_dict = user_data['dates_dict']
    date_keys = update.message.text.split(': ')[1].split(" ")
    user_data['dates'] = [dates_dict[key]['date'] for key in date_keys]
    del user_data['dates_dict']
    update.message.reply_text('Выберите время (например, "7:00 - 09:59" или "17:00-20:00")',
                              reply_markup=ReplyKeyboardMarkup([['16:00-19:00', '17:00-20:00']]))
    return SET_TIME


def _create_event_series(user_data):
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

    for event_date in user_data['dates']:
        # TODO timezone
        event_datetime = datetime.combine(event_date, datetime.min.time())
        models.AgitationEvent(
            place=place,
            start_date=event_datetime + timedelta(seconds=from_seconds),
            end_date=event_datetime + timedelta(seconds=to_seconds),
        ).save()

    del user_data['dates']
    del user_data['time_range']


def set_event_time(bot, update, user_data):
    text = update.message.text
    match = re.match("([01]?[0-9]|2[0-3]):([0-5][0-9])\s*-\s*([01]?[0-9]|2[0-3]):([0-5][0-9])", text)
    if bool(match):
        user_data['time_range'] = list(map(int, match.groups()))
        update.message.reply_text(str(user_data), reply_markup=ReplyKeyboardRemove())
        _create_event_series(user_data)
        return ConversationHandler.END


def help(bot, update):
    update.message.reply_text('Help!')


def echo(bot, update):
    update.message.reply_text(update.message.text)


def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def run_bot():
    updater = Updater(bot_settings.BOT_TOKEN)

    dp = updater.dispatcher

    # dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],

        states={
            MENU: [MessageHandler(Filters.text, process_menu_command)],
            SET_EVENT_PLACE: [MessageHandler(Filters.text, set_event_place, pass_user_data=True)],
            SELECT_EVENT_PLACE: [MessageHandler(Filters.text, select_event_place, pass_user_data=True)],
            SET_ADDRESS: [MessageHandler(Filters.text, set_place_address, pass_user_data=True)],
            SET_LOCATION: [MessageHandler(Filters.location, set_place_location, pass_user_data=True),
                           CommandHandler("skip", skip_place_location, pass_user_data=True)],
            SELECT_DATES: [RegexHandler("^Выбрать даты:", set_event_dates, pass_user_data=True),
                           RegexHandler("^Вернуться к выбору дат$", back_to_select_dates, pass_user_data=True)],
            SET_TIME: [MessageHandler(Filters.text, set_event_time, pass_user_data=True)]
        },
        fallbacks=[  # CommandHandler('cancel', cancel),
        ]
    )

    dp.add_handler(CallbackQueryHandler(dates_keyboard_button, pass_user_data=True))
    # dp.add_handler(InlineQueryHandler(select_event_place, pass_user_data=True))

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
