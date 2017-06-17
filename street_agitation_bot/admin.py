from django.contrib import admin

from reversion.admin import VersionAdmin

from . import models


class AgitationPlaceAdmin(VersionAdmin):
    list_display = (
        'id',
        'address',
    )

    list_filter = (
    )

    search_fields = (
        '=id',
        'address',
    )


class AgitationEventAdmin(VersionAdmin):
    list_display = (
        'id',
        'place',
        'start_date',
        'end_date',
    )

    search_fields = (
        'place__address',
    )


class ConversationStateAdmin(VersionAdmin):
    list_display = (
        'key',
        'state',
    )
    list_filter = (
        'state',
    )


admin.site.register(models.AgitationPlace, AgitationPlaceAdmin)
admin.site.register(models.AgitationEvent, AgitationEventAdmin)
admin.site.register(models.ConversationState, ConversationStateAdmin)
