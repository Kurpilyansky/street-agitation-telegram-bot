# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-13 10:52
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0037_auto_20170813_1042'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agitatorinregion',
            name='is_admin',
        ),
    ]