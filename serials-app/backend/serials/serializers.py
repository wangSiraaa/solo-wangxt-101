from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

from .models import (
    BoundVolume,
    BoundVolumeItem,
    Issue,
    IssueKind,
    Item,
    Location,
    OperationLog,
    Title,
)
from .rules import issue_covers


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name"]


class TitleSerializer(serializers.ModelSerializer):
    frequency_display = serializers.CharField(source="get_frequency_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    predecessor_name = serializers.CharField(
        source="predecessor.name", read_only=True, default=None
    )

    class Meta:
        model = Title
        fields = [
            "id", "name", "issn", "frequency", "frequency_display",
            "start_year", "start_month",
            "volume_start_number", "volume_start_year", "volume_start_month",
            "months_per_volume",
            "status", "status_display", "ceased_year", "ceased_month",
            "predecessor", "predecessor_name", "note",
        ]


class BoundVolumeBriefSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = BoundVolume
        fields = ["id", "barcode", "label", "status", "status_display", "location"]


class ItemSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=Location.objects.all(), source="location", write_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    effective_location = serializers.SerializerMethodField()
    bound_volume = BoundVolumeBriefSerializer(read_only=True)
    issue_label = serializers.CharField(source="issue.label", read_only=True)

    class Meta:
        model = Item
        fields = [
            "id", "barcode", "copy_no", "status", "status_display",
            "location", "location_id", "effective_location",
            "bound_volume", "issue", "issue_label", "checked_in_at",
        ]

    def get_effective_location(self, obj):
        loc = obj.effective_location
        return LocationSerializer(loc).data if loc else None


class IssueSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    covers = serializers.SerializerMethodField()
    items = ItemSerializer(many=True, read_only=True)
    title_name = serializers.CharField(source="title.name", read_only=True)

    class Meta:
        model = Issue
        fields = [
            "id", "title", "title_name", "kind", "kind_display", "label",
            "pub_year", "pub_month", "volume", "number", "number_end",
            "supplement_no", "covers", "note", "items", "registered_at",
        ]

    def get_covers(self, obj):
        return [{"volume": v, "number": n} for v, n in issue_covers(obj)]

    def validate(self, attrs):
        data = dict(attrs)
        if self.instance:
            for f in ("title", "kind", "pub_year", "pub_month", "volume",
                      "number", "number_end", "supplement_no", "note"):
                data.setdefault(f, getattr(self.instance, f))
        instance = Issue(**data)
        if self.instance:
            instance.pk = self.instance.pk
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            raise DRFValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            )
        return attrs


class BoundVolumeItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)
    pre_location = LocationSerializer(read_only=True)

    class Meta:
        model = BoundVolumeItem
        fields = ["id", "item", "position", "pre_location", "pre_status", "bound_at", "unbound_at"]


class BoundVolumeSerializer(serializers.ModelSerializer):
    location = LocationSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    bound_items = BoundVolumeItemSerializer(many=True, read_only=True)
    title_name = serializers.CharField(source="title.name", read_only=True)

    class Meta:
        model = BoundVolume
        fields = [
            "id", "title", "title_name", "barcode", "label",
            "location", "status", "status_display",
            "bound_items", "created_at", "unbound_at",
        ]


class OperationLogSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    item_barcode = serializers.CharField(source="item.barcode", read_only=True, default=None)
    bound_volume_barcode = serializers.CharField(
        source="bound_volume.barcode", read_only=True, default=None
    )
    issue_label = serializers.CharField(source="issue.label", read_only=True, default=None)
    title_name = serializers.CharField(source="title.name", read_only=True, default=None)
    from_location_name = serializers.SerializerMethodField()
    to_location_name = serializers.SerializerMethodField()

    class Meta:
        model = OperationLog
        fields = [
            "id", "type", "type_display", "actor",
            "title", "title_name", "issue", "issue_label",
            "item", "item_barcode", "bound_volume", "bound_volume_barcode",
            "from_location", "from_location_name",
            "to_location", "to_location_name",
            "payload", "created_at",
        ]

    def _loc(self, loc):
        return f"{loc.code} {loc.name}" if loc else None

    def get_from_location_name(self, obj):
        return self._loc(obj.from_location)

    def get_to_location_name(self, obj):
        return self._loc(obj.to_location)
