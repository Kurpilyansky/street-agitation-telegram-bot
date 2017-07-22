
from street_agitation_bot import models, utils
from street_agitation_bot.emoji import *

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup)

from telegram.ext import CallbackQueryHandler


PARTICIPANT_CONFIRM = 'PARTICIPANT_CONFIRM'
PARTICIPANT_DECLINE = 'PARTICIPANT_DECLINE'


def participant_button(bot, update, groups):
    query = update.callback_query

    participant_id = groups[1]
    participant = (models.AgitationEventParticipant.objects.filter(id=participant_id)
                   .select_related('agitator', 'event', 'event__place', 'event__place__region').first())
    if not participant:
        query.answer(text='Данная заявка не найдена. Что-то пошло не так :(', show_alert=True)
        return
    agitator = participant.agitator
    event = participant.event
    place = participant.place
    region = place.region
    if participant.canceled:
        query.message.edit_text('%s Заявка отменена\nРегион %s\n%s %s\nВолонтер %s'
                                % (participant.emoji_status, region.show(), event.show(), place.show(), agitator.show_full()),
                                parse_mode='Markdown')
        return
    agitator_in_region = models.AgitatorInRegion.get(region.id, update.effective_user.id)
    if not (agitator_in_region and agitator_in_region.is_admin):
        query.answer(text='У вас нет прав на это действие', show_alert=True)
        return

    query.answer()
    if groups[0] == PARTICIPANT_CONFIRM:
        models.AgitationEventParticipant.approve(id=participant_id)
        keyboard = [[InlineKeyboardButton(EMOJI_OK + ' Подтвердить',
                                          callback_data=PARTICIPANT_CONFIRM + participant_id)],
                    [InlineKeyboardButton('Отклонить',
                                          callback_data=PARTICIPANT_DECLINE + participant_id)]]
    # elif groups[1] == PARTICIPANT_DECLINE:
    else:
        models.AgitationEventParticipant.decline(id=participant_id)
        keyboard = [[InlineKeyboardButton('Подтвердить',
                                          callback_data=PARTICIPANT_CONFIRM + participant_id)],
                    [InlineKeyboardButton(EMOJI_NO + ' Отклонить',
                                          callback_data=PARTICIPANT_DECLINE + participant_id)]]

    query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


def register_handlers(dispatcher):
    dispatcher.add_handler(CallbackQueryHandler(participant_button,
                                                pattern='(%s|%s)(\d+)'
                                                        % (PARTICIPANT_CONFIRM, PARTICIPANT_DECLINE),
                                                pass_groups=True))


def notify_about_new_registration(bot, region_id, agitator_id, text):
    region = models.Region.get_by_id(region_id)
    agitator = models.Agitator.find_by_id(agitator_id)
    bot.send_message(region.registrations_chat_it,
                     'Новая анкета\nРегион %s\n%s%s'
                     % (region.show(), agitator.show_full(), text),
                     parse_mode="Markdown")


def notify_about_new_participant(bot, event_id, place_id, agitator_id):
    agitator = models.Agitator.find_by_id(agitator_id)
    event = (models.AgitationEvent.objects.filter(id=event_id)
             .select_related('place', 'place__region').first())
    place = models.AgitationPlace.objects.filter(id=place_id).first()
    participant = models.AgitationEventParticipant.get(agitator_id, event.id)
    region = event.place.region
    keyboard = [[InlineKeyboardButton('Подтвердить', callback_data=PARTICIPANT_CONFIRM + str(participant.id))],
                [InlineKeyboardButton('Отклонить', callback_data=PARTICIPANT_DECLINE + str(participant.id))]]
    bot.send_message(region.registrations_chat_it,
                     'Новая заявка на участие\nРегион %s\n%s %s\nВолонтер %s'
                     % (region.show(), event.show(), place.show(), agitator.show_full()),
                     parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(keyboard))
