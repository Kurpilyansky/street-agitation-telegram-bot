# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-07-01 19:40
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0006_auto_20170623_1714'),
    ]

    operations = [
        migrations.AddField(
            model_name='agitationeventparticipant',
            name='place',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='street_agitation_bot.AgitationPlace'),
        ),
    ]
