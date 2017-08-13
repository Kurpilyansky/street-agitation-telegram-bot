from street_agitation_bot import bot_settings, models, notifications, utils, cron
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
    user, created = models.User.objects.update_or_create(
        telegram_id=user.id,
        defaults={'first_name': user_data.get('first_name'),
                  'last_name': user_data.get('last_name'),
                  'phone': utils.clean_phone_number(user_data.get('phone')),
                  'telegram': user.username})

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


def select_region(bot, update, user_data):
    user = models.User.find_by_telegram_id(update.effective_user.id)
    if not user:
        return SET_LAST_NAME
    regions = user.regions
    if not regions:
        return ADD_REGION
    buttons = [InlineKeyboardButton(region.show(markdown=False), callback_data=str(region.id)) for region in regions]
    keyboard = utils.chunks(buttons, 2)
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
    user_telegram_id = update.effective_user.id
    region_name = update.message.text
    region = models.Region.find_by_name(region_name, user_telegram_id)
    if region:
        if models.AgitatorInRegion.get(region.id, user_telegram_id):
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
        user_telegram_id = update.effective_user.id
        abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
        if abilities.can_be_applicant:
            keyboard.append([InlineKeyboardButton('Заявить новый куб', callback_data=CUBE_APPLICATION)])
        if models.AgitationEventParticipant.objects.filter(
                                        agitator__telegram_id=user_telegram_id,
                                        event__start_date__gte=date.today()).exists():
            keyboard.append([InlineKeyboardButton('Мои заявки', callback_data=SHOW_PARTICIPATIONS)])
        keyboard.append([InlineKeyboardButton('Настройки', callback_data=SHOW_PROFILE)])
        if abilities.is_admin:
            keyboard.append([InlineKeyboardButton('Добавить ивент', callback_data=SET_EVENT_NAME)])
            keyboard.append([InlineKeyboardButton('Управление ивентами', callback_data=MANAGE_EVENTS)])
            keyboard.append([InlineKeyboardButton('Управление кубами', callback_data=MANAGE_CUBES)])
            keyboard.append([InlineKeyboardButton('Сделать рассылку', callback_data=MAKE_BROADCAST)])
    else:
        keyboard.append([InlineKeyboardButton('Выбрать регион', callback_data=SELECT_REGION)])
    send_message_text(bot, update, user_data, '*Меню*\nВыберите действие для продолжения работы', parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


def make_broadcast_start(bot, update, user_data):
    send_message_text(bot, update, user_data,
                      '*Отправьте сообщение, и оно будет отправлено всем пользователям*',
                      parse_mode='Markdown')


def make_broadcast(bot, update, user_data):
    user_data['broadcast_text'] = update.message.text
    return MAKE_BROADCAST_CONFIRM


def make_broadcast_confirm(bot, update, user_data):
    broadcast_text = user_data['broadcast_text']
    text = 'Вы уверены, что хотите отправить *всем пользователям вашего региона* следующее сообщение:\n\n%s' % broadcast_text
    keyboard = [[InlineKeyboardButton('Отправить', callback_data=YES),
                 InlineKeyboardButton('Отмена', callback_data=NO)]]
    send_message_text(bot, update, user_data, text,
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
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
           'и подать её в администрацию вашего района. https://goo.gl/3GneK2'  #TODO make a document
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
            keyboard.append([InlineKeyboardButton(p_text, callback_data=str(p.id))])
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
            user_data['participant_id'] = int(query.data)
            return SHOW_SINGLE_PARTICIPATION


def show_single_participation(bot, update, user_data):
    user_telegram_id = update.effective_user.id
    if 'participant_id' not in user_data:
        return SHOW_PARTICIPATIONS
    participant = models.AgitationEventParticipant.objects.filter(
        id=user_data['participant_id']).select_related('event', 'place', 'event__place__region', 'event__cubeusageinevent').first()
    if not participant or participant.agitator.telegram_id != user_telegram_id:
        del user_data['participant_id']
        return SHOW_PARTICIPATIONS
    user = models.User.find_by_telegram_id(user_telegram_id)
    event_text = participant.event.show() + " " + participant.place.show()
    if participant.canceled:
        status = '%s Вы отменили свою заявку' % participant.emoji_status()
    elif participant.declined:
        status = '%s Вашу заявку отклонили' % participant.emoji_status()
    elif participant.approved:
        status = '%s Ваше участие одобрили.' % participant.emoji_status()
        if participant.place.post_apply_text:
            status = '%s\n%s' % (status, participant.place.post_apply_text)
        else:
            participants = participant.get_neighbours()
            status = '%s Записались %d%s' % (status, len(participants), EMOJI_HUMAN)
            participant_texts = list()
            for i, p in enumerate(participants):
                if p.agitator_id == p.event.master_id:
                    text = EMOJI_CROWN + ' ' + p.agitator.show(private=True)
                else:
                    text = p.agitator.show(private=(user.id == p.event.master_id))
                participant_texts.append('%d. %s %s' % (i + 1, p.emoji_status(), text))
            if participant.event.need_cube:
                if hasattr(participant.event, 'cubeusageinevent'):
                    cube_usage_text = participant.event.cubeusageinevent.show(private=(user.id == participant.event.master_id))
                else:
                    cube_usage_text = '_нет информации о доставке_'
                status = cube_usage_text + '\n' + status
            status = status + '\n' + '\n'.join(participant_texts)
    else:
        status = '%s Вы подали заявку на участие' % participant.emoji_status()
        if participant.place.post_apply_text:
            status = '%s\n%s' % (status, participant.place.post_apply_text)
        else:
            participants_count = models.AgitationEventParticipant.get_count(participant.event_id, participant.place_id)
            status = '%s\nЗаписались %d%s' % (status, participants_count, EMOJI_HUMAN)
    keyboard = list()
    if participant.canceled:
        keyboard.append([InlineKeyboardButton('Восстановить заявку', callback_data=RESTORE)])
    else:
        keyboard.append([InlineKeyboardButton('Отказаться от участия', callback_data=CANCEL)])
    keyboard.append([InlineKeyboardButton('Назад', callback_data=BACK)])
    send_message_text(bot, update, user_data,
                      '%s\n%s' % (event_text, status),
                      location=participant.place.get_location(),
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def show_single_participation_button(bot, update, user_data):
    query = update.callback_query
    participant_id = user_data['participant_id']
    if query.data == BACK:
        query.answer()
        del user_data['participant_id']
        return SHOW_PARTICIPATIONS
    elif query.data == CANCEL:
        query.answer('Заявка отменена')
        models.AgitationEventParticipant.cancel(participant_id)
        notifications.notify_about_cancellation_participation(bot, participant_id)
        return
    elif query.data == RESTORE:
        query.answer('Заявка восстановлена')
        models.AgitationEventParticipant.restore(participant_id)
        notifications.notify_about_restoration_participation(bot, participant_id)
        return


EVENT_PAGE_SIZE = 10


def set_cube_usage_start(bot, update, user_data):
    user_telegram_id = update.effective_user.id
    event_id = user_data['event_id']
    event = models.AgitationEvent.objects.filter(id=event_id).select_related('place', 'cubeusageinevent').first()
    if not event or not event.need_cube:
        return
    abilities = models.AgitatorInRegion.get(event.place.region_id, user_telegram_id)
    if not abilities or not abilities.is_admin:
        return
    keyboard = [[InlineKeyboardButton('<< Назад', callback_data=MANAGE_EVENTS)]]
    if hasattr(event, 'cubeusageinevent'):
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
                            for storage in storages] + keyboard
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


def set_cube_usage_message(bot, update, user_data):
    if 'field_name' in user_data:
        user = _extract_mentioned_user(update.message)
        if not user:
            return
        if user_data['field_name'] == 'delivered_by':
            models.CubeUsageInEvent.objects.filter(
                event_id=user_data['event_id']
            ).update(delivered_by=user)
            del user_data['field_name']
        elif user_data['field_name'] == 'shipped_by':
            models.CubeUsageInEvent.objects.filter(
                event_id=user_data['event_id']
            ).update(shipped_by=user)
            del user_data['field_name']


def set_cube_usage_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if 'field_name' in user_data:
        if query.data == BACK:
            del user_data['field_name']
        elif user_data['field_name'] == 'shipped_to':
            storage_id = int(query.data)
            models.CubeUsageInEvent.objects.filter(
                event_id=user_data['event_id']
            ).update(shipped_to_id=storage_id)
            del user_data['field_name']
        elif user_data['field_name'] == 'delivered_from':
            cube_id = int(query.data)
            cube = models.Cube.objects.filter(id=cube_id).first()
            models.CubeUsageInEvent.objects.filter(
                event_id=user_data['event_id']
            ).update(cube_id=cube_id, delivered_from_id=cube.last_storage_id)
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
            models.CubeUsageInEvent.objects.create(event_id=user_data['event_id'],
                                                   cube_id=cube_id,
                                                   delivered_from_id=cube.last_storage_id)


@region_decorator
def manage_cubes(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
    if not abilities or not abilities.is_admin:
        return MENU
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
    keyboard.append([InlineKeyboardButton('Создать новый куб', callback_data=CREATE_NEW_CUBE)])
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      'Управление кубами',
                      reply_markup=InlineKeyboardMarkup(keyboard))


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
def create_new_cube(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
    if not abilities or not abilities.is_admin:
        return MENU
    keyboard = [[InlineKeyboardButton('Выбрать место из старых', callback_data=SELECT_CUBE_STORAGE)],
                [InlineKeyboardButton('Создать новое место', callback_data=CREATE_CUBE_STORAGE)],
                [InlineKeyboardButton('<< Назад', callback_data=MANAGE_CUBES)]]
    send_message_text(bot, update, user_data,
                      'Выберите место хранения нового куба',
                      reply_markup=InlineKeyboardMarkup(keyboard))


@region_decorator
def select_cube_storage(bot, update, user_data, region_id):
    storages = list(models.Storage.objects.filter(region_id=region_id))
    keyboard = [[InlineKeyboardButton(storage.show(private=True, markdown=False),
                                      callback_data=str(storage.id))]
                for storage in storages]
    keyboard.append([InlineKeyboardButton('<< Назад', callback_data=CREATE_NEW_CUBE)])
    send_message_text(bot, update, user_data,
                      'Выберите место хранения куба',
                      reply_markup=InlineKeyboardMarkup(keyboard))


def create_cube_storage(bot, update, user_data):
    if 'storage_params' not in user_data:
        user_data['storage_params'] = dict()
    params = user_data['storage_params']
    if 'private_name' not in params:
        send_message_text(bot, update, user_data,
                          'Введите название и полный адрес')
    elif 'public_name' not in params:
        send_message_text(bot, update, user_data,
                          'Введите название с точностью до района города (без указания тоного адреса)')
    elif 'holder' not in params:
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
                                 holder_id=params['holder']['id'])  # TODO from phone
    if 'location' in params:
        new_storage.geo_latitude = params['location']['latitude']
        new_storage.geo_longitude = params['location']['longitude']
    new_storage.save()
    models.Cube.objects.create(region_id=region_id, last_storage=new_storage)
    return MANAGE_CUBES


def create_cube_storage_message(bot, update, user_data):
    params = user_data['storage_params']
    message = update.message
    if 'private_name' not in params:
        if Filters.text(message):
            params['private_name'] = message.text
    elif 'public_name' not in params:
        if Filters.text(message):
            params['public_name'] = message.text
    elif 'holder' not in params:
        if Filters.contact(message):
            params['holder'] = {'phone': message.contact.phone_number}
        elif Filters.text(message):
            user = _extract_mentioned_user(message)
            if user:
                params['holder'] = {'id': user.id}
            else:
                params['holder'] = {'phone': message.text}  # TODO validate phone
    elif 'location' not in params:
        if Filters.location(message):
            params['location'] = {
                'latitude': message.location.latitude,
                'longitude': message.location.longitude,
            }
            return _create_cube_storage(bot, update, user_data)


def create_cube_storage_button(bot, update, user_data):
    params = user_data['storage_params']
    query = update.callback_query
    query.answer()
    if 'location' not in params and query.data == SKIP:
        return _create_cube_storage(bot, update, user_data)


@region_decorator
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


@region_decorator
def manage_events(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
    if not abilities or not abilities.is_admin:
        return MENU

    if 'event_id' in user_data:
        event = models.AgitationEvent.objects.filter(id=user_data['event_id']).select_related('place__region', 'cubeusageinevent').first()
        if event:
            cube_usage = event.cubeusageinevent if hasattr(event, 'cubeusageinevent') else None
            applications = list(models.AgitationEventParticipant.objects.filter(event_id=user_data['event_id']).all())
            keyboard = list()
            if applications:
                lines = list()
                for a in applications:
                    line = a.emoji_status() + " " + a.place.show() + " " + a.agitator.show(private=True)
                    lines.append(line)
                    keyboard.append([InlineKeyboardButton(EMOJI_OK + " " + a.agitator.full_name, callback_data=YES + str(a.id)),
                                     InlineKeyboardButton(EMOJI_NO + " " + a.agitator.full_name, callback_data=NO + str(a.id))])
                text = '\n'.join(lines)
            else:
                text = "Никто не записался на это мероприятие :("
            if not event.is_canceled:
                if event.need_cube:
                    keyboard.append([InlineKeyboardButton('Доставка куба', callback_data=SET_CUBE_USAGE)])
                keyboard.append([InlineKeyboardButton('Отменить мероприятие', callback_data=CANCEL_EVENT)])
            keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])

            if event.need_cube:
                if cube_usage:
                    text = cube_usage.show(private=True) + '\n\n' + text
                else:
                    text = '_нет информации о доставке_' + '\n\n' + text
            text = event.show() + '\n\n' + text

            send_message_text(bot, update, user_data,
                              text,
                              location=event.place.get_location(),
                              parse_mode="Markdown",
                              reply_markup=InlineKeyboardMarkup(keyboard))
            return
        else:
            del user_data['event_id']

    if 'events_offset' not in user_data:
        user_data['events_offset'] = 0

    offset = user_data['events_offset']
    if offset < 0:
        offset = 0
    query_set = models.AgitationEvent.objects.filter(start_date__gte=date.today(), place__region_id=region_id).select_related('place__region')
    events = list(query_set.select_related('place')[offset:offset + EVENT_PAGE_SIZE])
    keyboard = list()
    for event in events:
        keyboard.append([InlineKeyboardButton('%s %s' % (event.show(markdown=False), event.place.show(markdown=False)),
                                              callback_data=str(event.id))])
    keyboard.extend(_build_paging_buttons(offset, query_set.count(), EVENT_PAGE_SIZE))
    keyboard.append([InlineKeyboardButton('<< Меню', callback_data=MENU)])
    send_message_text(bot, update, user_data,
                      '*Выберите мероприятие*',
                      parse_mode="Markdown",
                      reply_markup=InlineKeyboardMarkup(keyboard))


def manage_events_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == CANCEL_EVENT:
        return CANCEL_EVENT
    if query.data == BACK:
        if 'event_id' in user_data:
            del user_data['event_id']
        else:
            user_data['events_offset'] -= EVENT_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['events_offset'] += EVENT_PAGE_SIZE
    elif query.data in [MENU, SET_CUBE_USAGE]:
        return query.data
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            user_data['event_id'] = int(query.data)
        else:
            match = re.match('^(%s|%s)(\d+)$' % (YES, NO), query.data)
            if bool(match):
                participant_id = int(match.group(2))
                if match.group(1) == YES:
                    models.AgitationEventParticipant.approve(participant_id)
                elif match.group(1) == NO:
                    models.AgitationEventParticipant.decline(participant_id)


@region_decorator
def cancel_event(bot, update, user_data, region_id):
    user_telegram_id = update.effective_user.id
    abilities = models.AgitatorInRegion.get(region_id, user_telegram_id)
    if not abilities or not abilities.is_admin:
        return MENU
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


def cancel_event_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    event = models.AgitationEvent.objects.filter(id=user_data['event_id']).first()
    if query.data == YES:
        event.is_canceled = True
        event.save()
        return MANAGE_EVENTS
    elif query.data == NO:
        return MANAGE_EVENTS


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
    query.answer()
    if query.data == BACK:
        user_data['events_offset'] -= EVENT_PAGE_SIZE
    elif query.data == FORWARD:
        user_data['events_offset'] += EVENT_PAGE_SIZE
    elif query.data in [MENU, SHOW_PARTICIPATIONS, CUBE_APPLICATION]:
        return query.data
    else:
        match = re.match('^\d+$', query.data)
        if bool(match):
            event_id = int(query.data)
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
        user_data['participant_id'] = participant.id
        return SHOW_SINGLE_PARTICIPATION
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


def set_event_name(bot, update, user_data):
    keyboard = [[InlineKeyboardButton('Куб', callback_data='Куб'),
                 InlineKeyboardButton('Автокуб', callback_data='Автокуб')],
                [InlineKeyboardButton('Агитпрогулка', callback_data='Агитпрогулка')],
                [InlineKeyboardButton("Отмена", callback_data=MENU)]]
    send_message_text(bot, update, user_data,
                      "*Укажите тип ивента*",
                      parse_mode='Markdown',
                      reply_markup=InlineKeyboardMarkup(keyboard))


def set_event_name_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == MENU:
        return MENU
    if query.data == SET_EVENT_NAME:
        return  # double click on button - ignore second click
    user_data['event_name'] = query.data
    return SET_EVENT_MASTER


def set_event_master_start(bot, update, user_data):
    send_message_text(bot, update, user_data, 'Укажите волонтера, ответственного за этот ивент')


def _extract_mentioned_user(message):
    if len(message.entities) != 1:
        return
    entity = message.entities[0]
    if entity.type == 'mention':
        agitator_username = str(message.text[entity.offset:][:entity.length][1:])
        return models.User.objects.filter(telegram=agitator_username).first()
    elif entity.type == 'text_mention':
        return models.User.find_by_id(entity.user.id)


def set_event_master_text(bot, update, user_data):
    user = _extract_mentioned_user(update.effective_message)
    if user:
        user_data['master_id'] = user.id
        return SET_EVENT_PLACE


def set_event_place(bot, update, user_data):
    if 'place_id' in user_data:
        del user_data['place_id']
    keyboard = [[InlineKeyboardButton('Выбрать место из старых', callback_data=SELECT_EVENT_PLACE)],
                [InlineKeyboardButton('Создать новое место', callback_data=SET_PLACE_ADDRESS)],
                [InlineKeyboardButton('Назад', callback_data=SET_EVENT_NAME)]]
    send_message_text(bot, update, user_data,
                      "Укажите место",
                      reply_markup=InlineKeyboardMarkup(keyboard))


PLACE_PAGE_SIZE = 10


@region_decorator
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
    send_message_text(bot, update, user_data, "Выберите место", reply_markup=InlineKeyboardMarkup(keyboard))


def select_event_place_button(bot, update, user_data):
    query = update.callback_query
    query.answer()
    if query.data == BACK:
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
        return CREATE_EVENT_SERIES_CONFIRM


def _create_events(user_data):
    place = models.AgitationPlace.objects.select_related('region').get(id=user_data['place_id'])
    time_range = user_data['time_range']
    from_seconds = (time_range[0] * 60 + time_range[1]) * 60 - place.region.timezone_delta
    to_seconds = (time_range[2] * 60 + time_range[3]) * 60 - place.region.timezone_delta
    if to_seconds < from_seconds:
        to_seconds += 86400

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
            need_cube=(event_name == 'Куб'),  # TODO small hack
            start_date=event_datetime + timedelta(seconds=from_seconds),
            end_date=event_datetime + timedelta(seconds=to_seconds),
        )
        events.append(event)
    return events


