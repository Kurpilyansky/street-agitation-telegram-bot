# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-06-18 21:30
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0002_auto_20170618_2113'),
    ]

    operations = [
        migrations.AddField(
            model_name='agitatorinregion',
            name='is_admin',
            field=models.BooleanField(default=False),
        ),
    ]