
from django.db.models import Q

import re

from datetime import datetime, timedelta

from django.db import transaction

from telegram import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
                      InlineKeyboardButton, InlineKeyboardMarkup,
                      InlineQueryResultArticle, TelegramError)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          CallbackQueryHandler, InlineQueryHandler)

from street_agitation_bot.handlers import ConversationHandler, EmptyHandler
from street_agitation_bot import utils
from door_to_door_bot import models
from door_to_door_bot.common import send_message_text, standard_callback_query_handler, build_paging_buttons
from door_to_door_bot.bot_constants import *

CLEAR_FILTER = 'CLEAR_FILTER'
ADD_NEW_OBJECT = 'ADD_NEW_OBJECT'
RETURN_TO_BACK = 'RETURN_TO_BACK'
SET_FLAT_CONTACT_STATUS = 'SET_FLAT_CONTACT_STATUS'

MENU = 'MENU'
CHOOSE_STREET = 'CHOOSE_STREET'
ADD_STREET = 'ADD_STREET'
CHOOSE_HOUSE = 'CHOOSE_HOUSE'
ADD_HOUSE = 'ADD_HOUSE'
CHOOSE_HOUSE_BLOCK = 'CHOOSE_HOUSE_BLOCK'
ADD_HOUSE_BLOCK = 'ADD_HOUSE_BLOCK'
CHOOSE_FLAT = 'CHOOSE_FLAT'
ADD_FLAT = 'ADD_FLAT'
CONTACT_FLAT = 'CONTACT_FLAT'


def team_decorator(func):
    def wrapper(bot, update, chat_data, *args, **kwargs):
        if 'team_id' not in chat_data:
            chat_id = update.effective_chat.id
            team = models.AgitationTeam.objects.get(chat_id=chat_id)
            chat_data['team_id'] = team.id
        else:
            team_id = int(chat_data['team_id'])
            team = models.AgitationTeam.objects.get(id=team_id)
        return func(bot, update, chat_data=chat_data, team=team, *args, **kwargs)

    return wrapper


def clear_chat_data(chat_data, keep_keys=None):
    for key in list(chat_data.keys()):
        if not (keep_keys and key in keep_keys):
            del chat_data[key]


def cancel(bot, update, chat_data):
    clear_chat_data(chat_data, ['last_bot_message_id', 'last_bot_message_ts'])
    return start(bot, update)


def start(bot, update):
    return MENU


@team_decorator
def show_menu(bot, update, chat_data, team):
    keyboard = [[InlineKeyboardButton('Выбрать улицу', callback_data=CHOOSE_STREET)]]
    send_message_text(bot, update,
                      team.show(markdown=True),
                      reply_markup=InlineKeyboardMarkup(keyboard),
                      chat_data=chat_data,
                      parse_mode='Markdown')

STREET_PAGE_SIZE = 5


