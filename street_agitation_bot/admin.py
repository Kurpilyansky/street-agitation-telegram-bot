from django.contrib import admin

from reversion.admin import VersionAdmin

from . import models


class RegionAdmin(VersionAdmin):
    list_display = (
        'id',
        'is_public',
        'name',
    )

    list_filter = (
        'is_public',
    )

    search_fields = (
        '=id',
        'name',
    )


class AgitatorAdmin(VersionAdmin):
    list_display = (
        'telegram_id',
        'telegram',
        'full_name',
        'phone',
    )

    list_filter = (
    )

    search_fields = (
        '=id',
        'telegram',
        'full_name',
    )


class AgitatorInRegionAdmin(VersionAdmin):
    list_display = (
        'region',
        'agitator',
        'have_registration',
        'can_be_applicant',
        'can_deliver',
        'can_hold',
        'is_admin',
    )

    list_filter = (
        'region',
        'have_registration',
        'can_be_applicant',
        'can_deliver',
        'can_hold',
        'is_admin',
    )

    search_fields = (
        '=id',
        'agitator__name',
        'agitator__telegram',
        'agitator__telegram_id',
    )


class AgitationPlaceAdmin(VersionAdmin):
    list_display = (
        'id',
        'region',
        'address',
    )

    list_filter = (
        'region',
    )

    search_fields = (
        '=id',
        'address',
    )


class AgitationEventAdmin(VersionAdmin):
    list_display = (
        'id',
        'region',
        'place',
        'start_date',
        'end_date',
    )
    list_filter = (
    )

    search_fields = (
        'place__address',
        'place__region__name',
    )


class AgitationEventParticipantAdmin(VersionAdmin):
    list_display = (
        'id',
        'agitator',
        'event',
        'approved',
        'declined',
        'canceled',
    )
    list_filter = (
        'approved',
        'declined',
        'canceled',
    )

    search_fields = (
        '=id',
        'agitator__full_name',
    )


class ConversationStateAdmin(VersionAdmin):
    list_display = (
        'key',
        'state',
    )
    list_filter = (
        'state',
    )


admin.site.register(models.Region, RegionAdmin)
admin.site.register(models.Agitator, AgitatorAdmin)
admin.site.register(models.AgitatorInRegion, AgitatorInRegionAdmin)
admin.site.register(models.AgitationPlace, AgitationPlaceAdmin)
admin.site.register(models.AgitationEvent, AgitationEventAdmin)
admin.site.register(models.AgitationEventParticipant, AgitationEventParticipantAdmin)
admin.site.register(models.ConversationState, ConversationStateAdmin)
