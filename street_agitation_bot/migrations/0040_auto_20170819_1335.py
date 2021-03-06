# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-08-19 13:35
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


def generate_region_settings(apps, schema_editor):
    Region = apps.get_model('street_agitation_bot', 'Region')
    RegionSettings = apps.get_model('street_agitation_bot', 'RegionSettings')
    for region in Region.objects.all():
        RegionSettings.objects.create(region=region,
                                      is_public=region.is_public,
                                      enabled_cube_logistics=False)


class Migration(migrations.Migration):

    dependencies = [
        ('street_agitation_bot', '0039_auto_20170816_2115'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegionSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_public', models.BooleanField(default=False)),
                ('enabled_cube_logistics', models.BooleanField(default=False)),
            ],
        ),
        migrations.AddField(
            model_name='regionsettings',
            name='region',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='settings', to='street_agitation_bot.Region'),
        ),
        migrations.RunPython(generate_region_settings, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='region',
            name='is_public',
        ),
    ]