class ObjectSelector(object):
    _field_name = ''
    _state_name = ''
    _prev_state_name = ''
    _next_state_name = ''
    _add_state_name = ''
    _keyboard_size = (1, 5)

    def __init__(self):
        pass

    def _get_query_set(self, chat_data):
        return []

    def _get_text(self, chat_data):
        return ''

    def _get_pattern(self, chat_data):
        name = self._field_name + '_pattern'
        if name in chat_data:
            return chat_data[name]
        return None

    def _set_pattern(self, chat_data, pattern):
        chat_data[self._field_name + '_pattern'] = pattern

    def _del_pattern(self, chat_data):
        chat_data.pop(self._field_name + '_pattern', '')

    def _get_offset(self, chat_data):
        name = self._field_name + '_offset'
        if name in chat_data:
            return chat_data[name]
        return 0

    def _set_offset(self, chat_data, offset):
        chat_data[self._field_name + '_offset'] = offset

    def _del_offset(self, chat_data):
        chat_data.pop(self._field_name + '_offset', '')

    def _clear_data(self, chat_data):
        self._del_pattern(chat_data)
        self._del_offset(chat_data)

    @property
    def _page_size(self):
        return self._keyboard_size[0] * self._keyboard_size[1]

    def get_handlers(self):
        return {self._state_name: [EmptyHandler(self._handle_start, pass_chat_data=True),
                                   CallbackQueryHandler(self._handle_button, pass_chat_data=True),
                                   MessageHandler(Filters.text, self._handle_text, pass_chat_data=True)]}

    def _handle_start(self, bot, update, chat_data):
        query_set = self._get_query_set(chat_data)
        total_count = query_set.count()
        offset = self._get_offset(chat_data)
        if offset < 0:
            offset = 0
        if offset >= total_count:
            offset = max(0, total_count - self._page_size)
        self._set_offset(chat_data, offset)
        objects = list(query_set[offset:][:self._page_size])
        buttons = [InlineKeyboardButton(obj.show(markdown=False, full=False), callback_data=str(obj.id))
                   for obj in objects]
        keyboard = utils.chunks(buttons, self._keyboard_size[0])
        keyboard += build_paging_buttons(offset, total_count, self._page_size, True)
        pattern = self._get_pattern(chat_data)
        if pattern:
            keyboard.append([InlineKeyboardButton('-- Сбросить фильтр "%s" --' % pattern,
                                                  callback_data=CLEAR_FILTER)])
        keyboard.append([InlineKeyboardButton('+', callback_data=ADD_NEW_OBJECT)])
        keyboard.append([InlineKeyboardButton('<< Назад', callback_data=RETURN_TO_BACK)])

        send_message_text(bot, update,
                          self._get_text(chat_data) +
                          '\nВы можете сузить выбор, отправив сообщение с названием или его частью.'
                          '\nЕсли не получается найти нужный вам объект, можете его добавить, нажав на *+*.',
                          chat_data=chat_data,
                          parse_mode='Markdown',
                          reply_markup=InlineKeyboardMarkup(keyboard))

    def _handle_button(self, bot, update, chat_data):
        query = update.callback_query
        query.answer()
        if query.data == CLEAR_FILTER:
            self._del_pattern(chat_data)
            return
        elif query.data == ADD_NEW_OBJECT:
            return self._add_state_name
        elif query.data == RETURN_TO_BACK:
            self._clear_data(chat_data)
            return self._prev_state_name
        elif query.data == TO_BEGIN:
            self._set_offset(chat_data, 0)
        elif query.data == TO_END:
            self._set_offset(chat_data, 1000000)
        elif query.data == BACK:
            self._set_offset(chat_data, self._get_offset(chat_data) - self._page_size)
        elif query.data == FORWARD:
            self._set_offset(chat_data, self._get_offset(chat_data) + self._page_size)
        else:
            match = re.match('\d+', query.data)
            if match:
                chat_data[self._field_name + '_id'] = int(query.data)
                return self._next_state_name

    def _handle_text(self, bot, update, chat_data):
        self._set_pattern(chat_data, update.message.text)


class StreetSelector(ObjectSelector):
    _field_name = 'street'
    _prev_state_name = MENU
    _state_name = CHOOSE_STREET
    _next_state_name = CHOOSE_HOUSE
    _add_state_name = ADD_STREET

    def _get_query_set(self, chat_data):
        streets_set = models.Street.objects
        pattern = self._get_pattern(chat_data)
        if pattern:
            streets_set = streets_set.filter(name__icontains=pattern)
        return streets_set.all()

    def _get_text(self, chat_data):
        return 'Укажите *улицу*'


class HouseSelector(ObjectSelector):
    _field_name = 'house'
    _prev_state_name = CHOOSE_STREET
    _state_name = CHOOSE_HOUSE
    _next_state_name = CHOOSE_HOUSE_BLOCK
    _add_state_name = ADD_HOUSE
    _keyboard_size = (4, 4)

    def _get_query_set(self, chat_data):
        houses_set = models.House.objects.filter(street_id=chat_data['street_id'])
        pattern = self._get_pattern(chat_data)
        if pattern:
            houses_set = houses_set.filter(number__icontains=pattern)
        return houses_set.all()

    def _get_text(self, chat_data):
        street = models.Street.objects.get(id=chat_data['street_id'])
        return 'Укажите *дом* на %s' % street.show()


class HouseBlockSelector(ObjectSelector):
    _field_name = 'house_block'
    _prev_state_name = CHOOSE_HOUSE
    _state_name = CHOOSE_HOUSE_BLOCK
    _next_state_name = CHOOSE_FLAT
    _add_state_name = ADD_HOUSE_BLOCK
    _keyboard_size = (4, 4)

    def _get_query_set(self, chat_data):
        blocks_set = models.HouseBlock.objects.filter(house_id=chat_data['house_id'])
        pattern = self._get_pattern(chat_data)
        if pattern:
            blocks_set = blocks_set.filter(number__icontains=pattern)
        return blocks_set.all()

    def _get_text(self, chat_data):
        house = models.House.objects.select_related('street').get(id=chat_data['house_id'])
        return 'Выберите *подъезд* в %s' % house.show()


