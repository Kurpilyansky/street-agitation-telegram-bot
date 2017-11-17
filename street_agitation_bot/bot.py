from django.db.models import Q

from street_agitation_bot import bot_settings, models, notifications, utils, cron, admin_commands
from street_agitation_bot.emoji import *

import traceback

import re
import collections
from datetime import datetime, date, timedelta
from telegram import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)
from street_agitation_bot.bot_constants import *
from street_agitation_bot.handlers import (ConversationHandler, EmptyHandler)
import logging

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


def region_decorator(func):
    def wrapper(bot, update, user_data, *args, **kwargs):
        if 'region_id' not in user_data:
            return change_region(bot, update, user_data)
        return func(bot, update, user_data, region_id=int(user_data['region_id']), *args, **kwargs)

    return wrapper


def has_admin_rights(func):
    def wrapper(bot, update, user_data, *args, **kwargs):
        if 'region_id' not in user_data:
            return change_region(bot, update, user_data)
        region_id = user_data['region_id']
        user_telegram_id = update.effective_user.id
        if not models.AdminRights.has_admin_rights(user_telegram_id, region_id):
            return cancel(bot, update, user_data)
        return func(bot, update, user_data, *args, **kwargs)

    return wrapper


def send_message_text(bot, update, user_data, *args, **kwargs):
    last_bot_message_ids = user_data.get('last_bot_message_id', None)
    if not last_bot_message_ids:
        last_bot_message_ids = []
    elif not isinstance(last_bot_message_ids, list):
        last_bot_message_ids = [last_bot_message_ids]

    user_data.pop('last_bot_message_id', None)
    user_data.pop('last_bot_message_ts', None)
    location = kwargs.get('location', {})
    kwargs.pop('location', None)
    cur_ts = datetime.utcnow().timestamp()
    for message_id in last_bot_message_ids:
        utils.safe_delete_message(bot, update.effective_user.id, message_id)
    new_message_ids = []
    if location:
        kwargs2 = kwargs.copy()
        if args:
            kwargs2.pop('reply_markup', None)
        new_message = bot.send_location(update.effective_user.id, location['latitude'], location['longitude'], **kwargs2)
        new_message_ids.append(new_message.message_id)
    if args:
        new_message = bot.send_message(update.effective_user.id, *args, **kwargs)
        new_message_ids.append(new_message.message_id)
    user_data['last_bot_message_id'] = new_message_ids
    user_data['last_bot_message_ts'] = cur_ts


def standard_callback(bot, update):
    query = update.callback_query
    query.answer()
    return query.data


def start(bot, update):
    if models.User.find_by_telegram_id(update.effective_user.id):
        return MENU
    else:
        return SET_LAST_NAME


def set_last_name_start(bot, update, user_data):
    text = 'Укажите вашу фамилию'
    if not models.User.find_by_telegram_id(update.effective_user.id):
        text = 'Пожалуйста, оставьте ваши контакты. Сделайте это сейчас, даже если на данный момент ' \
               'вы не готовы помогать. Ваши данные будут использованы только для связи с вами.\n\n' + text
    send_message_text(bot, update, user_data, text)


def set_last_name(bot, update, user_data):
    user_data["last_name"] = update.message.text
    return SET_FIRST_NAME


def set_first_name_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите ваше имя')


def set_first_name(bot, update, user_data):
    user_data["first_name"] = update.message.text
    return SET_PHONE


def set_phone_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите ваш телефон',
                      reply_markup=ReplyKeyboardMarkup([[KeyboardButton('Отправить мой номер телефона', request_contact=True)]]))


def set_phone_contact(bot, update, user_data):
    user_data["phone"] = update.message.contact.phone_number
    return SAVE_PROFILE


def set_phone_text(bot, update, user_data):
    user_data["phone"] = update.message.text
    return SAVE_PROFILE


def save_profile(bot, update, user_data):
    user = update.effective_user
    user, created = models.User.update_or_create(
        params={'telegram_id': user.id,
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'phone': user_data.get('phone'),
                'telegram': user.username})
    # TODO handle excetion 'User collisions'

    text = 'Спасибо за регистрацию!' if created else 'Данные профиля обновлены'
    if 'region_id' in user_data:
        keyboard = _create_back_to_menu_keyboard()
        keyboard.inline_keyboard[0:0] = [[InlineKeyboardButton('Настройки', callback_data=SHOW_PROFILE)]]
    else:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('Выбрать регион', callback_data=SELECT_REGION)]])
    send_message_text(bot, update, user_data, text, reply_markup=ReplyKeyboardRemove())
    send_message_text(bot, update, user_data, text, reply_markup=keyboard)

    del user_data['first_name']
    del user_data['last_name']
    del user_data['phone']


