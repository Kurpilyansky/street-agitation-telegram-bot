# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-07-02 16:39
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0010_auto_20170702_1632'),
    ]

    operations = [
        migrations.AddField(
            model_name='agitationevent',
            name='agitators_limit',
            field=models.IntegerField(null=True),
        ),
    ]
