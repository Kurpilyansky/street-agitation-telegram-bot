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


admin.site.register(models.AgitationPlace, AgitationPlaceAdmin)
admin.site.register(models.AgitationEvent, AgitationEventAdmin)
