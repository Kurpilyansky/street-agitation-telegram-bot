# -*- coding: utf-8 -*-

from django.db import models


class Agitator(models.Model):
    full_name = models.CharField(max_length=200, blank=False, null=False)
    phone = models.CharField(max_length=50, blank=False, null=False)
    telegram = models.CharField(max_length=100, blank=False, null=False)


class AgitationPlace(models.Model):
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

    class Meta:
        ordering = ['start_date']

    def show(self):
        return "%s-%s, *%s*" % (self.start_date.strftime("%d.%m %H:%M"),
                                self.end_date.strftime("%H:%M"),
                                self.place.address)


class ConversationState(models.Model):
    key = models.CharField(max_length=400, blank=True, null=True, unique=True)
    state = models.CharField(max_length=400, blank=True, null=True)
    data = models.TextField(max_length=64000, blank=True, null=True)
    last_update_time = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_update_time']

    def __str__(self):
        return "key '%s' state '%s' data '%s' last_update_time '%s'\n" % (
            self.key, self.state, self.data, str(self.last_update_time)
        )
