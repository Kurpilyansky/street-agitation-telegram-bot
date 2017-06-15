# -*- coding: utf-8 -*-

from django.db import models


class Agitator(models.Model):
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50)
    telegram = models.CharField(max_length=100)


class AgitationPlace(models.Model):
    address = models.CharField(max_length=200, help_text='Например, «Гражданский пр., 74»')
    geo_latitude = models.FloatField(null=True, blank=True)
    geo_longitude = models.FloatField(null=True, blank=True)

    last_update_time = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.address


class AgitationEvent(models.Model):
    place = models.ForeignKey(AgitationPlace)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()

    class Meta:
        ordering = ['start_date']

    def show(self):
        return "%s-%s, *%s*" % (self.start_date.strftime("%d.%m %H:%M"),
                                self.end_date.strftime("%H:%M"),
                                self.place.address)
