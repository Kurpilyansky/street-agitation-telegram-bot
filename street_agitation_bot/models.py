# -*- coding: utf-8 -*-

from django.db import models

from street_agitation_bot import bot_settings, utils


class Region(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True, unique=True)
    registrations_chat_it = models.BigIntegerField()

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

    def show(self):
        return utils.escape_markdown(self.name)

    def __str__(self):
        return self.name


class Agitator(models.Model):
    telegram_id = models.IntegerField(primary_key=True)
    telegram = models.CharField(max_length=100, blank=False, null=False)
    full_name = models.CharField(max_length=200, blank=False, null=False)
    phone = models.CharField(max_length=50, blank=False, null=False)

    registration_date = models.DateTimeField(auto_now_add=True)

    @property
    def regions(self):
        return list(Region.objects.filter(agitatorinregion__agitator__telegram_id=self.telegram_id).all())

    @classmethod
    def find_by_id(cls, id):
        return cls.objects.filter(telegram_id=id).first()

    def show_full(self):
        return utils.escape_markdown('%s @%s %s' % (self.full_name, self.telegram, self.phone))

    def __str__(self):
        return '%s @%s' % (self.full_name, self.telegram)


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

    @classmethod
    def get(cls, region_id, agitator_id):
        return cls.objects.filter(region_id=region_id, agitator_id=agitator_id).first()

    class Meta:
        unique_together = ('agitator', 'region')


class AgitationPlace(models.Model):
    region = models.ForeignKey(Region)

    address = models.CharField(max_length=200, help_text='Например, «Гражданский пр., 74»')
    geo_latitude = models.FloatField(null=True, blank=True)
    geo_longitude = models.FloatField(null=True, blank=True)

    last_update_time = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.address


class AgitationEvent(models.Model):
    place = models.ForeignKey(AgitationPlace)
    start_date = models.DateTimeField(null=False)
    end_date = models.DateTimeField(null=False)

    @property
    def region(self):
        return self.place.region

    class Meta:
        ordering = ['start_date', 'place_id']

    def show(self):
        return "%s-%s, *%s*" % (self.start_date.strftime("%d.%m %H:%M"),
                                self.end_date.strftime("%H:%M"),
                                utils.escape_markdown(self.place.address))

    def __str__(self):
        return "%s-%s, %s" % (self.start_date.strftime("%d.%m %H:%M"),
                              self.end_date.strftime("%H:%M"),
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

    approved = models.BooleanField(default=False)
    declined = models.BooleanField(default=False)
    canceled = models.BooleanField(default=False)

    @classmethod
    def create(cls, agitator_id, event_id):
        obj, created = cls.objects.update_or_create(agitator_id=agitator_id, event_id=event_id)
        return created

    @classmethod
    def get(cls, agitator_id, event_id):
        return cls.objects.filter(agitator_id=agitator_id, event_id=event_id).first()

    @classmethod
    def approve(cls, id):
        return cls.objects.filter(id=id).update(approved=True, declined=False)

    @classmethod
    def decline(cls, id):
        return cls.objects.filter(id=id).update(approved=False, declined=True)

    class Meta:
        unique_together = ('agitator', 'event')
