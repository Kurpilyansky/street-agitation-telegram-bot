# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-13 07:59
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0032_auto_20170813_0757'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Agitator',
        ),
    ]