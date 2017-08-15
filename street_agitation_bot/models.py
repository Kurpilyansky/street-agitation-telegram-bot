# -*- coding: utf-8 -*-

from django.db.models import Q
from django.db import transaction

from django.db import models

from street_agitation_bot import bot_settings, utils
from street_agitation_bot.emoji import *

from datetime import timedelta


class Region(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True, unique=True)
    registrations_chat_id = models.BigIntegerField()

    timezone_delta = models.IntegerField(help_text='Разница с UTC в секундах, например, для UTC+3 указано +10800')

    is_public = models.BooleanField()

    @classmethod
    def find_by_name(cls, name, user_id=None):
        region = cls.objects.filter(name=name).first()
        if region and (region.is_public or bot_settings.is_admin_user_id(user_id)):
            return region
        return None

    @classmethod
    def get_by_id(cls, region_id):
        return cls.objects.get(id=region_id)

    def show(self, markdown=True):
        if markdown:
            return utils.escape_markdown(self.name)
        else:
            return self.name

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)


class User(models.Model):
    telegram_id = models.IntegerField(null=True, blank=True)
    telegram = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=200, blank=False, null=False)
    last_name = models.CharField(max_length=200, blank=False, null=False)
    phone = models.CharField(max_length=50, blank=False, null=False)

    registration_date = models.DateTimeField(auto_now_add=True)

    @classmethod
    def _single_by(cls, field_name, params):
        field_value = params.get(field_name, None)
        if not field_value:
            return None
        query_set = cls.objects.filter(**{field_name: field_value})
        users = list(query_set[0:2])
        if len(users) == 1:
            return users[0]
        return None

    @classmethod
    def update_or_create(cls, params):
        params['phone'] = utils.clean_phone_number(params['phone'])
        with transaction.atomic():
            user_by_telegram_id = cls._single_by('telegram_id', params)
            user_by_telegram = cls._single_by('telegram', params)
            user_by_phone = cls._single_by('phone', params)
            candidate_ids = {u.id for u in [user_by_telegram_id, user_by_telegram, user_by_phone] if u}
            if len(candidate_ids) > 1:
                raise ValueError("User collisions")
            elif len(candidate_ids) == 1:
                if not params.get('first_name', None):
                    params.pop('first_name', None)
                if not params.get('last_name', None):
                    params.pop('last_name', None)

                old_id = candidate_ids.pop()
                cls.objects.filter(id=old_id).update(**params)
                return cls.objects.filter(id=old_id).first(), False
            else:
                if not params.get('first_name', None):
                    params['first_name'] = '?'
                if not params.get('last_name', None):
                    params['last_name'] = '?'
                print(params)
                return cls.objects.create(**params), True

    def show(self, markdown=True, private=True):
        if private:
            return self.show_full()
        else:
            return self.full_name

    @property
    def full_name(self):
        return "%s %s" % (self.last_name, self.first_name)

    @property
    def regions(self):
        return list(Region.objects.filter(agitatorinregion__agitator_id=self.id).all())

    @classmethod
    def find_by_telegram_id(cls, id):
        return cls.objects.filter(telegram_id=id).first()

    def show_full(self):
        if not self.telegram_id:
            return utils.escape_markdown('%s %s' % (self.full_name, self.phone))
        elif self.telegram:
            return utils.escape_markdown('%s @%s %s' % (self.full_name, self.telegram, self.phone))
        else:
            return utils.escape_markdown('@%s (%s) %s' % (self.telegram_id, self.full_name, self.phone))

    def __str__(self):
        return '@%s (%s) @%s' % (self.telegram_id, self.full_name, self.telegram)


class AdminRights(models.Model):
    user = models.ForeignKey(User)
    region = models.ForeignKey(Region, null=True, blank=True)

    @classmethod
    def has_admin_rights(cls, user_telegram_id, region_id):
        return bool(cls.objects.filter(user__telegram_id=user_telegram_id)
                               .filter(Q(region=None) | Q(region_id=region_id))
                               .first())

    class Meta:
        unique_together = ('user', 'region')


class AgitatorInRegion(models.Model):
    agitator = models.ForeignKey(User)
    region = models.ForeignKey(Region)

    have_registration = models.BooleanField(default=False)
    can_agitate = models.BooleanField(default=False)
    can_be_applicant = models.BooleanField(default=False)
    can_deliver = models.BooleanField(default=False)
    can_hold = models.BooleanField(default=False)

    @classmethod
    def save_abilities(cls, region_id, agitator, abilities):
        return cls.objects.update_or_create(region_id=region_id,
                                            agitator_id=agitator.id,
                                            defaults=abilities)

    def get_abilities_dict(self):
        return {'have_registration': self.have_registration,
                'can_agitate': self.can_agitate,
                'can_be_applicant': self.can_be_applicant,
                'can_deliver': self.can_deliver,
                'can_hold': self.can_hold}

    @classmethod
    def get(cls, region_id, telegram_id):
        return cls.objects.filter(region_id=region_id, agitator__telegram_id=telegram_id).first()

    class Meta:
        unique_together = ('agitator', 'region')


