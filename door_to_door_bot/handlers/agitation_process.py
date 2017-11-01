
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

CHOOSE_STREET = 'CHOOSE_STREET'
ADD_STREET = 'ADD_STREET'
CHOOSE_HOUSE = 'CHOOSE_HOUSE'
ADD_HOUSE = 'ADD_HOUSE'
CHOOSE_HOUSE_BLOCK = 'CHOOSE_HOUSE_BLOCK'
ADD_HOUSE_BLOCK = 'ADD_HOUSE_BLOCK'
CHOOSE_FLAT = 'CHOOSE_FLAT'
ADD_FLAT = 'ADD_FLAT'
CONTACT_FLAT = 'CONTACT_FLAT'
SHOW_CONTACTS_HISTORY = 'SHOW_CONTACTS_HISTORY'

FLAT_CONTACT_REPORT = 'FLAT_CONTACT_REPORT'
FLAT_CONTACT_REPORT__SET_STATUS = 'FLAT_CONTACT_REPORT__SET_STATUS'
FLAT_CONTACT_REPORT__SET_COMMENT = 'FLAT_CONTACT_REPORT__SET_COMMENT'
FLAT_CONTACT_REPORT__SET_CONTACTS = 'FLAT_CONTACT_REPORT__SET_CONTACTS'

def team_decorator(func):
    def wrapper(bot, update, user_data, *args, **kwargs):
        if 'cur_team_id' not in user_data:
            raise AssertionError('cur_team_id is not set')
            # chat_id = update.effective_chat.id
            # team = models.AgitationTeam.objects.get(chat_id=chat_id)
            # chat_data['team_id'] = team.id
        else:
            team_id = int(user_data['cur_team_id'])
            team = models.AgitationTeam.objects.get(id=team_id)
        return func(bot, update, user_data=user_data, team=team, *args, **kwargs)

    return wrapper


@team_decorator
def show_menu(bot, update, user_data, team):
    keyboard = [[InlineKeyboardButton('Выбрать улицу', callback_data=CHOOSE_STREET)],
                [InlineKeyboardButton('История обхода', callback_data=SHOW_CONTACTS_HISTORY)],
                [InlineKeyboardButton('<< Главное меню', callback_data=END_AGITATION_PROCESS)]]
    send_message_text(bot, update,
                      team.show(markdown=True),
                      reply_markup=InlineKeyboardMarkup(keyboard),
                      user_data=user_data,
                      parse_mode='Markdown')


def end_agitation_process(bot, update, user_data):
    user_data.pop('cur_team_id', '')
    return MENU

STREET_PAGE_SIZE = 5


