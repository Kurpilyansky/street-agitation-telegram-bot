from django.contrib import admin

from reversion.admin import VersionAdmin

from door_to_door_bot import models


class RegionAdmin(VersionAdmin):
    list_display = (
        'id',
        'name',
    )

    list_filter = (
    )

    search_fields = (
        '=id',
        'name',
    )


class RegionSettingsAdmin(VersionAdmin):
    list_display = (
        'region',
        'is_public',
    )

    list_filter = (
        'is_public',
    )

    search_fields = (
        '=region__id',
        'region__name',
    )


class UserAdmin(VersionAdmin):
    list_display = (
        'id',
        'telegram_id',
        'telegram',
        'last_name',
        'first_name',
        'phone',
    )

    list_filter = (
    )

    search_fields = (
        '=id',
        '=telegram_id',
        'telegram',
        'last_name',
        'first_name',
    )


class AdminRightsAdmin(VersionAdmin):
    list_display = (
        'region',
        'user',
        'level'
    )

    list_filter = (
        'region',
    )

    search_fields = (
        '=id',
        '=user__telegram_id',
        'user__last_name',
        'user__first_name',
        'user__telegram',
    )


class AgitatorInRegionAdmin(VersionAdmin):
    list_display = (
        'region',
        'agitator',
    )

    list_filter = (
        'region',
    )

    search_fields = (
        '=id',
        '=agitator__telegram_id',
        'agitator__last_name',
        'agitator__first_name',
        'agitator__telegram',
    )


class ConversationStateAdmin(VersionAdmin):
    list_display = (
        'key',
        'agitator',
        'state',
    )
    list_filter = (
        'state',
    )
    search_fields = (
        '=key',
        '=agitator__telegram_id',
        'state',
        'agitator__telegram',
        'agitator__last_name',
        'agitator__first_name',
    )


class AgitationTeamAdmin(VersionAdmin):
    list_display = (
        'id',
        'region',
        'start_time',
        'place',
        'chat_id',
    )
    list_filter = (
        'region',
    )
    search_fields = (
        'place',
    )


class StreetAdmin(VersionAdmin):
    list_display = (
        'id',
        'region',
        'name',
    )
    list_filter = (
        'region',
    )
    search_fields = (
        'name',
    )


class HouseAdmin(VersionAdmin):
    list_display = (
        'id',
        'street',
        'number',
    )
    list_filter = (
        'street__region',
    )
    search_fields = (
        'street__name',
        'number',
    )


class HouseBlockAdmin(VersionAdmin):
    list_display = (
        'id',
        'house',
        'number',
    )
    list_filter = (
        'house__street__region',
    )
    search_fields = (
        'house__street__name',
        'house__number',
        'number',
    )


class FlatAdmin(VersionAdmin):
    list_display = (
        'id',
        'house_block',
        'number',
    )
    list_filter = (
        'house_block__house__street__region',
    )
    search_fields = (
        'house_block__house__street__name',
        'house_block__house__number',
        'house_block__number',
        'number',
    )


class FlatContactAdmin(VersionAdmin):
    list_display = (
        'flat',
        'team',
        'status',
        'start_time',
        'end_time',
    )
    list_filter = (
        'team__region',
        'status',
    )
    search_fields = (
        '=flat_id',
        '=team_id',
    )


admin.site.register(models.Region, RegionAdmin)
admin.site.register(models.RegionSettings, RegionSettingsAdmin)
admin.site.register(models.User, UserAdmin)
admin.site.register(models.AdminRights, AdminRightsAdmin)
admin.site.register(models.AgitatorInRegion, AgitatorInRegionAdmin)
admin.site.register(models.ConversationState, ConversationStateAdmin)
admin.site.register(models.AgitationTeam, AgitationTeamAdmin)
admin.site.register(models.Street, StreetAdmin)
admin.site.register(models.House, HouseAdmin)
admin.site.register(models.HouseBlock, HouseBlockAdmin)
admin.site.register(models.Flat, FlatAdmin)
admin.site.register(models.FlatContact, FlatContactAdmin)