class FlatSelector(ObjectSelector):
    _field_name = 'flat'
    _prev_state_name = CHOOSE_HOUSE_BLOCK
    _state_name = CHOOSE_FLAT
    _next_state_name = CONTACT_FLAT
    _add_state_name = ADD_FLAT
    _keyboard_size = (3, 4)

    def _get_query_set(self, chat_data):
        flats_set = models.Flat.objects.filter(house_block_id=chat_data['house_block_id'])
        pattern = self._get_pattern(chat_data)
        if pattern:
            flats_set = flats_set.filter(number__icontains=pattern)
        return flats_set.all()

    def _get_text(self, chat_data):
        house_block = (models.HouseBlock
                             .objects
                             .select_related('house', 'house__street')
                             .get(id=chat_data['house_block_id']))
        return 'Выберите *квартиру* в %s' % house_block.show()


class StreetCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_STREET: [EmptyHandler(self._handle_start, pass_chat_data=True),
                             MessageHandler(Filters.text, team_decorator(self._handle_text), pass_chat_data=True),
                             standard_callback_query_handler]}

    def _handle_start(self, bot, update, chat_data):
        send_message_text(bot, update, 'Укажите название добавляемой улицы/проспекта/переулка. '
                                       'Используйте сокращения ул., пр., пер. и другие. '
                                       'Например, *Вознесенский пр.* или *ул. Мира*',
                          chat_data=chat_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_STREET)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, chat_data, team):
        street = models.Street(region=team.region,
                               name=update.message.text)
        street.save()
        chat_data['street_id'] = street.id
        return CHOOSE_HOUSE


class HouseCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_HOUSE: [EmptyHandler(self._handle_start, pass_chat_data=True),
                            MessageHandler(Filters.text, self._handle_text, pass_chat_data=True),
                            standard_callback_query_handler]}

    def _handle_start(self, bot, update, chat_data):
        street = models.Street.objects.get(id=chat_data['street_id'])
        send_message_text(bot, update, 'Укажите номер добавляемого дома на %s.\n'
                                       'Только номер, без слов "дом" и "д.". '
                                       'Например, 17, 16a, 22к1, 6стр1, 20/3.' % street.show(),
                          chat_data=chat_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_HOUSE)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, chat_data):
        house = models.House(street_id=chat_data['street_id'],
                             number=update.message.text)
        house.save()
        chat_data['house_id'] = house.id
        return CHOOSE_HOUSE_BLOCK


class HouseBlockCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_HOUSE_BLOCK: [EmptyHandler(self._handle_start, pass_chat_data=True),
                                  MessageHandler(Filters.text, self._handle_text, pass_chat_data=True),
                                  standard_callback_query_handler]}

    def _handle_start(self, bot, update, chat_data):
        house = models.House.objects.select_related('street').get(id=chat_data['house_id'])
        send_message_text(bot, update, 'Укажите номер добавляемого подъезда в %s.\n'
                                       'Только номер, без символов #, № и др.' % house.show(),
                          chat_data=chat_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_HOUSE_BLOCK)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, chat_data):
        house_block = models.HouseBlock(house_id=chat_data['house_id'],
                                        number=update.message.text)
        house_block.save()
        chat_data['house_block_id'] = house_block.id
        return CHOOSE_FLAT


class FlatCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_FLAT: [EmptyHandler(self._handle_start, pass_chat_data=True),
                           MessageHandler(Filters.text, self._handle_text, pass_chat_data=True),
                           standard_callback_query_handler]}

    def _handle_start(self, bot, update, chat_data):
        house_block = models.HouseBlock.objects.select_related('house', 'house__street')\
                            .get(id=chat_data['house_block_id'])
        send_message_text(bot, update, '%s.\n'
                                       'Укажите номер квартиры, или диапозон квартир.\n'
                                       'Например, *64* или *73-144*.' % house_block.show(),
                          chat_data=chat_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_FLAT)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, chat_data):
        text = update.message.text
        match = re.match('(\d+)(?:\s*-\s*(\d+))?', text)
        if not match:
            return
        groups = match.groups()
        if groups[1]:
            flat_numbers = range(int(groups[0]), int(groups[1]) + 1)
        else:
            flat_numbers = [int(groups[0])]
        with transaction.atomic():
            flat_ids = []
            for number in flat_numbers:
                flat = models.Flat(house_block_id=chat_data['house_block_id'],
                                   number=number)
                flat.save()
                flat_ids.append(flat.id)
            if len(flat_ids) == 1:
                chat_data['flat_id'] = flat_ids[0]
                return CONTACT_FLAT
            else:
                return CHOOSE_FLAT


