# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-13 07:56
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0029_auto_20170813_0752'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='conversationstate',
            name='agitator',
        ),
        migrations.RemoveField(
            model_name='cubeusageinevent',
            name='delivered_by',
        ),
        migrations.RemoveField(
            model_name='cubeusageinevent',
            name='shipped_by',
        ),
    ]