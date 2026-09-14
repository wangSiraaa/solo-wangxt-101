from django.contrib import admin

from .models import (
    BoundVolume,
    BoundVolumeItem,
    Issue,
    Item,
    Location,
    OperationLog,
    Title,
)


class BoundVolumeItemInline(admin.TabularInline):
    model = BoundVolumeItem
    extra = 0


@admin.register(Title)
class TitleAdmin(admin.ModelAdmin):
    list_display = ("name", "issn", "frequency", "status", "ceased_year", "ceased_month", "predecessor")
    list_filter = ("frequency", "status")


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("label", "title", "kind", "pub_year", "pub_month", "volume", "number", "number_end")
    list_filter = ("kind", "title")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("barcode", "issue", "copy_no", "status", "location", "bound_volume")
    list_filter = ("status", "location")


@admin.register(BoundVolume)
class BoundVolumeAdmin(admin.ModelAdmin):
    list_display = ("barcode", "label", "title", "status", "location")
    inlines = [BoundVolumeItemInline]


admin.site.register(Location)
admin.site.register(OperationLog)
