import settings

import re
import collections
from datetime import date, timedelta
from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler, CallbackQueryHandler)
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

(MENU,
 SET_EVENT_PLACE, CHOOSE_EVENT_PLACE, CREATE_EVENT_PLACE,
 SET_ADDRESS, SET_LOCATION, SELECT_DATES, SELECT_DATES_END, SET_TIME) = map(str, range(9))


def start(bot, update):
    reply_markup = ReplyKeyboardMarkup([[u'Добавить ивент']], one_time_keyboard=True)
    update.message.reply_text('Что сделать?', reply_markup=reply_markup)
    return MENU


def process_menu_command(bot, update):
    text = update.message.text
    if text == u'Добавить ивент':
        reply_markup = ReplyKeyboardMarkup([[u'Выбрать место из старых'], [u'Создать новое место']],
                                           one_time_keyboard=True)

        update.message.reply_text(text="Укажите место", reply_markup=reply_markup)
        return SET_EVENT_PLACE


def set_event_place(bot, update):
    text = update.message.text
    if text == u'Создать новое место':
        update.message.reply_text(text="Введите адрес", reply_markup=ReplyKeyboardRemove())
        return SET_ADDRESS


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
    return _send_after_set_location(bot, update, user_data)


def set_event_dates(bot, update, user_data):
    dates_dict = user_data['dates_dict']
    date_keys = update.message.text.split(': ')[1].split(" ")
    user_data['dates'] = [dates_dict[key]['date'] for key in date_keys]
    del user_data['dates_dict']
    update.message.reply_text('Выберите время (например, "7:00 - 09:59" или "17:00-20:00")',
                              reply_markup=ReplyKeyboardMarkup([['16:00-19:00', '17:00-20:00']]))
    return SET_TIME


def set_event_time(bot, update, user_data):
    text = update.message.text
    match = re.match("([01]?[0-9]|2[0-3]):([0-5][0-9])\s*-\s*([01]?[0-9]|2[0-3]):([0-5][0-9])", text)
    if bool(match):
        user_data['time_range'] = list(map(int, match.groups()))
        update.message.reply_text(str(user_data), reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


def help(bot, update):
    update.message.reply_text('Help!')


def echo(bot, update):
    update.message.reply_text(update.message.text)


def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def main():
    updater = Updater(settings.BOT_TOKEN)

    dp = updater.dispatcher

    # dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],

        states={
            MENU: [MessageHandler(Filters.text, process_menu_command)],
            SET_EVENT_PLACE: [MessageHandler(Filters.text, set_event_place)],
            SET_ADDRESS: [MessageHandler(Filters.text, set_place_address, pass_user_data=True)],
            SET_LOCATION: [MessageHandler(Filters.location, set_place_location, pass_user_data=True),
                           CommandHandler("skip", skip_place_location, pass_user_data=True)],
            SELECT_DATES: [RegexHandler("^Выбрать даты:", set_event_dates, pass_user_data=True),
                           RegexHandler("^Вернуться к выбору дат$", back_to_select_dates, pass_user_data=True)],
            SET_TIME: [MessageHandler(Filters.text, set_event_time, pass_user_data=True)]
        },
        fallbacks=[#CommandHandler('cancel', cancel),
                   ]
    )

    dp.add_handler(CallbackQueryHandler(dates_keyboard_button, pass_user_data=True))

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
