# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-12 22:39
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0019_taskrun'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cubeusageinevent',
            name='event',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='street_agitation_bot.AgitationEvent'),
        ),
    ]
