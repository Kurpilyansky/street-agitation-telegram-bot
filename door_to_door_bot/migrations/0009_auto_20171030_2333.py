# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-10-30 23:33
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('door_to_door_bot', '0008_auto_20171030_2259'),
    ]

    operations = [
        migrations.AddField(
            model_name='flatcontact',
            name='comment',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name='flatcontact',
            name='flyers_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='flatcontact',
            name='newspapers_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='flatcontact',
            name='phone',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='flatcontact',
            name='registrations_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
