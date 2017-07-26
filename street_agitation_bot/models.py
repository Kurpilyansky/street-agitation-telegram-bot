# -*- coding: utf-8 -*-

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


class Agitator(models.Model):
    telegram_id = models.IntegerField(primary_key=True)
    telegram = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=200, blank=False, null=False)
    last_name = models.CharField(max_length=200, blank=False, null=False)
    phone = models.CharField(max_length=50, blank=False, null=False)

    registration_date = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self):
        return "%s %s" % (self.last_name, self.first_name)

    @property
    def regions(self):
        return list(Region.objects.filter(agitatorinregion__agitator__telegram_id=self.telegram_id).all())

    @classmethod
    def find_by_id(cls, id):
        return cls.objects.filter(telegram_id=id).first()

    def show_full(self):
        if self.telegram:
            return utils.escape_markdown('%s @%s %s' % (self.full_name, self.telegram, self.phone))
        else:
            return utils.escape_markdown('@%s (%s) %s' % (self.telegram_id, self.full_name, self.phone))

    def __str__(self):
        return '@%s (%s) @%s' % (self.telegram_id, self.full_name, self.telegram)


class AgitatorInRegion(models.Model):
    agitator = models.ForeignKey(Agitator)
    region = models.ForeignKey(Region)

    is_admin = models.BooleanField(default=False)

    have_registration = models.BooleanField(default=False)
    can_agitate = models.BooleanField(default=False)
    can_be_applicant = models.BooleanField(default=False)
    can_deliver = models.BooleanField(default=False)
    can_hold = models.BooleanField(default=False)

    @classmethod
    def save_abilities(cls, region_id, agitator_id, abilities):
        return cls.objects.update_or_create(region_id=region_id,
                                            agitator_id=agitator_id,
                                            defaults=abilities)

    def get_abilities_dict(self):
        return {'have_registration': self.have_registration,
                'can_agitate': self.can_agitate,
                'can_be_applicant': self.can_be_applicant,
                'can_deliver': self.can_deliver,
                'can_hold': self.can_hold}

    @classmethod
    def get(cls, region_id, agitator_id):
        return cls.objects.filter(region_id=region_id, agitator_id=agitator_id).first()

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

    is_canceled = models.BooleanField(default=False)

    agitators_limit = models.IntegerField(null=True, blank=True)

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
    agitator = models.ForeignKey(Agitator, blank=True, null=True)
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
    agitator = models.ForeignKey(Agitator)
    event = models.ForeignKey(AgitationEvent)
    place = models.ForeignKey(AgitationPlace, null=True)

    approved = models.BooleanField(default=False)
    declined = models.BooleanField(default=False)
    canceled = models.BooleanField(default=False)

    @property
    def emoji_status(self):
        if self.canceled:
            return EMOJI_NO
        if self.approved:
            return EMOJI_OK
        if self.declined:
            return EMOJI_NO
        return EMOJI_QUESTION

    @classmethod
    def create(cls, agitator_id, event_id, place_id):
        return cls.objects.update_or_create(agitator_id=agitator_id, event_id=event_id, place_id=place_id)

    @classmethod
    def get(cls, agitator_id, event_id):
        return cls.objects.filter(agitator_id=agitator_id, event_id=event_id).first()

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
