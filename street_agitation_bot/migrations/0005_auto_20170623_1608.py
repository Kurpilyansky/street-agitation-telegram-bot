# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-06-23 16:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0004_auto_20170620_1436'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agitator',
            name='telegram',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
