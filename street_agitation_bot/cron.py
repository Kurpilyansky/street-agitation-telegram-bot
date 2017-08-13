from django.db.models import Q
from django.db import transaction

from time import sleep
from datetime import datetime, timedelta
import heapq

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from street_agitation_bot import models, utils
from street_agitation_bot.bot_constants import *


class PriorityQueue:
    def __init__(self):
        self._heap = []

    def top(self):
        if self._heap:
            return self._heap[0]
        return None

    def push(self, element):
        heapq.heappush(self._heap, element)

    def pop(self):
        return heapq.heappop(self._heap)


class CronTab:
    def __init__(self, bot):
        self.bot = bot
        self.queue = PriorityQueue()

    def add_task(self, task):
        self.queue.push(task)

    def process_tasks(self):
        for i in range(10):
            task = self.queue.top()
            if not task:
                break
            moment = task.moment
            if moment > datetime.utcnow():
                break
            self.queue.pop()
            last_run = models.TaskRun.get_last_run(task.get_key())
            if last_run and moment <= last_run.run_moment:
                task.repeat()
            else:
                if task.process() and task.save_runs_in_database:
                    models.TaskRun.objects.create(task_key=task.get_key(),
                                                  scheduled_moment=moment,
                                                  run_moment=datetime.utcnow())


class AbstractTask:
    save_runs_in_database = True

    def __init__(self, first_moment, repeat_timespan, bot, cron_tab):
        self.moment = first_moment
        self._repeat_timespan = repeat_timespan
        self._bot = bot
        self._cron_tab = cron_tab

    def __lt__(self, other):
        return self.moment < other.moment

    def get_key(self):
        raise NotImplementedError()

    def process(self):
        pass

    def repeat(self):
        self.moment += self._repeat_timespan
        self._cron_tab.add_task(self)
        return True


class DeliveryCubeToEventTask(AbstractTask):
    def __init__(self, event, **kwargs):
        super().__init__(event.start_date - timedelta(hours=4, minutes=30),
                         timedelta(hours=1),
                         **kwargs)
        self._event_id = event.id
        self._prev_message_id = None

    def get_key(self):
        return 'DeliveryCubeToEventTask' + str(self._event_id)

    def process(self):
        event = models.AgitationEvent.objects.select_related('place__region', 'cubeusageinevent').filter(id=self._event_id).first()
        if not event:
            return
        region = event.place.region
        if self._prev_message_id:
            utils.safe_delete_message(self._bot, region.registrations_chat_id, self._prev_message_id)
        cube_usage = event.cubeusageinevent if hasattr(event, 'cubeusageinevent') else None
        if cube_usage and cube_usage.delivered_from and cube_usage.delivered_by:
            return
        new_message = self._bot.send_message(region.registrations_chat_id,
                                             'Необходимо доставить куб на %s %s' % (event.show(), event.place.show()),
                                             parse_mode='Markdown',
                                             reply_markup=InlineKeyboardMarkup([[
                                                InlineKeyboardButton(
                                                    'Спланировать',
                                                    callback_data=TRANSFER_CUBE_TO_EVENT + str(event.id))]]))
        self._prev_message_id = new_message.message_id
        return self.repeat()


class ShipCubeFromEventTask(AbstractTask):
    def __init__(self, event, **kwargs):
        super().__init__(event.start_date - timedelta(hours=3, minutes=20),
                         timedelta(hours=1),
                         **kwargs)
        self._event_id = event.id
        self._prev_message_id = None

    def get_key(self):
        return 'ShipCubeFromEventTask' + str(self._event_id)

    def process(self):
        event = models.AgitationEvent.objects.select_related('place__region', 'cubeusageinevent').filter(id=self._event_id).first()
        if not event or event.is_canceled:
            return
        region = event.place.region
        if self._prev_message_id:
            utils.safe_delete_message(self._bot, region.registrations_chat_id, self._prev_message_id)
        cube_usage = event.cubeusageinevent if hasattr(event, 'cubeusageinevent') else None
        if cube_usage and cube_usage.shipped_to and cube_usage.shipped_by:
            return
        new_message = self._bot.send_message(region.registrations_chat_id,
                                             'Необходимо увезти куб после %s %s' % (event.show(), event.place.show()),
                                             parse_mode='Markdown',
                                             reply_markup=InlineKeyboardMarkup([[
                                                InlineKeyboardButton(
                                                    'Спланировать',
                                                    callback_data=TRANSFER_CUBE_TO_EVENT + str(event.id))]]))
        self._prev_message_id = new_message.message_id
        return self.repeat()


class MakeTransferCubeTask(AbstractTask):
    save_runs_in_database = False

    def __init__(self, event, **kwargs):
        super().__init__(event.end_date,
                         timedelta(minutes=1),
                         **kwargs)
        self._event_id = event.id

    def get_key(self):
        return 'MakeTransferCubeTask' + str(self._event_id)

    def process(self):
        event = models.AgitationEvent.objects.filter(
            id=self._event_id).select_related('cubeusageinevent', 'cubeusageinevent__cube').first()
        if not event or event.is_canceled:
            return
        cube_usage = event.cubeusageinevent if hasattr(event, 'cubeusageinevent') else None
        if cube_usage and cube_usage.transferred_to_storage:
            return
        if not cube_usage or not cube_usage.shipped_by or not cube_usage.shipped_to:
            self.repeat()
        else:
            cube_usage = event.cubeusageinevent
            cube = cube_usage.cube
            with transaction.atomic():
                cube.last_storage = cube_usage.shipped_to
                cube_usage.transferred_to_storage = True
                cube_usage.save()
                cube.save()
        return True


def _cron_cycle(cron_tab):
    while True:
        cron_tab.process_tasks()
        sleep(0.1)


cron_tab = None


def init_all(updater):
    bot = updater.dispatcher.bot
    global cron_tab
    cron_tab = CronTab(bot)
    query_set = models.AgitationEvent.objects \
        .filter(need_cube=True, is_canceled=False) \
        .filter(Q(cubeusageinevent=None)
                | Q(cubeusageinevent__delivered_by=None)
                | Q(cubeusageinevent__delivered_from=None)
                | Q(cubeusageinevent__shipped_to=None)
                | Q(cubeusageinevent__shipped_by=None)
                | Q(cubeusageinevent__transferred_to_storage=False))
    for event in query_set:
        cron_tab.add_task(DeliveryCubeToEventTask(event, bot=bot, cron_tab=cron_tab))
        cron_tab.add_task(ShipCubeFromEventTask(event, bot=bot, cron_tab=cron_tab))
        cron_tab.add_task(MakeTransferCubeTask(event, bot=bot, cron_tab=cron_tab))

    updater._init_thread(lambda: _cron_cycle(cron_tab), "cron")  # TODO hack


def schedule_after_event_created(bot, event):
    if event.need_cube:
        cron_tab.add_task(DeliveryCubeToEventTask(event, bot=bot, cron_tab=cron_tab))
        cron_tab.add_task(ShipCubeFromEventTask(event, bot=bot, cron_tab=cron_tab))
