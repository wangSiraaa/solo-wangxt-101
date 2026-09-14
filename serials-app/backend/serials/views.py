"""REST API：刊名 / 期 / 册 / 合订本 / 位置 / 操作日志。"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import rules, services
from .models import (
    BoundVolume,
    Issue,
    Item,
    Location,
    OperationLog,
    Title,
)
from .serializers import (
    BoundVolumeSerializer,
    IssueSerializer,
    ItemSerializer,
    LocationSerializer,
    OperationLogSerializer,
    TitleSerializer,
)


def _domain_error(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class TitleViewSet(viewsets.ModelViewSet):
    queryset = Title.objects.select_related("predecessor").all()
    serializer_class = TitleSerializer

    def perform_create(self, serializer):
        try:
            instance = Title(**serializer.validated_data)
            instance.full_clean()
        except DjangoValidationError as exc:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        serializer.save()

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        """时间轴：应到 slot × 出版登记 × 馆藏实体，逐月可核对。"""
        title = self.get_object()
        analysis = rules.analyze_title(title)
        slots = []
        for row in analysis.rows:
            s = row.slot
            slots.append(
                {
                    "year": s.year,
                    "month": s.month,
                    "volume": s.volume,
                    "number": s.number,
                    "state": row.state,
                    "issue": IssueSerializer(row.issue).data if row.issue else None,
                    "items": ItemSerializer(row.items, many=True).data,
                    "verification": (
                        rules.verification_hint(title, row) if row.state != rules.HELD else None
                    ),
                }
            )
        supplements = IssueSerializer(analysis.supplements, many=True).data
        return Response(
            {
                "title": TitleSerializer(title).data,
                "slots": slots,
                "supplements": supplements,
                "conflicts": analysis.conflicts,
                "stats": analysis.stats,
            }
        )

    @action(detail=True, methods=["get"])
    def gaps(self, request, pk=None):
        """缺藏/缺号清单：逐项可核实（缺号 != 缺藏）。"""
        title = self.get_object()
        analysis = rules.analyze_title(title)
        rows = []
        for row in analysis.rows:
            if row.state == rules.HELD:
                continue
            s = row.slot
            rows.append(
                {
                    "year": s.year,
                    "month": s.month,
                    "volume": s.volume,
                    "number": s.number,
                    "state": row.state,
                    "state_display": "缺藏" if row.state == rules.MISSING else "缺号（未登记出版）",
                    "issue": IssueSerializer(row.issue).data if row.issue else None,
                    "verification": rules.verification_hint(title, row),
                }
            )
        return Response({"title": TitleSerializer(title).data, "gaps": rows})

    @action(detail=True, methods=["get"])
    def lineage(self, request, pk=None):
        """刊名沿革链：前身 -> 本刊 -> 后继。"""
        title = self.get_object()
        chain, seen = [], set()
        node = title
        while node and node.pk not in seen:  # 前身方向
            seen.add(node.pk)
            chain.append(node)
            node = node.predecessor
        chain.reverse()
        successors = list(title.successors.all())
        return Response(
            {
                "ancestors": TitleSerializer(chain[:-1], many=True).data,
                "current": TitleSerializer(title).data,
                "successors": TitleSerializer(successors, many=True).data,
            }
        )


class IssueViewSet(viewsets.ModelViewSet):
    serializer_class = IssueSerializer

    def get_queryset(self):
        qs = Issue.objects.select_related("title").prefetch_related(
            "items__location", "items__bound_volume__location"
        )
        params = self.request.query_params
        if params.get("title"):
            qs = qs.filter(title_id=params["title"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issue = services.register_issue(
            actor=request.data.get("actor", "system"), **serializer.validated_data
        )
        return Response(IssueSerializer(issue).data, status=status.HTTP_201_CREATED)


class ItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemSerializer

    def get_queryset(self):
        qs = Item.objects.select_related(
            "issue__title", "location", "bound_volume__location"
        )
        params = self.request.query_params
        if params.get("issue"):
            qs = qs.filter(issue_id=params["issue"])
        if params.get("barcode"):
            qs = qs.filter(barcode=params["barcode"])
        if params.get("title"):
            qs = qs.filter(issue__title_id=params["title"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    @action(detail=False, methods=["post"])
    def check_in(self, request):
        """入藏一册：{issue_id, barcode, location_id, actor?}"""
        try:
            item = services.check_in(
                issue_id=request.data.get("issue_id"),
                barcode=request.data.get("barcode"),
                location_id=request.data.get("location_id"),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(ItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        """册移库：{location_id, actor?}（已装订册须走合订本移库）"""
        try:
            item = services.move_item(
                item_id=pk,
                to_location_id=request.data.get("location_id"),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(ItemSerializer(item).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        logs = OperationLog.objects.filter(item_id=pk).select_related(
            "from_location", "to_location", "item", "bound_volume", "issue", "title"
        )
        return Response(OperationLogSerializer(logs, many=True).data)


class BoundVolumeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BoundVolumeSerializer

    def get_queryset(self):
        qs = BoundVolume.objects.select_related("title", "location").prefetch_related(
            "bound_items__item__issue", "bound_items__pre_location"
        )
        params = self.request.query_params
        if params.get("title"):
            qs = qs.filter(title_id=params["title"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs

    @action(detail=False, methods=["post"])
    def bind(self, request):
        """合订：{item_ids, barcode, label?, location_id, actor?}"""
        try:
            bv = services.bind_items(
                item_ids=request.data.get("item_ids"),
                barcode=request.data.get("barcode"),
                label=request.data.get("label", ""),
                location_id=request.data.get("location_id"),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(
            BoundVolumeSerializer(bv).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def unbind(self, request, pk=None):
        """拆订：逐册恢复装订前位置与状态"""
        try:
            bv = services.unbind(
                bound_volume_id=pk, actor=request.data.get("actor", "system")
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(BoundVolumeSerializer(bv).data)

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        """合订本移库：{location_id, actor?}"""
        try:
            bv = services.move_bound_volume(
                bound_volume_id=pk,
                to_location_id=request.data.get("location_id"),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(BoundVolumeSerializer(bv).data)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        logs = OperationLog.objects.filter(bound_volume_id=pk).select_related(
            "from_location", "to_location", "item", "bound_volume", "issue", "title"
        )
        return Response(OperationLogSerializer(logs, many=True).data)


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer


class OperationLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OperationLogSerializer

    def get_queryset(self):
        qs = OperationLog.objects.select_related(
            "from_location", "to_location", "item", "bound_volume", "issue", "title"
        )
        params = self.request.query_params
        for key, field in (
            ("type", "type"),
            ("item", "item_id"),
            ("bound_volume", "bound_volume_id"),
            ("title", "title_id"),
            ("issue", "issue_id"),
        ):
            if params.get(key):
                qs = qs.filter(**{field: params[key]})
        return qs
