#!/usr/bin/env python
#
# A library that provides a Python interface to the Telegram Bot API
# Copyright (C) 2015-2017
# Leandro Toledo de Souza <devs@python-telegram-bot.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].
""" This module contains the ConversationHandler """

import json
import logging

from telegram import Update
from telegram.ext import (Filters, Handler, CallbackQueryHandler, InlineQueryHandler,
                          ChosenInlineResultHandler)
from telegram.utils.promise import Promise

import datetime


# def json_handler(self, obj):
#     if hasattr(obj, 'isoformat'):
#         return obj.isoformat()
#     else:
#         raise(TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj)))
#
# json.JSONEncoder.default = json_handler


class EmptyHandler(Handler):

    def check_update(self, update):
        return False

    def handle_update(self, update, dispatcher):
        optional_args = self.collect_optional_args(dispatcher, update)
        return self.callback(dispatcher.bot, update, **optional_args)


class ConversationHandler(Handler):
    """
    A handler to hold a conversation with a single user by managing four collections of other
    handlers. Note that neither posts in Telegram Channels, nor group interactions with multiple
    users are managed by instances of this class.

    The first collection, a ``list`` named ``entry_points``, is used to initiate the conversation,
    for example with a ``CommandHandler`` or ``RegexHandler``.

    The second collection, a ``dict`` named ``states``, contains the different conversation steps
    and one or more associated handlers that should be used if the user sends a message when the
    conversation with them is currently in that state. You will probably use mostly
    ``MessageHandler`` and ``RegexHandler`` here.

    The third collection, a ``list`` named ``fallbacks``, is used if the user is currently in a
    conversation but the state has either no associated handler or the handler that is associated
    to the state is inappropriate for the update, for example if the update contains a command, but
    a regular text message is expected. You could use this for a ``/cancel`` command or to let the
    user know their message was not recognized.

    The fourth, optional collection of handlers, a ``list`` named ``timed_out_behavior`` is used if
    the wait for ``run_async`` takes longer than defined in ``run_async_timeout``. For example,
    you can let the user know that they should wait for a bit before they can continue.

    To change the state of conversation, the callback function of a handler must return the new
    state after responding to the user. If it does not return anything (returning ``None`` by
    default), the state will not change. To end the conversation, the callback function must
    return ``CallbackHandler.END`` or ``-1``.

    Args:
        entry_points (list): A list of ``Handler`` objects that can trigger the start of the
            conversation. The first handler which ``check_update`` method returns ``True`` will be
            used. If all return ``False``, the update is not handled.
        states (dict): A ``dict[object: list[Handler]]`` that defines the different states of
            conversation a user can be in and one or more associated ``Handler`` objects that
            should be used in that state. The first handler which ``check_update`` method returns
            ``True`` will be used.
        fallbacks (list): A list of handlers that might be used if the user is in a conversation,
            but every handler for their current state returned ``False`` on ``check_update``.
            The first handler which ``check_update`` method returns ``True`` will be used. If all
            return ``False``, the update is not handled.
        allow_reentry (Optional[bool]): If set to ``True``, a user that is currently in a
            conversation can restart the conversation by triggering one of the entry points.
        run_async_timeout (Optional[float]): If the previous handler for this user was running
            asynchronously using the ``run_async`` decorator, it might not be finished when the
            next message arrives. This timeout defines how long the conversation handler should
            wait for the next state to be computed. The default is ``None`` which means it will
            wait indefinitely.
        timed_out_behavior (Optional[list]): A list of handlers that might be used if
            the wait for ``run_async`` timed out. The first handler which ``check_update`` method
            returns ``True`` will be used. If all return ``False``, the update is not handled.

    """

    END = -1

    def __init__(self,
                 entry_points,
                 states,
                 unknown_state_handler,
                 fallbacks,
                 pre_fallbacks,
                 user_model,
                 conversation_state_model,
                 allow_reentry=False,
                 run_async_timeout=None,
                 timed_out_behavior=None,
                 per_user=True,
                 per_chat=False):

        self.entry_points = entry_points
        """:type: list[telegram.ext.Handler]"""

        self.states = states
        """:type: dict[str: telegram.ext.Handler]"""

        self.unknown_state_handler = unknown_state_handler

        self.pre_fallbacks = pre_fallbacks
        self.fallbacks = fallbacks
        """:type: list[telegram.ext.Handler]"""

        self.user_model = user_model
        self.conversation_state_model = conversation_state_model

        self.allow_reentry = allow_reentry
        self.run_async_timeout = run_async_timeout

        self.timed_out_behavior = timed_out_behavior
        """:type: list[telegram.ext.Handler]"""

        self._state_in_database = dict()
        self._need_update_user_data = dict()
        self.conversations = dict()
        self.per_user = per_user
        self.per_chat = per_chat
        if per_user and per_chat:
            raise ValueError()
        """:type: dict[tuple: object]"""

        self.current_conversation = None
        self.current_handler = None

        self.logger = logging.getLogger(__name__)

        for state_handlers in states.values():
            for handler in state_handlers[1:]:
                if isinstance(handler, EmptyHandler):
                    logging.warning("EmptyHandler at non-first position will not be called")

        # all_handlers = list()
        # all_handlers.extend(entry_points)
        # all_handlers.extend(fallbacks)
        # for state_handlers in states.values():
        #     all_handlers.extend(state_handlers)
        #
        # if self.per_message:
        #     for handler in all_handlers:
        #         if not isinstance(handler, CallbackQueryHandler):
        #             logging.warning("If 'per_message=True', all entry points and state handlers"
        #                             " must be 'CallbackQueryHandler', since no other handlers "
        #                             "have a message context.")
        # else:
        #     for handler in all_handlers:
        #         if isinstance(handler, CallbackQueryHandler):
        #             logging.warning("If 'per_message=False', 'CallbackQueryHandler' will not be "
        #                             "tracked for every message.")
        #
        # if self.per_chat:
        #     for handler in all_handlers:
        #         if isinstance(handler, (InlineQueryHandler, ChosenInlineResultHandler)):
        #             logging.warning("If 'per_chat=True', 'InlineQueryHandler' can not be used, "
        #                             "since inline queries have no chat context.")

    def _get_key(self, update):
        if self.per_user:
            return update.effective_user.id
        elif self.per_chat:
            return update.effective_chat.id
        else:
            return None

    def check_update(self, update):

        # Ignore messages in channels
        if (not isinstance(update, Update)
                or update.channel_post):
                # or self.per_chat and (update.inline_query or update.chosen_inline_result)
                # or self.per_message and not update.callback_query
                # or update.callback_query and self.per_chat and not update.callback_query.message):
            return False
        if (self.per_user and    # TODO hack
                not update.callback_query and Filters.group(update.effective_message)):
            return False
        if (self.per_chat and    # TODO hack
                not update.callback_query and Filters.private(update.effective_message)):
            return False

        key = self._get_key(update)
        self._load_state(key)
        state = self.conversations.get(key)

        # Resolve promises
        if isinstance(state, tuple) and len(state) is 2 and isinstance(state[1], Promise):
            self.logger.debug('waiting for promise...')

            old_state, new_state = state
            error = False
            try:
                res = new_state.result(timeout=self.run_async_timeout)
            except Exception as exc:
                self.logger.exception("Promise function raised exception")
                self.logger.exception("{}".format(exc))
                error = True

            if not error and new_state.done.is_set():
                self.update_state(res, key)
                state = self.conversations.get(key)

            else:
                for candidate in (self.timed_out_behavior or []):
                    if candidate.check_update(update):
                        # Save the current user and the selected handler for handle_update
                        self.current_conversation = key
                        self.current_handler = candidate

                        return True

                else:
                    return False

        self.logger.debug('selecting conversation %s with state %s' % (str(key), str(state)))

        handler = None

        if state is not None:
            for pre_fallback in self.pre_fallbacks:
                if pre_fallback.check_update(update):
                    handler = pre_fallback
                    break


        # Search entry points for a match
        if not handler and (state is None or self.allow_reentry):
            for entry_point in self.entry_points:
                if entry_point.check_update(update):
                    handler = entry_point
                    break
            else:
                if state is None:
                    return False

        if state is not None and not handler:
            if state not in self.states:
                handler = self.unknown_state_handler

        # Get the handler list for current state, if we didn't find one yet and we're still here
        if state is not None and not handler:
            handlers = self.states.get(state)

            for candidate in (handlers or []):
                if candidate.check_update(update):
                    handler = candidate
                    break

            # Find a fallback handler if all other handlers fail
            else:
                for fallback in self.fallbacks:
                    if fallback.check_update(update):
                        handler = fallback
                        break

                else:
                    return False

        # Save the current user and the selected handler for handle_update
        self.current_conversation = key
        self.current_handler = handler

        return True

    def _handle_update(self, update, dispatcher):
        new_state = self.current_handler.handle_update(update, dispatcher)
        self.update_state(new_state, self.current_conversation)

    def handle_update(self, update, dispatcher):
        key = self.current_conversation
        if self._need_update_user_data.get(key):
            self.__get_user_data_dict(dispatcher)[key] = json.loads(self._state_in_database[key].data)
            del self._need_update_user_data[key]
        self._handle_update(update, dispatcher)
        visited = dict()
        while key in self.conversations:
            state = self.conversations.get(key)
            handlers = self.states.get(state, [self.unknown_state_handler])
            if (state in visited) or (not handlers) or (not isinstance(handlers[0], EmptyHandler)):
                break
            visited[state] = True
            self.current_handler = handlers[0]
            self._handle_update(update, dispatcher)
        self._save_state(key, dispatcher, update.effective_user.id)

    def update_state(self, new_state, key):
        if new_state == self.END:
            if key in self.conversations:
                del self.conversations[key]
            else:
                pass

        elif isinstance(new_state, Promise):
            self.conversations[key] = (self.conversations.get(key), new_state)

        elif new_state is not None:
            self.conversations[key] = new_state

    def _load_state(self, key):
        if key not in self.conversations and key not in self._state_in_database:
            state_in_database = self.conversation_state_model.objects.filter(key=key).first()
            if state_in_database:
                self.conversations[key] = state_in_database.state
                self._need_update_user_data[key] = True
                self._state_in_database[key] = state_in_database
            else:
                self._state_in_database[key] = self.conversation_state_model(key=key)

    def _save_state(self, key, dispatcher, user_telegram_id):
        state_in_database = self._state_in_database.get(key, self.conversation_state_model(key=key))
        user = self.user_model.find_by_telegram_id(user_telegram_id)
        if user:
            state_in_database.agitator = user
        state_in_database.state = self.conversations.get(key)
        state_in_database.data = json.dumps(self.__get_user_data_dict(dispatcher).get(key))
        state_in_database.save()
        self._state_in_database[key] = state_in_database

    def __get_user_data_dict(self, dispatcher):
        if self.per_user:
            return dispatcher.user_data
        elif self.per_chat:
            return dispatcher.chat_data
        else:
            return dict()