class ObjectSelector(object):
    _field_name = ''
    _state_name = ''
    _prev_state_name = ''
    _next_state_name = ''
    _add_state_name = ''
    _can_filter = False
    _keyboard_size = (1, 5)

    def __init__(self):
        pass

    def _get_query_set(self, user_data):
        return []

    def _get_text(self, user_data):
        return ''

    def _get_pattern(self, user_data):
        name = self._field_name + '_pattern'
        if name in user_data:
            return user_data[name]
        return None

    def _set_pattern(self, user_data, pattern):
        user_data[self._field_name + '_pattern'] = pattern

    def _del_pattern(self, user_data):
        user_data.pop(self._field_name + '_pattern', '')

    def _get_offset(self, user_data):
        name = self._field_name + '_offset'
        if name in user_data:
            return user_data[name]
        return 0

    def _set_offset(self, user_data, offset):
        user_data[self._field_name + '_offset'] = offset

    def _del_offset(self, user_data):
        user_data.pop(self._field_name + '_offset', '')

    def _clear_data(self, user_data):
        self._del_pattern(user_data)
        self._del_offset(user_data)

    @property
    def _page_size(self):
        return self._keyboard_size[0] * self._keyboard_size[1]

    def get_handlers(self):
        handlers = [EmptyHandler(self._handle_start, pass_user_data=True),
                    CallbackQueryHandler(self._handle_button, pass_user_data=True)]
        if self._can_filter:
            handlers.append(MessageHandler(Filters.text, self._handle_text, pass_user_data=True))
        return {self._state_name: handlers}

    def _handle_start(self, bot, update, user_data):
        query_set = self._get_query_set(user_data)
        total_count = query_set.count()
        offset = self._get_offset(user_data)
        if offset < 0:
            offset = 0
        if offset >= total_count:
            offset = max(0, total_count - self._page_size)
        self._set_offset(user_data, offset)
        objects = list(query_set[offset:][:self._page_size])
        buttons = [InlineKeyboardButton(obj.show(markdown=False, full=False), callback_data=str(obj.id))
                   for obj in objects]
        keyboard = utils.chunks(buttons, self._keyboard_size[0])
        keyboard += build_paging_buttons(offset, total_count, self._page_size, True)
        pattern = self._get_pattern(user_data)
        if pattern:
            keyboard.append([InlineKeyboardButton('-- Сбросить фильтр "%s" --' % pattern,
                                                  callback_data=CLEAR_FILTER)])
        if self._add_state_name:
            keyboard.append([InlineKeyboardButton('+', callback_data=ADD_NEW_OBJECT)])
        keyboard.append([InlineKeyboardButton('<< Назад', callback_data=RETURN_TO_BACK)])

        text = self._get_text(user_data)
        if self._can_filter:
            text += '\nВы можете сузить выбор, отправив сообщение с названием или его частью.'
        if self._add_state_name:
            text += '\nЕсли не получается найти нужный вам объект, можете его добавить, нажав на *+*.'
        send_message_text(bot, update,
                          text,
                          user_data=user_data,
                          parse_mode='Markdown',
                          reply_markup=InlineKeyboardMarkup(keyboard))

    def _handle_button(self, bot, update, user_data):
        query = update.callback_query
        query.answer()
        if query.data == CLEAR_FILTER:
            self._del_pattern(user_data)
            return
        elif query.data == ADD_NEW_OBJECT:
            return self._add_state_name
        elif query.data == RETURN_TO_BACK:
            self._clear_data(user_data)
            return self._prev_state_name
        elif query.data == TO_BEGIN:
            self._set_offset(user_data, 0)
        elif query.data == TO_END:
            self._set_offset(user_data, 1000000)
        elif query.data == BACK:
            self._set_offset(user_data, self._get_offset(user_data) - self._page_size)
        elif query.data == FORWARD:
            self._set_offset(user_data, self._get_offset(user_data) + self._page_size)
        else:
            match = re.match('\d+', query.data)
            if match:
                return self._handle_select_object(user_data, int(query.data))

    def _handle_select_object(self, user_data, object_id):
        user_data[self._field_name + '_id'] = object_id
        return self._next_state_name

    def _handle_text(self, bot, update, user_data):
        self._set_pattern(user_data, update.message.text)


class StreetSelector(ObjectSelector):
    _field_name = 'street'
    _prev_state_name = MENU
    _state_name = CHOOSE_STREET
    _next_state_name = CHOOSE_HOUSE
    _add_state_name = ADD_STREET
    _can_filter = True

    def _get_query_set(self, user_data):
        streets_set = models.Street.objects.order_by('name')
        pattern = self._get_pattern(user_data)
        if pattern:
            streets_set = streets_set.filter(name__icontains=pattern)
        return streets_set.all()

    def _get_text(self, user_data):
        return 'Укажите *улицу*'


class HouseSelector(ObjectSelector):
    _field_name = 'house'
    _prev_state_name = CHOOSE_STREET
    _state_name = CHOOSE_HOUSE
    _next_state_name = CHOOSE_HOUSE_BLOCK
    _add_state_name = ADD_HOUSE
    _can_filter = True
    _keyboard_size = (4, 4)

    def _get_query_set(self, user_data):
        houses_set = models.House.objects.filter(street_id=user_data['street_id']).order_by('number')
        pattern = self._get_pattern(user_data)
        if pattern:
            houses_set = houses_set.filter(number__icontains=pattern)
        return houses_set.all()

    def _get_text(self, user_data):
        street = models.Street.objects.get(id=user_data['street_id'])
        return 'Укажите *дом* на %s' % street.show()


