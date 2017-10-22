# -*- coding: utf-8 -*-

from django.db.models import Q
from django.db import transaction

from django.db import models

from street_agitation_bot import utils
from street_agitation_bot.emoji import *

from datetime import timedelta


class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)
    registrations_chat_id = models.BigIntegerField(null=True, blank=True)

    timezone_delta = models.IntegerField(help_text='Разница с UTC в секундах, например, для UTC+3 указано +10800')

    @classmethod
    def find_by_name(cls, name):
        return cls.objects.filter(name=name).first()

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


class RegionSettings(models.Model):
    region = models.OneToOneField(Region, related_name='settings')

    is_public = models.BooleanField(default=False)


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
        params['phone'] = utils.clean_phone_number(params['phone']) if 'phone' in params else ''
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
                return cls.objects.create(**params), True

    def show(self, markdown=True, private=True):
        if not markdown:
            return self.full_name
        escaped_full_name = utils.escape_markdown(self.full_name)
        if not self.telegram_id:
            if private:
                return utils.escape_markdown('%s %s' % (escaped_full_name, self.phone))
            else:
                return escaped_full_name
        # elif self.telegram:
        #     return '%s @%s' % (escaped_full_name, utils.escape_markdown(self.telegram))
        else:
            return '[%s](tg://user?id=%s)' % (escaped_full_name, self.telegram_id)

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
    SUPER_ADMIN_LEVEL = 2

    user = models.ForeignKey(User)
    region = models.ForeignKey(Region, null=True, blank=True)
    level = models.IntegerField(default=1)

    @classmethod
    def get_region_admins(cls, region_id):
        users = dict()
        admin_rights = cls.objects.select_related('user').filter(Q(region=None) | Q(region_id=region_id)).all()
        for ar in admin_rights:
            if ar.user in users:
                users[ar.user] = max(ar.level, users[ar.user])
            else:
                users[ar.user] = ar.level
        return users

    @classmethod
    def get_admin_rights_level(cls, user_telegram_id, region_id):
        return (cls.objects.filter(user__telegram_id=user_telegram_id)
                           .filter(Q(region=None) | Q(region_id=region_id))
                           .aggregate(models.Max('level'))['level__max'])

    @classmethod
    def can_disrank(cls, region_id, level):
        return list(set(map(lambda x: x.user,
                            cls.objects.select_related('user')
                               .filter(region_id=region_id, level__lt=level)
                               .all())))

    @classmethod
    def disrank(cls, user_id, region_id, level):
        cls.objects.filter(user_id=user_id, region_id=region_id, level__lt=level).delete()

    @classmethod
    def has_admin_rights(cls, user_telegram_id, region_id, level=1):
        return bool(cls.objects.filter(user__telegram_id=user_telegram_id, level__gte=level)
                               .filter(Q(region=None) | Q(region_id=region_id))
                               .first())

    @classmethod
    def has_admin_rights_for_event(cls, user_telegram_id, event):
        return event.master.telegram_id == user_telegram_id \
               or cls.has_admin_rights(user_telegram_id, event.place.region_id)

    class Meta:
        unique_together = ('user', 'region')


class AgitatorInRegion(models.Model):
    agitator = models.ForeignKey(User)
    region = models.ForeignKey(Region)

    @classmethod
    def save_abilities(cls, region_id, agitator, abilities):
        return cls.objects.update_or_create(region_id=region_id,
                                            agitator_id=agitator.id,
                                            defaults=abilities)

    def get_abilities_dict(self):
        return {}

    @classmethod
    def get(cls, region_id, telegram_id):
        return cls.objects.filter(region_id=region_id, agitator__telegram_id=telegram_id).first()

    class Meta:
        unique_together = ('agitator', 'region')


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


class Street(models.Model):
    region = models.ForeignKey(Region)
    name = models.CharField(max_length=500)

    def show(self, markdown=True, full=True):
        if markdown:
            return utils.escape_markdown(self.name)
        else:
            return self.name

    def __str__(self):
        return '%s %s' % (self.region, self.name)


class House(models.Model):
    street = models.ForeignKey(Street)
    number = models.CharField(max_length=100)

    def show(self, markdown=True, full=True):
        text = utils.escape_markdown(self.number) if markdown else self.number
        if full:
            text = '%s д.%s' % (self.street.show(markdown, full), text)
        return text

    def __str__(self):
        return '%s %s' % (self.street, self.number)


class HouseBlock(models.Model):
    house = models.ForeignKey(House)
    number = models.CharField(max_length=10)
    min_flat_number = models.IntegerField(null=True, blank=True)
    max_flat_number = models.IntegerField(null=True, blank=True)

    def show(self, markdown=True, full=True):
        text = utils.escape_markdown(self.number) if markdown else self.number
        if full:
            text = '%s подъезд №%s' % (self.house.show(markdown, full), text)
        return text

    def __str__(self):
        return '%s подъезд №%s' % (self.house, self.number)


class Flat(models.Model):
    house_block = models.ForeignKey(HouseBlock)
    number = models.CharField(max_length=10)

    def show(self, markdown=True, full=True):
        text = utils.escape_markdown(self.number) if markdown else self.number
        if full:
            text = '%s кв.%s' % (self.house_block.show(markdown, full), text)
        return text

    def __str__(self):
        return '%s кв.%s' % (self.house_block, self.number)


class AgitationTeam(models.Model):
    region = models.ForeignKey(Region)

    start_time = models.DateTimeField()
    place = models.CharField(max_length=500)
    agitators = models.ManyToManyField(User)
    chat_id = models.IntegerField(null=True, blank=True, unique=True)

    def is_full(self):
        return self.agitators.count() > 1

    def show(self, markdown=True):
        diff = timedelta(seconds=self.region.timezone_delta)
        datetime_str = (self.start_time + diff).strftime("%d.%m %H:%M")
        place = utils.escape_markdown(self.place) if markdown else self.place
        agitators_str = ' '.join(map(lambda a: a.show(markdown), self.agitators.all()))
        return '%s %s %s' % (datetime_str, place, agitators_str)


class FlatContact(models.Model):
    flat = models.ForeignKey(Flat)
    team = models.ForeignKey(AgitationTeam)
    date = models.DateTimeField()