class AgitationPlaceHierarchy(models.Model):
    base_place = models.ForeignKey('AgitationPlace', related_name='hierarchy_base_place')
    sub_place = models.ForeignKey('AgitationPlace', related_name='hierarchy_sub_place')

    order = models.IntegerField()

    def save(self, *args, **kwargs):
        if self.base_place.region_id != self.sub_place.region_id:
            raise ValueError('base_place.region_id and sub_place.region_id must be equals')
        super().save(*args, **kwargs)

    def __str__(self):
        return '%s -> %s' % (self.base_place, self.sub_place)

    class Meta:
        unique_together = ['base_place', 'sub_place']


class AgitationPlace(models.Model):
    region = models.ForeignKey(Region)

    address = models.CharField(max_length=200, help_text='Например, «Гражданский пр., 74»')
    geo_latitude = models.FloatField(null=True, blank=True)
    geo_longitude = models.FloatField(null=True, blank=True)

    last_update_time = models.DateTimeField(auto_now=True)

    post_apply_text = models.CharField(max_length=1000, null=True, blank=True)
    registrations_chat_id = models.BigIntegerField(null=True, blank=True)

    def get_location(self):
        if self.geo_latitude and self.geo_longitude:
            return {'latitude': self.geo_latitude, 'longitude': self.geo_longitude}
        return None

    @property
    def subplaces(self):
        return list(AgitationPlace.objects.filter(hierarchy_sub_place__base_place_id=self.id)
                    .order_by('hierarchy_sub_place__order').all())

    def show(self, markdown=True):
        if markdown:
            return '*%s*' % utils.escape_markdown(self.address)
        else:
            return self.address

    def __str__(self):
        return '%s %s' % (self.region.name, self.address)


class AgitationEvent(models.Model):
    place = models.ForeignKey(AgitationPlace)
    name = models.CharField(max_length=100, blank=True, null=True)
    start_date = models.DateTimeField(null=False)
    end_date = models.DateTimeField(null=False)

    master = models.ForeignKey(User)

    need_cube = models.BooleanField(null=False, blank=False)

    is_canceled = models.BooleanField(default=False)

    agitators_limit = models.IntegerField(null=True, blank=True)

    @property
    def cube_usage(self):
        return self.cubeusageinevent if hasattr(self, 'cubeusageinevent') else None

    @property
    def region(self):
        return self.place.region

    class Meta:
        ordering = ['start_date', 'place_id']

    def show(self, markdown=True):
        diff = timedelta(seconds=self.region.timezone_delta)
        if markdown:
            return "%s%s-%s, %s" % ("*ОТМЕНЕН* " if self.is_canceled else "",
                                    (self.start_date + diff).strftime("%d.%m %H:%M"),
                                    (self.end_date + diff).strftime("%H:%M"),
                                    utils.escape_markdown(self.name))
        else:
            return "%s%s-%s, %s" % ("ОТМЕНЕН " if self.is_canceled else "",
                                    (self.start_date + diff).strftime("%d.%m %H:%M"),
                                    (self.end_date + diff).strftime("%H:%M"),
                                    self.name)

    def __str__(self):
        return "%s-%s, %s %s" % (self.start_date.strftime("%d.%m %H:%M"),
                                 self.end_date.strftime("%H:%M"),
                                 self.name,
                                 self.place.address)


class ConversationState(models.Model):
    key = models.CharField(max_length=400, blank=True, null=True, unique=True)
    agitator = models.ForeignKey(User, blank=True, null=True)
    state = models.CharField(max_length=400, blank=True, null=True)
    data = models.TextField(max_length=64000, blank=True, null=True)
    last_update_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_update_time']

    def __repr__(self):
        return "key '%s' agitator '%s' state '%s' data '%s' last_update_time '%s'\n" % (
            self.key, self.agitator, self.state, self.data, str(self.last_update_time)
        )

    def __str__(self):
        return "key '%s' state '%s' last_update_time '%s'\n" % (
            self.key, self.state, str(self.last_update_time)
        )


