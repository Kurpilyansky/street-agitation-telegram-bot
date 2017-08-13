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
        'have_registration',
        'can_be_applicant',
        'can_deliver',
        'can_hold',
    )

    list_filter = (
        'region',
        'have_registration',
        'can_be_applicant',
        'can_deliver',
        'can_hold',
    )

    search_fields = (
        '=id',
        '=agitator__telegram_id',
        'agitator__last_name',
        'agitator__first_name',
        'agitator__telegram',
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


class AgitationPlaceHierarchyAdmin(VersionAdmin):
    list_display = (
        'id',
        'base_place',
        'sub_place',
    )

    list_filter = (
        'base_place',
    )

    search_fields = (
        '=id',
        'sub_place__address',
    )


class AgitationEventAdmin(VersionAdmin):
    list_display = (
        'id',
        'name',
        'place',
        'master',
        'start_date',
        'end_date',
    )
    list_filter = (
        'place__region',
    )

    search_fields = (
        'master__telegram',
        'master__first_name',
        'master__last_name',
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
        'agitator__last_name',
        'agitator__first_name',
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


class TaskRunAdmin(VersionAdmin):
    list_display = (
        'task_key',
        'scheduled_moment',
        'run_moment',
    )
    list_filter = (
    )
    search_fields = (
        'task_key',
    )


class StorageAdmin(VersionAdmin):
    list_display = (
        'region',
        'public_name',
        'private_name',
        'holder',
    )
    list_filter = (
        'region',
    )
    search_fields = (
        'public_name',
        'private_name',
        'holder__first_name',
        'holder__last_name',
        'holder__telegram',
        '=holder__telegram_id',
    )


class CubeAdmin(VersionAdmin):
    list_display = (
        'region',
        'last_storage',
    )
    list_filter = (
        'region',
        'last_storage',
    )
    search_fields = (
    )


class CubeUsageInEventAdmin(VersionAdmin):
    list_display = (
        # 'cube__region__name',
        'cube',
        'event',
    )
    list_filter = (
        'cube__region',
    )
    search_fields = (
    )


admin.site.register(models.Region, RegionAdmin)
admin.site.register(models.User, UserAdmin)
admin.site.register(models.AdminRights, AdminRightsAdmin)
admin.site.register(models.AgitatorInRegion, AgitatorInRegionAdmin)
admin.site.register(models.AgitationPlace, AgitationPlaceAdmin)
admin.site.register(models.AgitationPlaceHierarchy, AgitationPlaceHierarchyAdmin)
admin.site.register(models.AgitationEvent, AgitationEventAdmin)
admin.site.register(models.AgitationEventParticipant, AgitationEventParticipantAdmin)
admin.site.register(models.ConversationState, ConversationStateAdmin)
admin.site.register(models.TaskRun, TaskRunAdmin)
admin.site.register(models.Storage, StorageAdmin)
admin.site.register(models.Cube, CubeAdmin)
admin.site.register(models.CubeUsageInEvent, CubeUsageInEventAdmin)