@region_decorator
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
    participant = models.AgitationEventParticipant.get(update.effective_user.id, event_id)
    if participant:
        query.answer()
        utils.safe_delete_message(bot, update.effective_chat.id, update.effective_message.message_id)
        user_data['participant_id'] = participant.id
        return SHOW_SINGLE_PARTICIPATION
    query.answer('Что-то пошло не так')


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

    standard_callback_query_handler = CallbackQueryHandler(standard_callback)

    conv_handler = ConversationHandler(
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
            SELECT_REGION: [EmptyHandler(select_region, pass_user_data=True),
                            CallbackQueryHandler(select_region_button, pass_user_data=True)],
            ADD_REGION: [EmptyHandler(add_region_start, pass_user_data=True),
                         MessageHandler(Filters.text, add_region, pass_user_data=True)],
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
            SHOW_SINGLE_PARTICIPATION: [EmptyHandler(show_single_participation, pass_user_data=True),
                                        CallbackQueryHandler(show_single_participation_button, pass_user_data=True)],
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
                             CallbackQueryHandler(set_event_name_button, pass_user_data=True)],
            SET_EVENT_MASTER: [EmptyHandler(set_event_master_start, pass_user_data=True),
                               MessageHandler(Filters.text, set_event_master_text, pass_user_data=True)],
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
                                  standard_callback_query_handler]
        },
        pre_fallbacks=[CallbackQueryHandler(force_button_query_handler, pattern='^%s_' % FORCE_BUTTON, pass_user_data=True),
                       CallbackQueryHandler(show_event_for_master,
                                            pattern='^%s(\d)+$' % SHOW_EVENT_FOR_MASTER,
                                            pass_groups=True,
                                            pass_user_data=True),
                       CallbackQueryHandler(transfer_cube_to_event,
                                            pattern='^%s(\d)+$' % TRANSFER_CUBE_TO_EVENT,
                                            pass_groups=True,
                                            pass_user_data=True)],
        fallbacks=[CommandHandler('cancel', cancel, pass_user_data=True),
                   CommandHandler("region", change_region, pass_user_data=True),
                   CommandHandler("send_bug_report", send_bug_report, pass_user_data=True)]
    )

    # dp.add_handler(InlineQueryHandler(select_event_place, pass_user_data=True))

    dp.add_handler(conv_handler)

    notifications.register_handlers(dp)

    # log all errors
    dp.add_error_handler(error_handler)

    cron.init_all(updater)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()