class HouseBlockSelector(ObjectSelector):
    _field_name = 'house_block'
    _prev_state_name = CHOOSE_HOUSE
    _state_name = CHOOSE_HOUSE_BLOCK
    _next_state_name = CHOOSE_FLAT
    _add_state_name = ADD_HOUSE_BLOCK
    _can_filter = True
    _keyboard_size = (4, 4)

    def _get_query_set(self, user_data):
        blocks_set = models.HouseBlock.objects.filter(house_id=user_data['house_id']).order_by('number')
        pattern = self._get_pattern(user_data)
        if pattern:
            blocks_set = blocks_set.filter(number__icontains=pattern)
        return blocks_set.all()

    def _get_text(self, user_data):
        house = models.House.objects.select_related('street').get(id=user_data['house_id'])
        return 'Выберите *подъезд* в %s' % house.show()


class FlatSelector(ObjectSelector):
    _field_name = 'flat'
    _prev_state_name = CHOOSE_HOUSE_BLOCK
    _state_name = CHOOSE_FLAT
    _next_state_name = CONTACT_FLAT
    _add_state_name = ADD_FLAT
    _can_filter = True
    _keyboard_size = (3, 4)

    def _get_query_set(self, user_data):
        flats_set = models.Flat.objects.filter(house_block_id=user_data['house_block_id']).order_by('number')
        pattern = self._get_pattern(user_data)
        if pattern:
            flats_set = flats_set.filter(number__icontains=pattern)
        return flats_set.all()

    def _get_text(self, user_data):
        house_block = (models.HouseBlock
                             .objects
                             .select_related('house', 'house__street')
                             .get(id=user_data['house_block_id']))
        return 'Выберите *квартиру* в %s' % house_block.show()


class ContactsHistoryShower(ObjectSelector):
    _field_name = 'flat_contact'
    _prev_state_name = MENU
    _state_name = SHOW_CONTACTS_HISTORY
    _next_state_name = CONTACT_FLAT
    _can_filter = False
    _keyboard_size = (1, 7)

    def _get_query_set(self, user_data):
        contacts_set = models.FlatContact.objects\
                             .filter(team_id=user_data['cur_team_id'])\
                             .order_by('-start_time')
        return contacts_set.all()

    def _get_text(self, user_data):
        return '*История агитации*'

    def _handle_select_object(self, user_data, object_id):
        flat_contact = models.FlatContact.objects\
                             .filter(id=object_id)\
                             .select_related('flat',
                                             'flat__house_block',
                                             'flat__house_block__house',
                                             'flat__house_block__house__street')\
                             .first()
        if flat_contact:
            self._clear_data(user_data)
            flat = flat_contact.flat
            user_data['flat_id'] = flat.id
            house_block = flat.house_block
            user_data['house_block_id'] = house_block.id
            house = house_block.house
            user_data['house_id'] = house.id
            street = house.street
            user_data['street_id'] = street.id
            return CONTACT_FLAT


class StreetCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_STREET: [EmptyHandler(self._handle_start, pass_user_data=True),
                             MessageHandler(Filters.text, team_decorator(self._handle_text), pass_user_data=True),
                             standard_callback_query_handler]}

    def _handle_start(self, bot, update, user_data):
        send_message_text(bot, update, 'Укажите название добавляемой улицы/проспекта/переулка. '
                                       'Используйте сокращения ул., пр., пер. и другие. '
                                       'Например, *Вознесенский пр.* или *ул. Мира*',
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_STREET)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, user_data, team):
        street = models.Street(region=team.region,
                               name=update.message.text)
        street.save()
        user_data['street_id'] = street.id
        return CHOOSE_HOUSE


class HouseCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_HOUSE: [EmptyHandler(self._handle_start, pass_user_data=True),
                            MessageHandler(Filters.text, self._handle_text, pass_user_data=True),
                            standard_callback_query_handler]}

    def _handle_start(self, bot, update, user_data):
        street = models.Street.objects.get(id=user_data['street_id'])
        send_message_text(bot, update, 'Укажите номер добавляемого дома на %s.\n'
                                       'Только номер, без слов "дом" и "д.". '
                                       'Например, 17, 16a, 22к1, 6стр1, 20/3.' % street.show(),
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_HOUSE)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, user_data):
        house = models.House(street_id=user_data['street_id'],
                             number=update.message.text)
        house.save()
        user_data['house_id'] = house.id
        return CHOOSE_HOUSE_BLOCK


class HouseBlockCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_HOUSE_BLOCK: [EmptyHandler(self._handle_start, pass_user_data=True),
                                  MessageHandler(Filters.text, self._handle_text, pass_user_data=True),
                                  standard_callback_query_handler]}

    def _handle_start(self, bot, update, user_data):
        house = models.House.objects.select_related('street').get(id=user_data['house_id'])
        send_message_text(bot, update, 'Укажите номер добавляемого подъезда в %s.\n'
                                       'Только номер, без символов #, № и др.' % house.show(),
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_HOUSE_BLOCK)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, user_data):
        house_block = models.HouseBlock(house_id=user_data['house_id'],
                                        number=update.message.text)
        house_block.save()
        user_data['house_block_id'] = house_block.id
        return CHOOSE_FLAT


class FlatCreator(object):
    def __init__(self):
        pass

    def get_handlers(self):
        return {ADD_FLAT: [EmptyHandler(self._handle_start, pass_user_data=True),
                           MessageHandler(Filters.text, self._handle_text, pass_user_data=True),
                           standard_callback_query_handler]}

    def _handle_start(self, bot, update, user_data):
        house_block = models.HouseBlock.objects.select_related('house', 'house__street')\
                            .get(id=user_data['house_block_id'])
        send_message_text(bot, update, '%s.\n'
                                       'Укажите номер квартиры, или диапозон квартир.\n'
                                       'Например, *64* или *73-144*.' % house_block.show(),
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('<< Назад', callback_data=CHOOSE_FLAT)]]),
                          parse_mode='Markdown')

    def _handle_text(self, bot, update, user_data):
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
                flat = models.Flat(house_block_id=user_data['house_block_id'],
                                   number=number)
                flat.save()
                flat_ids.append(flat.id)
            if len(flat_ids) == 1:
                user_data['flat_id'] = flat_ids[0]
                return CONTACT_FLAT
            else:
                return CHOOSE_FLAT


