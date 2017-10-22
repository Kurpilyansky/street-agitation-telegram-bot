import re

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
        return func(bot, update, chat_data, team=team, *args, **kwargs)

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
        offset = self._get_offset(chat_data)
        if offset < 0 or offset >= query_set.count():
            offset = 0
        objects = list(query_set[offset:][:self._page_size])
        buttons = [InlineKeyboardButton(obj.show(markdown=False, full=False), callback_data=str(obj.id))
                   for obj in objects]
        keyboard = utils.chunks(buttons, self._keyboard_size[0])
        keyboard += build_paging_buttons(offset, query_set.count(), self._page_size)
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
        elif query.data == BACK:
            self._set_offset(chat_data, self._get_offset(chat_data) + self._page_size)
        elif query.data == FORWARD:
            self._set_offset(chat_data, self._get_offset(chat_data) - self._page_size)
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

    def _get_query_set(self, chat_data):
        houses_set = models.House.objects
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

    def _get_query_set(self, chat_data):
        blocks_set = models.HouseBlock.objects
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

    def _get_query_set(self, chat_data):
        flats_set = models.Flat.objects
        pattern = self._get_pattern(chat_data)
        if pattern:
            flats_set = flats_set.filter(number__icontains=pattern)
        return flats_set.all()

    def _get_text(self, chat_data):
        house_block = (models.HouseBlock
                             .objects
                             .select_related('house', 'house__street')
                             .get(id=chat_data['house_id']))
        return 'Выберите *квартиру* в %s' % house_block.show()


def register(dp):
    states_handlers = {
        MENU: [EmptyHandler(show_menu, pass_chat_data=True), standard_callback_query_handler],
    }
    states_handlers.update(StreetSelector().get_handlers())
    states_handlers.update(HouseSelector().get_handlers())
    states_handlers.update(HouseBlockSelector().get_handlers())
    states_handlers.update(FlatSelector().get_handlers())
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
    dp.add_handler(conv_handler)
