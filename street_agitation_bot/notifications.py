
from street_agitation_bot import models, utils
from street_agitation_bot.emoji import *

from street_agitation_bot.bot_constants import *

import telegram
from telegram import (InlineKeyboardButton, InlineKeyboardMarkup)

from telegram.ext import CallbackQueryHandler


PARTICIPANT_CONFIRM = 'PARTICIPANT_CONFIRM'
PARTICIPANT_DECLINE = 'PARTICIPANT_DECLINE'


def edit_participant_message(message, participant):
    keyboard = [[InlineKeyboardButton('Подтвердить',
                                      callback_data=PARTICIPANT_CONFIRM + str(participant.id))],
                [InlineKeyboardButton('Отклонить',
                                      callback_data=PARTICIPANT_DECLINE + str(participant.id))]]

    try:
        message.edit_text('%s\nРегион %s\n%s %s\nВолонтер %s'
                          % (participant.emoji_status(True),
                             participant.place.region.show(), participant.event.show(),
                             participant.place.show(), participant.agitator.show(private=True)),
                          parse_mode='Markdown',
                          reply_markup=InlineKeyboardMarkup(keyboard))
    except telegram.error.BadRequest:
        pass  ## ignore 'Message is not modified'


def participant_button(bot, update, groups):
    query = update.callback_query

    participant_id = groups[1]
    participant = (models.AgitationEventParticipant.objects.filter(id=participant_id)
                   .select_related('agitator', 'event', 'event__place').first())
    if not participant:
        query.answer(text='Данная заявка не найдена. Что-то пошло не так :(', show_alert=True)
        return
    user_telegram_id = update.effective_user.id
    if not models.AdminRights.has_admin_rights_for_event(user_telegram_id, participant.event):
        query.answer(text='У вас нет прав на это действие', show_alert=True)
        return

    query.answer()
    if groups[0] == PARTICIPANT_CONFIRM:
        participant.make_approve()
    elif groups[0] == PARTICIPANT_DECLINE:
        participant.make_decline()

    edit_participant_message(query.message, participant)


def register_handlers(dispatcher):
    dispatcher.add_handler(CallbackQueryHandler(participant_button,
                                                pattern='(%s|%s)(\d+)'
                                                        % (PARTICIPANT_CONFIRM, PARTICIPANT_DECLINE),
                                                pass_groups=True))


def notify_about_new_registration(bot, region_id, user, text):
    region = models.Region.get_by_id(region_id)
    if region.registrations_chat_id:
        bot.send_message(region.registrations_chat_id,
                         'Новая анкета\nРегион %s\n%s%s'
                         % (region.show(), user.show(private=True), text),
                         parse_mode="Markdown")


def _notify_about_participant(bot, participant_id, text):
    participant = models.AgitationEventParticipant.objects.filter(
                    id=participant_id
                  ).select_related('place', 'event', 'agitator').first()
    if not participant:
        return
    event = participant.event
    place = participant.place
    agitator = participant.agitator
    region = event.place.region
    keyboard = [[InlineKeyboardButton('Подтвердить', callback_data=PARTICIPANT_CONFIRM + str(participant.id))],
                [InlineKeyboardButton('Отклонить', callback_data=PARTICIPANT_DECLINE + str(participant.id))]]
    chat_ids = []
    if region.registrations_chat_id:
        chat_ids.append(region.registrations_chat_id)
    if event.place.registrations_chat_id:
        chat_ids = [event.place.registrations_chat_id]
        if place.registrations_chat_id:
            chat_ids.append(place.registrations_chat_id)
    full_text = '%s %s\nРегион %s\n%s %s' % (
        agitator.show(private=True), text, region.show(), event.show(), place.show())
    for chat_id in chat_ids:
        bot.send_message(chat_id,
                         text=full_text,
                         parse_mode='Markdown',
                         reply_markup=InlineKeyboardMarkup(keyboard))
    if event.master.telegram_id:
        bot.send_message(event.master.telegram_id,
                         text='%s %s в %s %s' % (agitator.show(), text, event.show(), place.show()),
                         parse_mode='Markdown',
                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                             'Посмотреть все заявки', callback_data=SHOW_EVENT_FOR_MASTER+str(event.id))]]))


def notify_about_new_participant(bot, participant_id):
    _notify_about_participant(bot, participant_id, 'подал заявку на участие')


def notify_about_cancellation_participation(bot, participant_id):
    _notify_about_participant(bot, participant_id, 'отменил заявку на участие')


def notify_about_restoration_participation(bot, participant_id):
    _notify_about_participant(bot, participant_id, 'восстановил заявку на участие')


def notify_about_cube_usage(bot, event_id):
    event = models.AgitationEvent.objects.filter(id=event_id).select_related(
        'cubeusageinevent', 'master', 'place__region').first()
    if not event or not event.cube_usage:
        return
    cube_usage = event.cubeusageinevent
    bot.send_message(event.place.region.registrations_chat_id,
                     'Новая информация о %s %s\n%s' % (event.show(), event.place.show(),
                                                       cube_usage.show(private=True)),
                     parse_mode='Markdown')
    bot.send_message(event.master.telegram_id,
                     'Новая информация о %s %s\n%s' % (event.show(), event.place.show(),
                                                       cube_usage.show(private=True)),
                     parse_mode='Markdown')
