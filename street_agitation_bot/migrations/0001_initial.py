# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-06-17 19:00
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AgitationEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateTimeField()),
                ('end_date', models.DateTimeField()),
            ],
            options={
                'ordering': ['start_date'],
            },
        ),
        migrations.CreateModel(
            name='AgitationPlace',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.CharField(help_text='Например, «Гражданский пр., 74»', max_length=200)),
                ('geo_latitude', models.FloatField(blank=True, null=True)),
                ('geo_longitude', models.FloatField(blank=True, null=True)),
                ('last_update_time', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='Agitator',
            fields=[
                ('telegram_id', models.IntegerField(primary_key=True, serialize=False)),
                ('telegram', models.CharField(max_length=100)),
                ('full_name', models.CharField(max_length=200)),
                ('phone', models.CharField(max_length=50)),
                ('registration_date', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='ConversationState',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(blank=True, max_length=400, null=True, unique=True)),
                ('state', models.CharField(blank=True, max_length=400, null=True)),
                ('data', models.TextField(blank=True, max_length=64000, null=True)),
                ('last_update_time', models.DateTimeField(auto_now=True)),
                ('agitator', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='street_agitation_bot.Agitator')),
            ],
            options={
                'ordering': ['-last_update_time'],
            },
        ),
        migrations.AddField(
            model_name='agitationevent',
            name='place',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='street_agitation_bot.AgitationPlace'),
        ),
    ]