class FlatContactor(object):
    def __init__(self):
        pass

    _count_fields = ['newspapers_count', 'flyers_count', 'registrations_count']
    _human_name = {'newspapers_count': 'Газета',
                   'flyers_count': 'Листовка',
                   'registrations_count': 'Регистрация'}

    def get_handlers(self):
        handlers = {
            CONTACT_FLAT: [
                    EmptyHandler(team_decorator(self._handle_start), pass_user_data=True),
                    CallbackQueryHandler(team_decorator(self._handle_button), pass_user_data=True)
                ],
            FLAT_CONTACT_REPORT: [
                    EmptyHandler(team_decorator(self._handle_report_start), pass_user_data=True),
                    CallbackQueryHandler(team_decorator(self._handle_report_button), pass_user_data=True)
                ],
            FLAT_CONTACT_REPORT__SET_STATUS: [
                    EmptyHandler(team_decorator(self._handle_report__set_status_start), pass_user_data=True),
                    CallbackQueryHandler(team_decorator(self._handle_report__set_status_button), pass_user_data=True)
                ]
        }
        handlers.update(self.ReportCommentSetter(self).get_handlers())
        handlers.update(self.ReportContactsSetter(self).get_handlers())
        return handlers

    def _handle_start(self, bot, update, user_data, team):
        flat = models.Flat.objects.get(id=user_data['flat_id'])
        my_flat_contact = models.FlatContact.objects.filter(team_id=team.id, flat_id=flat.id).first()
        another_flat_contact = None
        if not my_flat_contact:
            another_flat_contact = models.FlatContact.objects.filter(flat_id=flat.id) \
               .filter(Q(status__isnull=False) | ~Q(status=models.FlatContact.Status.NONE)).first()
            if not another_flat_contact and True:   # TODO
                user = models.User.find_by_telegram_id(update.effective_user.id)
                my_flat_contact = models.FlatContact(flat=flat,
                                                     team=team,
                                                     start_time=datetime.now(),
                                                     created_by=user)
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
            keyboard.append([InlineKeyboardButton('Изменить', callback_data=FLAT_CONTACT_REPORT)])
            keyboard.append([InlineKeyboardButton('<< Назад', callback_data=BACK)])
        else:
            return FLAT_CONTACT_REPORT
        send_message_text(bot, update, text,
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')

    def _handle_button(self, bot, update, user_data, team):
        query = update.callback_query
        query.answer()
        if query.data in [FLAT_CONTACT_REPORT]:
            return query.data
        elif query.data == BACK:
            return CHOOSE_FLAT

    def _build_report_text(self, flat_contact, report):
        lines = [flat_contact.show(full=False)]
        if report['status'] is not None:
            lines.append('Статус: %s' % models.FlatContact.Status.get_choice(report['status']).label)
        for name in self._count_fields:
            report[name] = int(report[name])
            if report[name]:
                lines.append('%s: %d' % (self._human_name[name], report[name]))
        if report['comment']:
            lines.append('Комментарий: %s' % report['comment'])
        if report['contacts']:
            lines.append('Контакты: %s' % report['contacts'])
        return '\n'.join(lines)

    def _handle_report_start(self, bot, update, user_data, team):
        flat = models.Flat.objects.get(id=user_data['flat_id'])
        my_flat_contact = models.FlatContact.objects.filter(team_id=team.id, flat_id=flat.id).first()
        if not my_flat_contact:
            return CHOOSE_FLAT
        if 'report' not in user_data:
            user_data['report'] = my_flat_contact.get_report_as_dict()
        report = user_data['report']
        if report['status'] is None:
            return FLAT_CONTACT_REPORT__SET_STATUS
        keyboard = []
        for name in self._count_fields:
            keyboard.append([InlineKeyboardButton('+ ' + self._human_name[name], callback_data='+' + name),
                             InlineKeyboardButton('- ' + self._human_name[name], callback_data='-' + name)])
        keyboard.append([InlineKeyboardButton('Изменить статус', callback_data=FLAT_CONTACT_REPORT__SET_STATUS)])
        keyboard.append([InlineKeyboardButton('Изменить комментарий' if report['comment'] else 'Оставить комментарий',
                                              callback_data=FLAT_CONTACT_REPORT__SET_COMMENT)])
        keyboard.append([InlineKeyboardButton('Изменить контакты' if report['contacts'] else 'Оставить контакты',
                                              callback_data=FLAT_CONTACT_REPORT__SET_CONTACTS)])
        keyboard.append([InlineKeyboardButton('-- Сохранить --', callback_data=END)])
        if my_flat_contact.end_time:
            keyboard.append([InlineKeyboardButton('-- Отмена --', callback_data=CANCEL)])

        send_message_text(bot, update, self._build_report_text(my_flat_contact, report),
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')

    def _handle_report_button(self, bot, update, user_data, team):
        query = update.callback_query
        query.answer()
        if query.data in [FLAT_CONTACT_REPORT__SET_STATUS,
                          FLAT_CONTACT_REPORT__SET_COMMENT,
                          FLAT_CONTACT_REPORT__SET_CONTACTS]:
            return query.data
        if query.data == END:
            flat = models.Flat.objects.get(id=user_data['flat_id'])
            my_flat_contact = models.FlatContact.objects.filter(team_id=team.id, flat_id=flat.id).first()
            my_flat_contact.update_report(user_data['report'])
            if my_flat_contact.end_time is None:
                my_flat_contact.end_time = datetime.now()
            my_flat_contact.save()
            del user_data['report']
            return CONTACT_FLAT
        elif query.data == CANCEL:
            del user_data['report']
            return CONTACT_FLAT
        elif query.data[0] == '+' or query.data[0] == '-':
            name = query.data[1:]
            delta = 1 if query.data[0] == '+' else -1
            user_data['report'][name] = max(0, int(user_data['report'][name]) + delta)

    def _handle_report__set_status_start(self, bot, update, user_data, team):
        flat = models.Flat.objects.get(id=user_data['flat_id'])
        my_flat_contact = models.FlatContact.objects.filter(team_id=team.id, flat_id=flat.id).first()
        report = user_data['report']
        keyboard = []
        for status in models.FlatContact.Status.choices:
            data = '%s_%d' % (SET_FLAT_CONTACT_STATUS, status[0])
            keyboard.append([InlineKeyboardButton(status[1], callback_data=data)])
        keyboard.append([InlineKeyboardButton('-- Отмена --', callback_data=CANCEL)])
        send_message_text(bot, update, self._build_report_text(my_flat_contact, report),
                          user_data=user_data,
                          reply_markup=InlineKeyboardMarkup(keyboard),
                          parse_mode='Markdown')

    def _handle_report__set_status_button(self, bot, update, user_data, team):
        query = update.callback_query
        query.answer()
        report = user_data['report']
        if query.data == CANCEL:
            if report['status'] is None:
                models.FlatContact.objects \
                    .filter(team_id=team.id,
                            flat_id=user_data['flat_id']
                            ).delete()
                return CHOOSE_FLAT
            else:
                return FLAT_CONTACT_REPORT
        else:
            match = re.match('%s_(\d+)' % SET_FLAT_CONTACT_STATUS, query.data)
            if match:
                report['status'] = int(match.group(1))
                return FLAT_CONTACT_REPORT

    class ReportStringSetter(object):
        state = ''
        field_name = ''
        human_field_name = ''

        def __init__(self, contactor):
            self.contactor = contactor

        def get_handlers(self):
            return {self.state: [EmptyHandler(team_decorator(self._handle_start), pass_user_data=True),
                                 CallbackQueryHandler(self._handle_button, pass_user_data=True),
                                 MessageHandler(Filters.text, self._handle_text, pass_user_data=True)]}

        def _handle_start(self, bot, update, user_data, team):
            flat = models.Flat.objects.get(id=user_data['flat_id'])
            my_flat_contact = models.FlatContact.objects.filter(team_id=team.id, flat_id=flat.id).first()
            report = user_data['report']
            keyboard = []
            if report[self.field_name]:
                keyboard.append([InlineKeyboardButton('Удалить %s' % self.human_field_name,
                                                      callback_data=DELETE)])
            keyboard.append([InlineKeyboardButton('-- Отмена --', callback_data=CANCEL)])
            send_message_text(bot, update,
                              '%s\n\n*Введите %s*' % (self.contactor._build_report_text(my_flat_contact, report),
                                                      self.human_field_name),
                              user_data=user_data,
                              parse_mode='Markdown',
                              reply_markup=InlineKeyboardMarkup(keyboard))

        def _handle_text(self, bot, update, user_data):
            user_data['report'][self.field_name] = update.message.text
            return FLAT_CONTACT_REPORT

        def _handle_button(self, bot, update, user_data):
            query = update.callback_query
            query.answer()
            if query.data == DELETE:
                user_data['report'][self.field_name] = None
            return FLAT_CONTACT_REPORT

    class ReportCommentSetter(ReportStringSetter):
        state = FLAT_CONTACT_REPORT__SET_COMMENT
        field_name = 'comment'
        human_field_name = 'комментарий'

    class ReportContactsSetter(ReportStringSetter):
        state = FLAT_CONTACT_REPORT__SET_CONTACTS
        field_name = 'contacts'
        human_field_name = 'контакты (телефон, e-mail)'



state_handlers = {
    # MENU: [EmptyHandler(show_menu, pass_user_data=True), standard_callback_query_handler],
    END_AGITATION_PROCESS: [EmptyHandler(end_agitation_process, pass_user_data=True)]
}
state_handlers.update(StreetSelector().get_handlers())
state_handlers.update(StreetCreator().get_handlers())
state_handlers.update(HouseSelector().get_handlers())
state_handlers.update(HouseCreator().get_handlers())
state_handlers.update(HouseBlockSelector().get_handlers())
state_handlers.update(HouseBlockCreator().get_handlers())
state_handlers.update(FlatSelector().get_handlers())
state_handlers.update(FlatCreator().get_handlers())
state_handlers.update(FlatContactor().get_handlers())
state_handlers.update(ContactsHistoryShower().get_handlers())