class FlatContactor(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {CONTACT_FLAT: [EmptyHandler(team_decorator(self._handle_start), pass_chat_data=True),
                               CallbackQueryHandler(team_decorator(self._handle_button), pass_chat_data=True)]}

    def _handle_start(self, bot, update, chat_data, team):
        flat = models.Flat.objects.get(id=chat_data['flat_id'])
        my_flat_contact = models.FlatContact.objects.filter(team_id=team.id, flat_id=flat.id).first()
        another_flat_contact = None
        if not my_flat_contact:
            another_flat_contact = models.FlatContact.objects.filter(flat_id=flat.id) \
               .filter(Q(status__isnull=False) | ~Q(status=models.FlatContact.Status.NONE)).first()
            if not another_flat_contact and True:   # TODO
                my_flat_contact = models.FlatContact(flat=flat,
                                                     team=team,
                                                     start_time=datetime.now())
                my_flat_contact.save()

        keyboard = []
        if another_flat_contact:
            text = '%s\nКто-то из волонтеров уже контактировал с этой квартирой' % flat.show()
            keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])
        elif not my_flat_contact:
            text = flat.show()
            keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])
        elif my_flat_contact.status is not None:
            text = my_flat_contact.show()
            keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])
        else:
            text = my_flat_contact.show()
            for status in models.FlatContact.Status.choices:
                data = '%s_%d' % (SET_FLAT_CONTACT_STATUS, status[0])
                keyboard.append([InlineKeyboardButton(status[1], callback_data=data)])
            keyboard.append([InlineKeyboardButton('-- Отмена --', callback_data=CANCEL)])
        send_message_text(bot, update, text,
                          chat_data=chat_data,
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')

    def _handle_button(self, bot, update, chat_data, team):
        query = update.callback_query
        query.answer()
        if query.data == BACK:
            return CHOOSE_FLAT
        elif query.data == CANCEL:
            models.FlatContact.objects \
                .filter(team_id=team.id,
                        flat_id=chat_data['flat_id']
                        ).delete()
            return CHOOSE_FLAT
        else:
            match = re.match('%s_(\d+)' % SET_FLAT_CONTACT_STATUS, query.data)
            if match:
                flat_contact = models.FlatContact.objects\
                                     .filter(team_id=team.id,
                                             flat_id=chat_data['flat_id']
                                             )\
                                     .first()
                flat_contact.status = int(match.group(1))
                flat_contact.end_time = datetime.now()
                flat_contact.save()
                return CHOOSE_FLAT


def register(dp):
    states_handlers = {
        MENU: [EmptyHandler(show_menu, pass_chat_data=True), standard_callback_query_handler],
    }
    states_handlers.update(StreetSelector().get_handlers())
    states_handlers.update(StreetCreator().get_handlers())
    states_handlers.update(HouseSelector().get_handlers())
    states_handlers.update(HouseCreator().get_handlers())
    states_handlers.update(HouseBlockSelector().get_handlers())
    states_handlers.update(HouseBlockCreator().get_handlers())
    states_handlers.update(FlatSelector().get_handlers())
    states_handlers.update(FlatCreator().get_handlers())
    states_handlers.update(FlatContactor().get_handlers())
    conv_handler = ConversationHandler(
        per_user=False,
        per_chat=True,
        user_model=models.User,
        conversation_state_model=models.ConversationState,
        entry_points=[CommandHandler("start", start)],
        unknown_state_handler=EmptyHandler(cancel, pass_chat_data=True),
        states=states_handlers,
        pre_fallbacks=[],
        fallbacks=[CommandHandler('menu', cancel, pass_chat_data=True),
                   CommandHandler('cancel', cancel, pass_chat_data=True)]
    )
    # dp.add_handler(conv_handler)