class AgitationEventParticipant(models.Model):
    agitator = models.ForeignKey(User)
    event = models.ForeignKey(AgitationEvent)
    place = models.ForeignKey(AgitationPlace, null=True)

    approved = models.BooleanField(default=False)
    declined = models.BooleanField(default=False)
    canceled = models.BooleanField(default=False)

    def emoji_status(self, with_text=False):
        if self.canceled:
            emoji = EMOJI_NO
            text = 'Заявка отменена'
        elif self.approved:
            emoji = EMOJI_OK
            text = 'Заявка подтверждена'
        elif self.declined:
            emoji = EMOJI_NO
            text = 'Заявка отклонена'
        else:
            emoji = EMOJI_QUESTION
            text = 'Новая заявка'
        if with_text:
            return emoji + ' ' + text
        else:
            return emoji

    def make_approve(self):
        self.approved = True
        self.declined = False
        self.save()

    def make_decline(self):
        self.approved = False
        self.declined = True
        self.save()

    @classmethod
    def create(cls, user, event_id, place_id):
        return cls.objects.update_or_create(agitator=user, event_id=event_id, place_id=place_id)

    @classmethod
    def get(cls, telegram_id, event_id):
        return cls.objects.filter(agitator__telegram_id=telegram_id, event_id=event_id).first()

    @classmethod
    def get_count(cls, event_id, place_id):
        return cls.objects.filter(event_id=event_id, place_id=place_id,
                                  declined=False, canceled=False).count()

    @classmethod
    def approve(cls, id):
        return cls.objects.filter(id=id).update(approved=True, declined=False)

    @classmethod
    def decline(cls, id):
        return cls.objects.filter(id=id).update(approved=False, declined=True)

    @classmethod
    def cancel(cls, id):
        return cls.objects.filter(id=id).update(canceled=True)

    @classmethod
    def restore(cls, id):
        return cls.objects.filter(id=id).update(canceled=False)

    def get_neighbours(self):
        return list(AgitationEventParticipant.objects.filter(event_id=self.event_id, place_id=self.place_id,
                                                             declined=False, canceled=False).all())

    class Meta:
        unique_together = ('agitator', 'event')


class Storage(models.Model):
    region = models.ForeignKey(Region)

    public_name = models.CharField(max_length=1000)
    private_name = models.CharField(max_length=1000)
    holder = models.ForeignKey(User)
    geo_latitude = models.FloatField(null=True, blank=True)
    geo_longitude = models.FloatField(null=True, blank=True)

    def show(self, markdown=True, private=False):
        name = self.private_name if private else self.public_name
        if markdown:
            name = '*%s*' % utils.escape_markdown(name)
        return '%s (контакт: %s)' % (name, self.holder.show(markdown, private))

    def __str__(self):
        return self.show(markdown=False, private=True)


class Cube(models.Model):
    region = models.ForeignKey(Region)
    last_storage = models.ForeignKey(Storage)

    def show(self, markdown=True, private=False):
        return self.last_storage.show(markdown, private)

    def __str__(self):
        return '%d %s' % (self.id, str(self.last_storage))

    def is_available_for(self, event):
        usage = CubeUsageInEvent.objects.filter(cube_id=self.id).filter(
            (Q(event__start_date__lte=event.end_date) & Q(event__end_date__gte=event.start_date))
            | (Q(event__end_date__gte=event.start_date) & Q(event__start_date__lte=event.end_date))
            ## TODO check this formula
        ).first()
        return usage is None


class CubeUsageInEvent(models.Model):
    event = models.OneToOneField(AgitationEvent)
    cube = models.ForeignKey(Cube)
    delivered_from = models.ForeignKey(Storage, null=True, blank=True, related_name='usage_delivered_from')
    delivered_by = models.ForeignKey(User, null=True, blank=True, related_name='usage_delivered_by')
    shipped_to = models.ForeignKey(Storage, null=True, blank=True, related_name='usage_shipped_to')
    shipped_by = models.ForeignKey(User, null=True, blank=True, related_name='usage_shipped_by')
    transferred_to_storage = models.BooleanField(null=False, blank=False, default=False)

    def show(self, markdown=True, private=False):
        return '%s привезет из %s\n%s отвезет в %s' % (
            self.delivered_by.show(markdown, private) if self.delivered_by else '???',
            self.delivered_from.show(markdown, private) if self.delivered_from else '???',
            self.shipped_by.show(markdown, private) if self.shipped_by else '???',
            self.shipped_to.show(markdown, private) if self.shipped_to else '???')


class AgitationEventReport(models.Model):
    start_date = models.DateTimeField(help_text='Фактическое время начала', null=True, blank=True)
    end_date = models.DateTimeField(help_text='Фактическое время окончания', null=True, blank=True)
    comment = models.CharField(max_length=1000, null=True, blank=True)


class AgitationEventReportMaterials(models.Model):
    report = models.ForeignKey(AgitationEventReport)
    name = models.CharField(max_length=100)
    start_count = models.PositiveIntegerField()
    end_count = models.PositiveIntegerField(null=True, blank=True)


class TaskRun(models.Model):
    task_key = models.CharField(max_length=200)
    scheduled_moment = models.DateTimeField()
    run_moment = models.DateTimeField()

    @classmethod
    def get_last_run(cls, key):
        return cls.objects.filter(task_key=key).order_by('-scheduled_moment').first()
