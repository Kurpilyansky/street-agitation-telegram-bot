# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-13 07:52
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0027_auto_20170813_0740'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversationstate',
            name='agitator2',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='street_agitation_bot.User'),
        ),
        migrations.AddField(
            model_name='cubeusageinevent',
            name='delivered_by2',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='usage_delivered_by2', to='street_agitation_bot.User'),
        ),
        migrations.AddField(
            model_name='cubeusageinevent',
            name='shipped_by2',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='usage_shipped_by2', to='street_agitation_bot.User'),
        ),
    ]