@region_decorator
def show_profile(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    user = models.User.find_by_telegram_id(user_telegram_id)
    if not user:
        return SET_LAST_NAME
    agitator_in_region = models.AgitatorInRegion.get(region_id, user_telegram_id)
    if not agitator_in_region:
        return SET_ABILITIES
    profile = '*Настройки*\nФамилия %s\nИмя %s\nТелефон %s' % (user.last_name, user.first_name, user.phone)
    abilities = _prepare_abilities_text(agitator_in_region.get_abilities_dict())
    keyboard = _create_back_to_menu_keyboard()
    keyboard.inline_keyboard[0:0] = [[InlineKeyboardButton('Редактировать профиль', callback_data=SET_LAST_NAME)],
                                     [InlineKeyboardButton('Редактировать «умения»', callback_data=SET_ABILITIES)]]
    send_message_text(bot, update, user_data, '\n'.join((profile, abilities)), parse_mode='Markdown', reply_markup=keyboard)


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
        return SET_LAST_NAME
    keyboard = _build_add_region_keyboard(update, user_data)
    send_message_text(bot, update, user_data,
                      'Выберите региональный штаб',
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
        text = (EMOJI_OK + " " if val else "") + ABILITIES_TEXTS[key]
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
    user_telegram_id = update.effective_user.id
    user = models.User.find_by_telegram_id(user_telegram_id)
    text = _prepare_abilities_text(user_data['abilities'])
    obj, created = models.AgitatorInRegion.save_abilities(region_id, user, user_data['abilities'])
    keyboard = _create_back_to_menu_keyboard()
    keyboard.inline_keyboard[0:0] = [[InlineKeyboardButton('Настройки', callback_data=SHOW_PROFILE)]]
    send_message_text(bot, update, user_data,
                      'Данные сохранены' + text,
                      parse_mode="Markdown",
                      reply_markup=keyboard)
    if created:
        notifications.notify_about_new_registration(bot, region_id, user, text)
    del user_data['abilities']


def _prepare_abilities_text(abilities):
    text = ''
    for key, val in abilities.items():
        text += "\n%s: %s" % (ABILITIES_TEXTS[key], "*да*" if val else "нет")
    return text


def show_menu(bot, update, user_data):
    keyboard = list()
    if 'region_id' in user_data:
        keyboard.append([InlineKeyboardButton('Расписание', callback_data=SCHEDULE)])
        keyboard.append([InlineKeyboardButton('Записаться', callback_data=APPLY_TO_AGITATE)])
        region_id = user_data['region_id']
        region = models.Region.get_by_id(region_id)
        user_telegram_id = update.effective_user.id
        abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
        if not abilities:
            return SET_ABILITIES
        if abilities.can_be_applicant:
            keyboard.append([InlineKeyboardButton('Заявить новый куб', callback_data=CUBE_APPLICATION)])
        if models.AgitationEventParticipant.objects.filter(
                                        agitator__telegram_id=user_telegram_id,
                                        event__start_date__gte=date.today()).exists():
            keyboard.append([InlineKeyboardButton('Мои заявки', callback_data=SHOW_PARTICIPATIONS)])
        keyboard.append([InlineKeyboardButton('Настройки', callback_data=SHOW_PROFILE)])
        if models.AdminRights.has_admin_rights(user_telegram_id, region_id):
            keyboard.append([InlineKeyboardButton('Добавить ивент', callback_data=SET_EVENT_NAME)])
            keyboard.append([InlineKeyboardButton('Управление ивентами', callback_data=MANAGE_EVENTS)])
            if region.settings.enabled_cube_logistics:
                keyboard.append([InlineKeyboardButton('Логистика', callback_data=MANAGE_CUBES)])
            keyboard.append([InlineKeyboardButton('Сделать рассылку', callback_data=MAKE_BROADCAST)])
            keyboard.append([InlineKeyboardButton('Настройки штаба', callback_data=SHOW_REGION_SETTINGS)])
    else:
        return SELECT_REGION
    send_message_text(bot, update, user_data, '*Меню*\nВыберите действие для продолжения работы', parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def make_broadcast_start(bot, update, user_data):
    send_message_text(bot, update, user_data,
                      '*Отправьте сообщение, и оно будет отправлено всем пользователям*',
                      parse_mode='Markdown')


@has_admin_rights
def make_broadcast(bot, update, user_data):
    user_data['broadcast_text'] = update.message.text
    return MAKE_BROADCAST_CONFIRM


@has_admin_rights
def make_broadcast_confirm(bot, update, user_data):
    broadcast_text = user_data['broadcast_text']
    text = 'Вы уверены, что хотите отправить *всем пользователям вашего региона* следующее сообщение:\n\n%s' % broadcast_text
    keyboard = [[InlineKeyboardButton('Отправить', callback_data=YES),
                 InlineKeyboardButton('Отмена', callback_data=NO)]]
    send_message_text(bot, update, user_data, text,
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
                reply_markup = None
                if bot_settings.is_admin_user_id(update.effective_user.id):
                    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Записаться', callback_data=FORCE_BUTTON + '_' + APPLY_TO_AGITATE)]])
                bot.send_message(u.telegram_id, cur_text, parse_mode='Markdown', reply_markup=reply_markup)
            except TelegramError as e:
                logger.error(e, exc_info=1)
                errors.append(e)
        return MENU
    else:
        return MENU


@region_decorator
def show_schedule(bot, update, user_data, region_id):
    events = list(models.AgitationEvent.objects.filter(
        end_date__gte=datetime.utcnow(),
        place__region_id=region_id,
        is_canceled=False
    ).select_related('place', 'place__region'))
    if events:
        schedule_text = "\n".join(['%s %s' % (e.show(), e.place.show()) for e in events])
    else:
        schedule_text = "В ближайшее время пока ничего не запланировано"
    schedule_text = "*Расписание*\n" + schedule_text
    keyboard = _create_back_to_menu_keyboard()
    if events:
        keyboard.inline_keyboard[0:0] = [[InlineKeyboardButton('Записаться', callback_data=APPLY_TO_AGITATE)]]
    send_message_text(bot, update, user_data,
                      schedule_text,
                      parse_mode="Markdown",
                      reply_markup=keyboard)


def cube_application(bot, update, user_data):
    text = 'Если вы готовы стать заявителем куба, то вам нужно заполнить эту форму ' \
           'и подать её в администрацию вашего района. https://goo.gl/2ZsoGX'  #TODO make a document
    send_message_text(bot, update, user_data, text, reply_markup=_create_back_to_menu_keyboard())


@region_decorator
def show_participations(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    participations = models.AgitationEventParticipant.objects.filter(
        agitator__telegram_id=user_telegram_id,
        event__start_date__gte=date.today(),
    ).select_related('event', 'event__place', 'event__place__region').order_by('event__start_date').all()
    keyboard = list()
    if participations:
        for p in participations:
            p_text = p.emoji_status() + " " + p.event.show(markdown=False) + " " + p.place.show(markdown=False)
            if p.event.place.region_id != region_id:
                p_text = '*%s* %s' % (p.event.place.region.name, p_text)
            keyboard.append([InlineKeyboardButton(p_text, callback_data=str(p.event_id))])
        text = "*Вы записались на следующие мероприятия*"
    else:
        text = "Вы не записались ни на одно мероприятие в будущем"
    keyboard.append([InlineKeyboardButton("<< Меню", callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      text,
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def show_participations_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == MENU:
        return query.data
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['event_id'] = int(query.data)
            return SHOW_EVENT_PARTICIPANTS


def _back_from_show_event_participants(user_data):
    user_data.pop('event_id', None)
    user_data.pop('participant_id', None)
    return user_data.pop('back_state', SHOW_PARTICIPATIONS)


@region_decorator
def show_event_participants(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    if 'event_id' not in user_data:
        return _back_from_show_event_participants(user_data)
    event = models.AgitationEvent.objects.filter(id=user_data['event_id']
                                                 ).select_related('place', 'cubeusageinevent').first()
    if not event:
        return _back_from_show_event_participants(user_data)
    is_event_admin = models.AdminRights.has_admin_rights_for_event(user_telegram_id, event)

    participant = models.AgitationEventParticipant.get(user_telegram_id, event.id)
    if not participant:
        if is_event_admin:
            place = event.place
        else:
            return _back_from_show_event_participants(user_data)
    else:
        user_data['participant_id'] = participant.id
        place = participant.place

    event_text = event.show()
    details_text = ''
    show_participants = False
    if participant:
        event_text += ' ' + participant.place.show()
        show_participants = False
        if participant.canceled:
            status = '%s Вы отменили свою заявку' % participant.emoji_status()
        elif participant.declined:
            status = '%s Вашу заявку отклонили' % participant.emoji_status()
        elif participant.approved:
            status = '%s Ваше участие одобрили.' % participant.emoji_status()
            if participant.place.post_apply_text:
                status = '%s\n%s' % (status, participant.place.post_apply_text)
            else:
                show_participants = True
        else:
            status = '%s Вы подали заявку на участие.' % participant.emoji_status()
            if participant.place.post_apply_text:
                status = '%s\n%s' % (status, participant.place.post_apply_text)
            else:
                if not is_event_admin:
                    participants_count = models.AgitationEventParticipant.get_count(participant.event_id,
                                                                                    participant.place_id)
                    status = '%s\nЗаписались %d%s' % (status, participants_count, EMOJI_HUMAN)
        details_text = status

    if show_participants or is_event_admin:
        if event.need_cube:
            if event.cube_usage:
                cube_usage_text = event.cube_usage.show(private=is_event_admin)
            else:
                cube_usage_text = '_нет информации о доставке_'
            details_text = cube_usage_text + '\n' + details_text

        participants = models.AgitationEventParticipant.objects.filter(event_id=event.id)
        if participant:
            participants = participants.filter(place_id=participant.place_id)

        canceled_count = 0
        declined_count = 0
        ok_count = 0
        participant_texts = list()
        for i, p in enumerate(participants):
            if p.canceled:
                canceled_count += 1
            elif p.declined:
                declined_count += 1
            else:
                ok_count += 1
                if p.agitator_id == p.event.master_id:
                    text = EMOJI_CROWN + ' ' + p.agitator.show(private=True)
                else:
                    text = p.agitator.show(private=is_event_admin)
                if p.place_id != place.id:
                    text += ' - %s' % p.place.show()
                participant_texts.append('%d. %s %s' % (ok_count, p.emoji_status(), text))
        details_text += ' Записались %d%s' % (ok_count, EMOJI_HUMAN)
        if canceled_count:
            details_text += '\n%d отменили заявку' % canceled_count
        if declined_count:
            details_text += '\n%d отклоненных заявок' % declined_count
        details_text += '\n' + '\n'.join(participant_texts)
    keyboard = list()
    if is_event_admin:
        keyboard.append([InlineKeyboardButton('Управление заявками', callback_data=MANAGE_EVENT_PARTICIPANTS)])
        if not event.is_canceled and models.AdminRights.has_admin_rights(user_telegram_id, region_id):
            if event.need_cube:
                keyboard.append([InlineKeyboardButton('Логистика', callback_data=SET_CUBE_USAGE)])
            keyboard.append([InlineKeyboardButton('Отменить мероприятие', callback_data=CANCEL_EVENT)])
    if participant:
        if participant.canceled:
            keyboard.append([InlineKeyboardButton('Восстановить заявку', callback_data=RESTORE)])
        else:
            keyboard.append([InlineKeyboardButton('Отказаться от участия', callback_data=CANCEL)])
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])
    send_message_text(bot, update, user_data,
                      '%s\n%s' % (event_text, details_text),
                      location=place.get_location(),
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def show_event_participants_button(bot, update, user_data):
    query = update.callback_query
    if query.data in [SET_CUBE_USAGE, CANCEL_EVENT, MANAGE_EVENT_PARTICIPANTS]:
        query.answer()
        return query.data
    elif query.data == BACK:
        query.answer()
        return _back_from_show_event_participants(user_data)
    elif query.data == CANCEL:
        participant_id = user_data['participant_id']
        query.answer('Заявка отменена')
        models.AgitationEventParticipant.cancel(participant_id)
        notifications.notify_about_cancellation_participation(bot, participant_id)
        return
    elif query.data == RESTORE:
        participant_id = user_data['participant_id']
        query.answer('Заявка восстановлена')
        models.AgitationEventParticipant.restore(participant_id)
        notifications.notify_about_restoration_participation(bot, participant_id)
        return


EVENT_PAGE_SIZE = 10


@has_admin_rights
def set_cube_usage_start(bot, update, user_data):
    event_id = user_data['event_id']
    event = models.AgitationEvent.objects.filter(id=event_id).select_related('place', 'cubeusageinevent').first()
    if not event or not event.need_cube:
        return MANAGE_EVENTS
    keyboard = [[InlineKeyboardButton('<< Назад', callback_data=MANAGE_EVENTS)]]
    if event.cube_usage:
        if 'field_name' in user_data:
            field_name = user_data['field_name']
            keyboard = [[InlineKeyboardButton('Отмена', callback_data=BACK)]]
            if field_name == 'delivered_from':
                cubes = list(models.Cube.objects.filter(region=event.place.region_id))
                cubes = list(filter(lambda c: c.is_available_for(event), cubes))
                keyboard = [[InlineKeyboardButton(cube.last_storage.show(markdown=False, private=True),
                                                  callback_data=SELECT_CUBE_FOR_EVENT + str(cube.id))]
                            for cube in cubes] + keyboard
                send_message_text(bot, update, user_data,
                                  'Выберите куб для %s %s' % (event.show(), event.place.show()),
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  parse_mode='Markdown')
            elif field_name == 'delivered_by':
                send_message_text(bot, update, user_data,
                                  'Укажите, кто привезет куб на %s %s ' % (event.show(), event.place.show()),
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  parse_mode='Markdown')
            elif field_name == 'shipped_by':
                send_message_text(bot, update, user_data,
                                  'Укажите, кто увезет куб после %s %s' % (event.show(), event.place.show()),
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  parse_mode='Markdown')
            elif field_name == 'shipped_to':
                storages = list(models.Storage.objects.filter(region_id=event.place.region_id))
                keyboard = [[InlineKeyboardButton(storage.show(private=True, markdown=False),
                                                  callback_data=str(storage.id))]
                            for storage in storages
                            ] + [[InlineKeyboardButton('Добавить новый «склад»',
                                                       callback_data=CREATE_CUBE_STORAGE)]
                                 ] + keyboard
                send_message_text(bot, update, user_data,
                                  'Куда увезут куб после %s %s' % (event.show(), event.place.show()),
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  parse_mode='Markdown')
            return
        cube_usage = event.cubeusageinevent
        keyboard = [[InlineKeyboardButton('Изменить «откуда привезет»', callback_data='delivered_from')],
                    [InlineKeyboardButton('Изменить «кто привезет»', callback_data='delivered_by')],
                    [InlineKeyboardButton('Изменить «куда отвезет»', callback_data='shipped_to')],
                    [InlineKeyboardButton('Изменить «кто отвезет»', callback_data='shipped_by')]
                    ] + keyboard
        send_message_text(bot, update, user_data,
                          cube_usage.show(private=True),
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')
        return
    cubes = list(models.Cube.objects.filter(region=event.place.region_id))
    cubes = list(filter(lambda c: c.is_available_for(event), cubes))
    if cubes:
        keyboard = [[InlineKeyboardButton(cube.last_storage.show(markdown=False, private=True),
                                          callback_data=SELECT_CUBE_FOR_EVENT + str(cube.id))]
                    for cube in cubes] + keyboard
        send_message_text(bot, update, user_data,
                          'Выберите куб для %s %s' % (event.show(), event.place.show()),
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')
    else:
        keyboard = [[InlineKeyboardButton('Управление кубами', callback_data=MANAGE_CUBES)]] + keyboard
        send_message_text(bot, update, user_data,
                          'Совсем нет свободных кубов :(',
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')


@has_admin_rights
def set_cube_usage_message(bot, update, user_data):
    if 'field_name' in user_data:
        user = _extract_mentioned_user(update.message)
        if not user:
            return
        event_id = user_data['event_id']
        if user_data['field_name'] == 'delivered_by':
            models.CubeUsageInEvent.objects.filter(
                event_id=event_id
            ).update(delivered_by=user)
            notifications.notify_about_cube_usage(bot, event_id)
            del user_data['field_name']
        elif user_data['field_name'] == 'shipped_by':
            models.CubeUsageInEvent.objects.filter(
                event_id=event_id
            ).update(shipped_by=user)
            notifications.notify_about_cube_usage(bot, event_id)
            del user_data['field_name']


@has_admin_rights
def set_cube_usage_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    event_id = user_data['event_id']
    if 'field_name' in user_data:
        if query.data == BACK:
            del user_data['field_name']
        elif user_data['field_name'] == 'shipped_to':
            if query.data in [CREATE_CUBE_STORAGE]:
                return query.data
            storage_id = int(query.data)
            models.CubeUsageInEvent.objects.filter(
                event_id=event_id
            ).update(shipped_to_id=storage_id)
            notifications.notify_about_cube_usage(bot, event_id)
            del user_data['field_name']
        elif user_data['field_name'] == 'delivered_from':
            cube_id = int(query.data)
            cube = models.Cube.objects.filter(id=cube_id).first()
            models.CubeUsageInEvent.objects.filter(
                event_id=event_id
            ).update(cube_id=cube_id, delivered_from_id=cube.last_storage_id)
            notifications.notify_about_cube_usage(bot, event_id)
            del user_data['field_name']
    if query.data in [MANAGE_CUBES, MANAGE_EVENTS]:
        return query.data
    elif query.data in ['delivered_from', 'delivered_by', 'shipped_to', 'shipped_by']:
        user_data['field_name'] = query.data
        return
    else:
        match = re.match('^SELECT_CUBE_FOR_EVENT(\d+)$', query.data)
        if bool(match):
            cube_id = int(match.group(1))
            cube = models.Cube.objects.filter(id=cube_id).first()
            models.CubeUsageInEvent.objects.create(event_id=event_id,
                                                   cube_id=cube_id,
                                                   delivered_from_id=cube.last_storage_id)
            notifications.notify_about_cube_usage(bot, event_id)


@region_decorator
@has_admin_rights
def manage_cubes(bot, update, user_data, region_id):
    if 'cube_id' in user_data:
        cube = models.Cube.objects.filter(id=user_data['cube_id']).first()
        if not cube:
            del user_data['cube_id']
            return
        keyboard = [[InlineKeyboardButton('<< Назад', callback_data=BACK)]]
        send_message_text(bot, update, user_data,
                          'Куб хранится в %s' % cube.last_storage.show(private=True),
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')
        return
    cubes = list(models.Cube.objects.filter(region_id=region_id))
    keyboard = [[InlineKeyboardButton(cube.show(markdown=False, private=True),
                                      callback_data=str(cube.id))]
                for cube in cubes]
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    keyboard.append([InlineKeyboardButton('Создать новый куб', callback_data=CREATE_NEW_CUBE)])
    send_message_text(bot, update, user_data,
                      'Управление кубами',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def manage_cubes_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data in [MENU, CREATE_NEW_CUBE]:
        return query.data
    elif query.data == BACK:
        del user_data['cube_id']
        return
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['cube_id'] = int(query.data)


@region_decorator
@has_admin_rights
def create_new_cube(bot, update, user_data, region_id):
    keyboard = [[InlineKeyboardButton('Выбрать место из старых', callback_data=SELECT_CUBE_STORAGE)],
                [InlineKeyboardButton('Создать новое место', callback_data=CREATE_CUBE_STORAGE)],
                [InlineKeyboardButton('<< Назад', callback_data=MANAGE_CUBES)]]
    send_message_text(bot, update, user_data,
                      'Выберите место хранения нового куба',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
@has_admin_rights
def select_cube_storage(bot, update, user_data, region_id):
    storages = list(models.Storage.objects.filter(region_id=region_id))
    keyboard = [[InlineKeyboardButton(storage.show(private=True, markdown=False),
                                      callback_data=str(storage.id))]
                for storage in storages]
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=CREATE_NEW_CUBE)])
    send_message_text(bot, update, user_data,
                      'Выберите место хранения куба',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def create_cube_storage(bot, update, user_data):
    if 'storage_params' not in user_data:
        user_data['storage_params'] = dict()
    params = user_data['storage_params']
    if 'private_name' not in params:
        send_message_text(bot, update, user_data,
                          'Введите название и полный адрес')
    elif 'public_name' not in params:
        send_message_text(bot, update, user_data,
                          'Введите название с точностью до района/микрорайона города '
                          'или станции метро (без указания точного адреса)')
    elif 'holder_id' not in params:
        send_message_text(bot, update, user_data,
                          'С кем связаться?')
    elif 'location' not in params:
        send_message_text(bot, update, user_data,
                          'Геопозиция',
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Не указывать', callback_data=SKIP)]]))


@region_decorator
def _create_cube_storage(bot, update, user_data, region_id):
    params = user_data['storage_params']
    del user_data['storage_params']
    new_storage = models.Storage(region_id=region_id,
                                 public_name=params['public_name'],
                                 private_name=params['private_name'],
                                 holder_id=params['holder_id'])
    if 'location' in params:
        new_storage.geo_latitude = params['location']['latitude']
        new_storage.geo_longitude = params['location']['longitude']
    new_storage.save()
    if user_data.get('field_name', None) == 'shipped_to':
        event_id = user_data['event_id']
        models.CubeUsageInEvent.objects.filter(
            event_id=event_id
        ).update(shipped_to=new_storage)
        notifications.notify_about_cube_usage(bot, event_id)
        del user_data['field_name']
        return SET_CUBE_USAGE
    models.Cube.objects.create(region_id=region_id, last_storage=new_storage)
    return MANAGE_CUBES


@has_admin_rights
def create_cube_storage_message(bot, update, user_data):
    params = user_data['storage_params']
    message = update.message
    if 'private_name' not in params:
        if Filters.text(message):
            params['private_name'] = message.text
    elif 'public_name' not in params:
        if Filters.text(message):
            params['public_name'] = message.text
    elif 'holder_id' not in params:
        user = _extract_mentioned_user(message)
        if user:
            params['holder_id'] = user.id
    elif 'location' not in params:
        if Filters.location(message):
            params['location'] = {
                'latitude': message.location.latitude,
                'longitude': message.location.longitude,
            }
            return _create_cube_storage(bot, update, user_data)


@has_admin_rights
def create_cube_storage_button(bot, update, user_data):
    params = user_data['storage_params']
    query = update.callback_query
    query.answer()
    if 'location' not in params and query.data == SKIP:
        return _create_cube_storage(bot, update, user_data)


@region_decorator
@has_admin_rights
def select_cube_storage_button(bot, update, user_data, region_id):
    query = update.callback_query
    query.answer()
    if query.data in [CREATE_NEW_CUBE]:
        return query.data
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            storage_id = int(query.data)
            models.Cube.objects.create(region_id=region_id, last_storage_id=storage_id)
            return MANAGE_CUBES


def manage_event_participants(bot, update, user_data):
    event = models.AgitationEvent.objects.filter(
            id=user_data['event_id']
        ).select_related('place__region', 'cubeusageinevent').first()
    telegram_user_id = update.effective_user.id
    if not event or not models.AdminRights.has_admin_rights_for_event(telegram_user_id, event):
        return SHOW_EVENT_PARTICIPANTS

    participants = models.AgitationEventParticipant.get_all(user_data['event_id'])
    keyboard = list()
    if participants:
        lines = list()
        for p in participants:
            line = p.emoji_status() + ' ' + p.agitator.show(private=True)
            if p.place_id != event.place_id:
                line += ' ' + p.place.show()
            lines.append(line)
            keyboard.append([InlineKeyboardButton(EMOJI_OK + " " + p.agitator.full_name, callback_data=YES + str(p.id)),
                             InlineKeyboardButton(EMOJI_NO + " " + p.agitator.full_name, callback_data=NO + str(p.id))])
        text = '\n'.join(lines)
    else:
        text = "Никто не записался на это мероприятие :("
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])

    text = event.show() + ' ' + event.place.show() + '\n\n' + text

    send_message_text(bot, update, user_data,
                      text,
                      location=event.place.get_location(),
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def manage_event_participants_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        return SHOW_EVENT_PARTICIPANTS
    else:
        match = re.match('^(%s|%s)(\d+)$' % (YES, NO), query.data)
        if bool(match):
            participant_id = int(match.group(2))
            participant = models.AgitationEventParticipant.objects.filter(id=participant_id).first()
            if participant and participant.event_id == user_data['event_id']:
                if match.group(1) == YES:
                    models.AgitationEventParticipant.approve(participant_id)
                elif match.group(1) == NO:
                    models.AgitationEventParticipant.decline(participant_id)


@region_decorator
@has_admin_rights
def manage_events(bot, update, user_data, region_id):
    if 'events_offset' not in user_data:
        user_data['events_offset'] = 0

    offset = user_data['events_offset']
    if offset < 0:
        offset = 0
    query_set = models.AgitationEvent.objects.filter(start_date__gte=date.today(), place__region_id=region_id).select_related('place__region')
    events = list(query_set.select_related('place')[offset:offset + EVENT_PAGE_SIZE])
    keyboard = list()
    for event in events:
        participants = list([p for p in models.AgitationEventParticipant.get_all(event.id) if not p.canceled ])
        ok_count = len([1 for p in participants if p.approved])
        quest_count = len([1 for p in participants if not p.approved and not p.declined])
        count_str = ''
        if ok_count:
            count_str += '%d%s ' % (ok_count, EMOJI_OK)
        if quest_count:
            count_str += '%d%s ' % (quest_count, EMOJI_QUESTION)
        keyboard.append([InlineKeyboardButton('%s%s %s' % (count_str, event.show(markdown=False), event.place.show(markdown=False)),
                                              callback_data=str(event.id))])
    keyboard.extend(_build_paging_buttons(offset, query_set.count(), EVENT_PAGE_SIZE))
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      '*Выберите мероприятие*',
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def manage_events_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
        user_data['events_offset'] -= EVENT_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['events_offset'] += EVENT_PAGE_SIZE
    elif query.data in [MENU, SET_CUBE_USAGE]:
        return query.data
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['event_id'] = int(query.data)
            user_data['back_state'] = MANAGE_EVENTS
            return SHOW_EVENT_PARTICIPANTS


@region_decorator
@has_admin_rights
def cancel_event(bot, update, user_data, region_id):
    if 'event_id' not in user_data:
        return MENU
    event = models.AgitationEvent.objects.filter(id=user_data['event_id']).select_related('place__region').first()
    if not event:
        del user_data['event_id']
        return MENU
    if event.is_canceled:
        return MANAGE_EVENTS
    keyboard = [[InlineKeyboardButton('Да', callback_data=YES),
                 InlineKeyboardButton('Нет', callback_data=NO)]]
    send_message_text(bot, update, user_data,
                      event.show() + '\n*Вы уверены, что хотите отменить мероприятие?*',
                      location=event.place.get_location(),
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def cancel_event_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    event = models.AgitationEvent.objects.filter(id=user_data['event_id']).first()
    if query.data == YES:
        event.is_canceled = True
        event.save()
        return SHOW_EVENT_PARTICIPANTS
    elif query.data == NO:
        return SHOW_EVENT_PARTICIPANTS


def _build_paging_buttons(offset, count, page_size):
    paging_buttons = []
    if offset > 0:
        paging_buttons.append(InlineKeyboardButton('<<', callback_data=BACK))
    if count > offset + page_size:
        paging_buttons.append(InlineKeyboardButton('>>', callback_data=FORWARD))
    if paging_buttons:
        return [paging_buttons]
    else:
        return []


@region_decorator
def apply_to_agitate(bot, update, user_data, region_id):
    if 'events_offset' not in user_data:
        user_data['events_offset'] = 0

    user_telegram_id = update.effective_user.id
    abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
    offset = user_data['events_offset']
    if offset < 0:
        offset = 0
    query_set = models.AgitationEvent.objects.filter(end_date__gte=datetime.utcnow(),
                                                     place__region_id=region_id,
                                                     is_canceled=False)
    events = list(query_set.select_related('place')[offset:offset + EVENT_PAGE_SIZE])
    participations = list(models.AgitationEventParticipant.objects.filter(
        agitator__telegram_id=user_telegram_id,
        event__end_date__gte=datetime.utcnow(),
        event__place__region_id=region_id).all())
    exclude_event_ids = {p.event_id: True for p in participations}
    keyboard = list()
    any_event = False
    for event in events:
        if event.id not in exclude_event_ids:
            any_event = True
            keyboard.append([create_apply_to_agitate_button(event)])

    if not any_event and offset == 0:
        keyboard = _create_back_to_menu_keyboard()
        keyboard.inline_keyboard[0:0] = [[InlineKeyboardButton('Мои заявки', callback_data=SHOW_PARTICIPATIONS)]]
        send_message_text(bot, update, user_data,
                          '*Вы уже подали заявку на все запланированные мероприятия. Спасибо вам*',
                          parse_mode="Markdown",
                          reply_markup=keyboard)
        del user_data['events_offset']
        return

    keyboard.extend(_build_paging_buttons(offset, query_set.count(), EVENT_PAGE_SIZE))

    if abilities.can_be_applicant:
        keyboard.append([InlineKeyboardButton('Заявить новый куб', callback_data=CUBE_APPLICATION)])
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      '*В каких мероприятиях вы хотите поучаствовать в качестве уличного агитатора?*',
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def apply_to_agitate_button(bot, update, user_data):
    query = update.callback_query
    if query.data == BACK:
        query.answer()
        user_data['events_offset'] -= EVENT_PAGE_SIZE
    elif query.data == FORWARD:
        query.answer()
        user_data['events_offset'] += EVENT_PAGE_SIZE
    elif query.data in [MENU, SHOW_PARTICIPATIONS, CUBE_APPLICATION]:
        query.answer()
        return query.data
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            event_id = int(query.data)
            event = models.AgitationEvent.objects.filter(id=event_id).first()
            if event.agitators_limit:
                count = models.AgitationEventParticipant.get_count(event.id, event.place_id)
                if count == event.agitators_limit:
                    query.answer('Все места заняты, выберите другое место')
                    return
            query.answer()
            user_data['event_id'] = event_id
            return APPLY_TO_AGITATE_PLACE


def apply_to_agitate_place(bot, update, user_data):
    event = models.AgitationEvent.objects.filter(id=user_data['event_id']).select_related('place__region').first()
    if not event:
        del user_data['event_id']
        return APPLY_TO_AGITATE

    place_ids = user_data.get('place_ids', [event.place_id])
    while place_ids:
        place = models.AgitationPlace.objects.filter(id=place_ids[-1]).first()
        if not place:
            place_ids.pop()
            continue
        subplaces = place.subplaces
        if subplaces:
            buttons = list()
            for p in subplaces:
                buttons.append(create_apply_to_agitate_button(event, p))
            keyboard = utils.chunks(buttons, 2)
            keyboard.append([InlineKeyboardButton('Назад', callback_data=NO)])
            send_message_text(bot, update, user_data,
                              'Выберите место для участия в %s\n' % event.show(),
                              parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            keyboard = [[InlineKeyboardButton('Да', callback_data=YES),
                         InlineKeyboardButton('Нет', callback_data=NO)]]
            send_message_text(bot, update, user_data,
                              '*Подтвердите, что ваш выбор*\n'
                              'Вы хотите агитировать на %s %s?' % (event.show(), place.show()),
                              location=place.get_location(),
                              parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(keyboard))
        break
    user_data['place_ids'] = place_ids


def create_apply_to_agitate_button(event, place=None):
    if not place:
        button_data = str(event.id)
        place = event.place
        text = event.show(markdown=False) + " " + place.show(markdown=False)
    else:
        button_data = str(place.id)
        text = place.show(markdown=False)
    if not place.subplaces:
        applies_text = str(models.AgitationEventParticipant.get_count(event.id, place.id))
        if event.agitators_limit:
            applies_text = "%s/%d" % (applies_text, event.agitators_limit)
        text = u'%s%s %s' % (applies_text, EMOJI_HUMAN, text)
    return InlineKeyboardButton(text, callback_data=button_data)


def apply_to_agitate_place_button(bot, update, user_data):
    query = update.callback_query
    if query.data == NO:
        place_ids = user_data['place_ids']
        place_ids.pop()
        user_data['place_ids'] = place_ids
        if not place_ids:
            del user_data['place_ids']
            del user_data['event_id']
            query.answer()
            return APPLY_TO_AGITATE
    elif query.data == YES:
        event_id = user_data['event_id']
        place_id = user_data['place_ids'][-1]
        user_telegram_id = update.effective_user.id
        user = models.User.find_by_telegram_id(user_telegram_id)
        participant, created = models.AgitationEventParticipant.create(user, event_id, place_id)
        if created:
            notifications.notify_about_new_participant(bot, participant.id)
        del user_data['event_id']
        del user_data['place_ids']
        query.answer('Вы записаны')
        user_data['event_id'] = event_id
        return SHOW_EVENT_PARTICIPANTS
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            place_id = int(query.data)
            event = models.AgitationEvent.objects.filter(id=user_data['event_id']).first()
            if event.agitators_limit:
                count = models.AgitationEventParticipant.get_count(event.id, place_id)
                if count == event.agitators_limit:
                    query.answer('Все места заняты, выберите другое место')
                    return APPLY_TO_AGITATE_PLACE
            user_data['place_ids'].append(place_id)
    query.answer()


@has_admin_rights
def set_event_name(bot, update, user_data):
    keyboard = [[InlineKeyboardButton('Куб', callback_data='Куб'),
                 InlineKeyboardButton('Автокуб', callback_data='Автокуб')],
                [InlineKeyboardButton('Агитпрогулка', callback_data='Агитпрогулка')],
                [InlineKeyboardButton("Отмена", callback_data=MENU)]]
    send_message_text(bot, update, user_data,
                      "*Укажите тип ивента*",
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def set_event_name_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == MENU:
        return MENU
    if query.data == SET_EVENT_NAME:
        return  # double click on button - ignore second click
    user_data['event_name'] = query.data
    return SET_EVENT_MASTER


@has_admin_rights
def set_event_name_text(bot, update, user_data):
    user_data['event_name'] = update.message.text
    return SET_EVENT_MASTER


@has_admin_rights
def set_event_master_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите волонтера, ответственного за этот ивент')


def _extract_mentioned_user(message):
    if len(message.entities) > 1:
        return
    params = None
    if len(message.entities) == 1:
        entity = message.entities[0]
        if entity.type == 'mention':
            agitator_username = str(message.text[entity.offset:][:entity.length][1:])
            return models.User.objects.filter(telegram=agitator_username).first()
            ## TODO support non-registered users with username: how to check correctness of username?
        elif entity.type == 'text_mention':
            params = {'telegram_id': entity.user.id,
                      'first_name': entity.first_name,
                      'last_name': entity.last_name}
    elif Filters.contact(message):
        contact = message.contact
        params = {'phone': contact.phone_number,
                  'telegram_id': contact.user_id,
                  'first_name': contact.first_name,
                  'last_name': contact.last_name,
                  }
    elif Filters.text(message):
        text = message.text
        tokens = text.split()
        phone, name = '', ''
        for i in range(len(tokens)):
            cur_phone = utils.clean_phone_number(' '.join(tokens[0:i + 1]))
            cur_name = ' '.join(tokens[i + 1:])
            if (len(phone), len(name)) < (len(cur_phone), len(cur_name)):
                phone, name = cur_phone, cur_name
            cur_phone = utils.clean_phone_number(' '.join(tokens[i:]))
            cur_name = ' '.join(tokens[0:i])
            if (len(phone), len(name)) < (len(cur_phone), len(cur_name)):
                phone, name = cur_phone, cur_name
        if len(phone) >= 5:
            params = {'phone': phone,
                      'first_name': name}
    if params:
        return models.User.update_or_create(params)[0]


@has_admin_rights
def set_event_master_message(bot, update, user_data):
    user = _extract_mentioned_user(update.effective_message)
    if user:
        user_data['master_id'] = user.id
        return SET_EVENT_PLACE


@has_admin_rights
def set_event_place(bot, update, user_data):
    if 'place_id' in user_data:
        del user_data['place_id']
    keyboard = [[InlineKeyboardButton('Выбрать место из старых', callback_data=SELECT_EVENT_PLACE)],
                [InlineKeyboardButton('Создать новое место', callback_data=SET_PLACE_ADDRESS)],
                [InlineKeyboardButton('Назад', callback_data=SET_EVENT_MASTER)]]
    send_message_text(bot, update, user_data,
                      "Укажите место",
                      reply_markup=InlineKeyboardMarkup(keyboard))


PLACE_PAGE_SIZE = 10


@region_decorator
@has_admin_rights
def select_event_place(bot, update, user_data, region_id):
    if "place_offset" not in user_data:
        user_data["place_offset"] = 0
    offset = user_data["place_offset"]
    if offset < 0:
        offset = 0
    query_set = models.AgitationPlace.objects.filter(region_id=region_id)
    places = query_set.order_by('-last_update_time')[offset:offset + PLACE_PAGE_SIZE]
    keyboard = []
    for place in places:
        keyboard.append([InlineKeyboardButton(place.address, callback_data=str(place.id))])
    keyboard.extend(_build_paging_buttons(offset, query_set.count(), PLACE_PAGE_SIZE))
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=SET_EVENT_PLACE)])
    send_message_text(bot, update, user_data, "Выберите место", reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def select_event_place_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data in [SET_EVENT_PLACE]:
        return query.data
    elif query.data == BACK:
        user_data['place_offset'] -= PLACE_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['place_offset'] += PLACE_PAGE_SIZE
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['place_id'] = int(query.data)
            del user_data['place_offset']
            return SELECT_DATES


@has_admin_rights
def set_place_address_start(bot, update, user_data):
    keyboard = [[InlineKeyboardButton("Назад", callback_data=SET_EVENT_PLACE)]]
    send_message_text(bot, update, user_data, 'Введите адрес', reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def set_place_address(bot, update, user_data):
    user_data['address'] = update.message.text
    return SET_PLACE_LOCATION


@has_admin_rights
def set_place_location_start(bot, update, user_data):
    keyboard = [[InlineKeyboardButton("Не указывать", callback_data=SKIP)]]
    send_message_text(bot, update, user_data, 'Отправь геопозицию', reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def set_place_location(bot, update, user_data):
    location = update.message.location
    user_data['location'] = {
        'latitude': location.latitude,
        'longitude': location.longitude,
    }
    return SELECT_DATES


@has_admin_rights
def skip_place_location(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == SKIP:
        user_data['location'] = {}
        return SELECT_DATES


def _build_dates_keyboard(user_data):
    dates_dict = user_data['dates_dict']
    buttons = [InlineKeyboardButton(("+ " if value["selected"] else "") + key, callback_data=key)
               for key, value in dates_dict.items()]
    keyboard = utils.chunks(buttons, 5)
    if any([value for value in dates_dict.values() if value["selected"]]):
        keyboard.append([InlineKeyboardButton("Закончить", callback_data=END)])
    else:
        keyboard.append([InlineKeyboardButton("Нужно выбрать хотя бы одну дату", callback_data=TRASH)])
    return InlineKeyboardMarkup(keyboard)


@has_admin_rights
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


@has_admin_rights
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


@has_admin_rights
def set_event_time_start(bot, update, user_data):
    keyboard = list()
    for c in ['16:00-19:00', '17:00-20:00']:
        keyboard.append([InlineKeyboardButton(c, callback_data=c)])
    send_message_text(bot, update, user_data,
                      'Выберите время (например, "7:00 - 09:59" или "17:00-20:00")',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def set_event_time(bot, update, user_data):
    if update.message:
        text = update.message.text
    else:
        text = update.callback_query.data
    match = re.match("([01]?[0-9]|2[0-3]):([0-5][0-9])\s*-\s*([01]?[0-9]|2[0-3]):([0-5][0-9])", text)
    if bool(match):
        user_data['time_range'] = list(map(int, match.groups()))
        return CREATE_EVENT_SERIES_CONFIRM


def _create_events(user_data):
    place = models.AgitationPlace.objects.select_related('region').get(id=user_data['place_id'])
    time_range = user_data['time_range']
    from_seconds = (time_range[0] * 60 + time_range[1]) * 60 - place.region.timezone_delta
    to_seconds = (time_range[2] * 60 + time_range[3]) * 60 - place.region.timezone_delta
    if to_seconds < from_seconds:
        to_seconds += 86400

    region = models.Region.get_by_id(user_data['region_id'])

    events = list()
    for date_tuple in user_data['dates']:
        # TODO timezone
        event_date = date(year=date_tuple[0], month=date_tuple[1], day=date_tuple[2])
        event_datetime = datetime.combine(event_date, datetime.min.time())
        event_name = user_data['event_name']
        event = models.AgitationEvent(
            master_id=user_data['master_id'],
            place=place,
            name=event_name,
            need_cube=(region.settings.enabled_cube_logistics and event_name == 'Куб'),  # TODO small hack
            start_date=event_datetime + timedelta(seconds=from_seconds),
            end_date=event_datetime + timedelta(seconds=to_seconds),
        )
        events.append(event)
    return events


@region_decorator
@has_admin_rights
def create_event_series_confirm(bot, update, user_data, region_id):
    if 'place_id' in user_data:
        place = models.AgitationPlace.objects.select_related('region').get(id=user_data['place_id'])
        place.save()  # for update last_update_time
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
        user_data['place_id'] = place.id

    if place.region_id != region_id:
        return cancel(bot, update, user_data)
    events = _create_events(user_data)
    text = "\n".join(["*Вы уверены, что хотите добавить события?*",
                      "Ответственный: %s" % events[0].master.show(private=True)] +
                     ['%s %s' % (e.show(), place.show()) for e in events])
    keyboard = [[InlineKeyboardButton('Создать', callback_data=YES),
                 InlineKeyboardButton('Отменить', callback_data=NO)]]
    send_message_text(bot, update, user_data, text,
                      location=events[0].place.get_location(),
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


@has_admin_rights
def create_event_series_confirm_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == YES:
        return CREATE_EVENT_SERIES
    elif query.data == NO:
        del user_data['dates']
        del user_data['time_range']
        del user_data['place_id']
        del user_data['event_name']
        del user_data['master_telegram_id']
        return MENU


@has_admin_rights
def create_event_series(bot, update, user_data):
    events = _create_events(user_data)
    for e in events:
        e.save()
        cron.schedule_after_event_created(bot, e)
        models.AgitationEventParticipant.create(e.master, e.id, e.place.id)[0].make_approve()
    text = "\n".join(["Добавлено:",
                      "Ответственный: %s" % events[0].master.show(private=True)] +
                     ['%s %s' % (e.show(), e.place.show()) for e in events])
    send_message_text(bot, update, user_data, text,
                      location=events[0].place.get_location(),
                      parse_mode="Markdown",
                      reply_markup=_create_back_to_menu_keyboard())

    del user_data['dates']
    del user_data['time_range']
    del user_data['place_id']
    del user_data['master_id']
    del user_data['event_name']


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
    if region.settings.enabled_cube_logistics:
        text += '\n\n_Раздел «Логистика кубов» включен_'
        keyboard.append([InlineKeyboardButton('Отключить раздел «Логистика кубов»', callback_data=CHANGE_CUBE_LOGISTICS)])
    else:
        keyboard.append([InlineKeyboardButton('Включить раздел «Логистика кубов»', callback_data=CHANGE_CUBE_LOGISTICS)])
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      text,
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
    send_message_text(bot, update, user_data,
                      text,
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
    text = '*Укажите нового админа.*\n' \
           'Вы можете указать пользователя в одном из трех форматов:\n' \
           '- "@(имя в телеграмме)" (пользователь *должен быть* зарегистрирован в боте);\n' \
           '- "+70123456789 Вася Пупкин";\n' \
           '- "Share contact" из вашего списка контактов.'
    keyboard = [[InlineKeyboardButton('<< Назад', callback_data=MANAGE_ADMIN_RIGHTS)]]
    send_message_text(bot, update, user_data,
                      text,
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
    send_message_text(bot, update, user_data,
                      text,
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


@region_decorator
@has_admin_rights
def change_cube_logistics_start(bot, update, user_data, region_id):
    region = models.Region.get_by_id(region_id)
    text = 'Штаб *%s*\n' % region.show()
    text += 'Раздел «Логистика кубов» позволяет заполнять информацию о том, как доставляется ' \
            'куб на место проведения мероприятия.\n\n'
    keyboard = []
    if region.settings.enabled_cube_logistics:
        text += 'Вы можете отключить данную функциональность.\n' \
                'Если у вас есть идеи, как улучшить данный инструмент, напишите @kurpilyansky.'
        keyboard.append([InlineKeyboardButton('Отключить раздел «Логистика кубов»', callback_data=NO)])
    else:
        text += 'Если ваш город небольшой, то, скорее всего, вам не нужна данная функциональность.\n' \
                'Если вы храните кубы не только в штабе, если доставляете куб на машине ' \
                '(каждый раз разной), то попробуйте использовать данную функциональность.' \
                'Она может облегчить жизнь и вам, и волонтерам.'
        keyboard.append([InlineKeyboardButton('Включить раздел «Логистика кубов»', callback_data=YES)])
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=SHOW_REGION_SETTINGS)])
    send_message_text(bot, update, user_data,
                      text,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
def change_cube_logistics_button(bot, update, user_data, region_id):
    query = update.callback_query
    region = models.Region.get_by_id(region_id)
    query.answer()
    if query.data in [SHOW_REGION_SETTINGS]:
        return query.data
    elif query.data == YES:
        region.settings.enabled_cube_logistics = True
        region.settings.save()
        return SHOW_REGION_SETTINGS
    elif query.data == NO:
        region.settings.enabled_cube_logistics = False
        region.settings.save()
        return SHOW_REGION_SETTINGS


def clear_user_data(user_data, keep_keys=None):
    for key in list(user_data.keys()):
        if not (keep_keys and key in keep_keys):
            del user_data[key]


def cancel(bot, update, user_data):
    clear_user_data(user_data, ['last_bot_message_id', 'last_bot_message_ts', 'region_id'])
    return start(bot, update)


def change_region(bot, update, user_data):
    clear_user_data(user_data, ['last_bot_message_id', 'last_bot_message_ts'])
    return SELECT_REGION


def _create_back_to_menu_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("<< Меню", callback_data=MENU)]])


def force_button_query_handler(bot, update, user_data):
    query = update.callback_query
    query.answer()
    return query.data.split('_', 1)[1]


def show_event_for_master(bot, update, user_data, groups):
    query = update.callback_query
    event_id = int(groups[0])
    query.answer()
    utils.safe_delete_message(bot, update.effective_chat.id, update.effective_message.message_id)
    user_data['event_id'] = event_id
    return SHOW_EVENT_PARTICIPANTS


def transfer_cube_to_event(bot, update, user_data, groups):
    query = update.callback_query
    query.answer()
    event_id = int(groups[0])
    user_data['event_id'] = event_id
    return SET_CUBE_USAGE


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
    admin_commands.register_handlers(dp)
    notifications.register_handlers(dp)

    standard_callback_query_handler = CallbackQueryHandler(standard_callback)

    conv_handler = ConversationHandler(
        user_model=models.User,
        conversation_state_model=models.ConversationState,
        entry_points=[CommandHandler("start", start)],
        unknown_state_handler=EmptyHandler(cancel, pass_user_data=True),
        states={
            SET_LAST_NAME: [EmptyHandler(set_last_name_start, pass_user_data=True),
                            MessageHandler(Filters.text, set_last_name, pass_user_data=True)],
            SET_FIRST_NAME: [EmptyHandler(set_first_name_start, pass_user_data=True),
                             MessageHandler(Filters.text, set_first_name, pass_user_data=True)],
            SET_PHONE: [EmptyHandler(set_phone_start, pass_user_data=True),
                        MessageHandler(Filters.contact, set_phone_contact, pass_user_data=True),
                        MessageHandler(Filters.text, set_phone_text, pass_user_data=True)],
            SAVE_PROFILE: [EmptyHandler(save_profile, pass_user_data=True),
                           standard_callback_query_handler],
            SHOW_PROFILE: [EmptyHandler(show_profile, pass_user_data=True),
                           standard_callback_query_handler],
            SELECT_REGION: [EmptyHandler(select_region_start, pass_user_data=True),
                            CallbackQueryHandler(select_region_button, pass_user_data=True)],
            SET_ABILITIES: [EmptyHandler(set_abilities, pass_user_data=True),
                            CallbackQueryHandler(set_abilities_button, pass_user_data=True)],
            SAVE_ABILITIES: [EmptyHandler(save_abilities, pass_user_data=True),
                             standard_callback_query_handler],
            MENU: [EmptyHandler(show_menu, pass_user_data=True), standard_callback_query_handler],
            MAKE_BROADCAST: [EmptyHandler(make_broadcast_start, pass_user_data=True),
                             MessageHandler(Filters.text, make_broadcast, pass_user_data=True)],
            MAKE_BROADCAST_CONFIRM: [EmptyHandler(make_broadcast_confirm, pass_user_data=True),
                                     CallbackQueryHandler(make_broadcast_confirm_button, pass_user_data=True)],
            SCHEDULE: [EmptyHandler(show_schedule, pass_user_data=True), standard_callback_query_handler],
            CUBE_APPLICATION: [EmptyHandler(cube_application, pass_user_data=True),
                               standard_callback_query_handler],
            SHOW_PARTICIPATIONS: [EmptyHandler(show_participations, pass_user_data=True),
                                  CallbackQueryHandler(show_participations_button, pass_user_data=True)],
            SHOW_EVENT_PARTICIPANTS: [EmptyHandler(show_event_participants, pass_user_data=True),
                                      CallbackQueryHandler(show_event_participants_button, pass_user_data=True)],
            MANAGE_EVENT_PARTICIPANTS: [EmptyHandler(manage_event_participants, pass_user_data=True),
                                        CallbackQueryHandler(manage_event_participants_button, pass_user_data=True)],
            MANAGE_CUBES: [EmptyHandler(manage_cubes, pass_user_data=True),
                           CallbackQueryHandler(manage_cubes_button, pass_user_data=True)],
            CREATE_NEW_CUBE: [EmptyHandler(create_new_cube, pass_user_data=True),
                              standard_callback_query_handler],
            SELECT_CUBE_STORAGE: [EmptyHandler(select_cube_storage, pass_user_data=True),
                                  CallbackQueryHandler(select_cube_storage_button, pass_user_data=True)],
            CREATE_CUBE_STORAGE: [EmptyHandler(create_cube_storage, pass_user_data=True),
                                  MessageHandler(Filters.text | Filters.location | Filters.contact,
                                                 create_cube_storage_message, pass_user_data=True),
                                  CallbackQueryHandler(create_cube_storage_button, pass_user_data=True)],
            MANAGE_EVENTS: [EmptyHandler(manage_events, pass_user_data=True),
                            CallbackQueryHandler(manage_events_button, pass_user_data=True)],
            CANCEL_EVENT: [EmptyHandler(cancel_event, pass_user_data=True),
                           CallbackQueryHandler(cancel_event_button, pass_user_data=True)],
            SET_CUBE_USAGE: [EmptyHandler(set_cube_usage_start, pass_user_data=True),
                             CallbackQueryHandler(set_cube_usage_button, pass_user_data=True),
                             MessageHandler(Filters.text, set_cube_usage_message, pass_user_data=True)],
            APPLY_TO_AGITATE: [EmptyHandler(apply_to_agitate, pass_user_data=True),
                               CallbackQueryHandler(apply_to_agitate_button, pass_user_data=True)],
            APPLY_TO_AGITATE_PLACE: [EmptyHandler(apply_to_agitate_place, pass_user_data=True),
                                     CallbackQueryHandler(apply_to_agitate_place_button, pass_user_data=True)],
            SET_EVENT_NAME: [EmptyHandler(set_event_name, pass_user_data=True),
                             CallbackQueryHandler(set_event_name_button, pass_user_data=True),
                             MessageHandler(Filters.text, set_event_name_text, pass_user_data=True)],
            SET_EVENT_MASTER: [EmptyHandler(set_event_master_start, pass_user_data=True),
                               MessageHandler(Filters.text | Filters.contact,
                                              set_event_master_message, pass_user_data=True)],
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
            CREATE_EVENT_SERIES_CONFIRM: [EmptyHandler(create_event_series_confirm, pass_user_data=True),
                                          CallbackQueryHandler(create_event_series_confirm_button, pass_user_data=True)],
            CREATE_EVENT_SERIES: [EmptyHandler(create_event_series, pass_user_data=True),
                                  standard_callback_query_handler],
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
            CHANGE_CUBE_LOGISTICS: [EmptyHandler(change_cube_logistics_start, pass_user_data=True),
                                    CallbackQueryHandler(change_cube_logistics_button, pass_user_data=True)],
        },
        pre_fallbacks=[CallbackQueryHandler(force_button_query_handler, pattern='^%s_' % FORCE_BUTTON, pass_user_data=True),
                       CallbackQueryHandler(show_event_for_master,
                                            pattern='^%s(\d+)$' % SHOW_EVENT_FOR_MASTER,
                                            pass_groups=True,
                                            pass_user_data=True),
                       CallbackQueryHandler(transfer_cube_to_event,
                                            pattern='^%s(\d+)$' % TRANSFER_CUBE_TO_EVENT,
                                            pass_groups=True,
                                            pass_user_data=True)],
        fallbacks=[CommandHandler('cancel', cancel, pass_user_data=True),
                   CommandHandler("region", change_region, pass_user_data=True),
                   CommandHandler("send_bug_report", send_bug_report, pass_user_data=True)]
    )

    # dp.add_handler(InlineQueryHandler(select_event_place, pass_user_data=True))

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error_handler)

    cron.init_all(updater)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
