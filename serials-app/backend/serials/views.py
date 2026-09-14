"""REST API：刊名 / 出版单元 / 册 / 合订本 / 位置 / 编号检索 / 操作日志。"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import rules, services
from .models import (
    BoundVolume,
    Issue,
    Item,
    Location,
    NumberAssignment,
    OperationLog,
    Title,
)
from .serializers import (
    BoundVolumeSerializer,
    IssueSerializer,
    ItemSerializer,
    LocationSerializer,
    NumberAssignmentSerializer,
    OperationLogSerializer,
    TitleSerializer,
)


def _domain_error(exc):
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _serialize_slot_row(row):
    return {
        "year": row.slot.year,
        "month": row.slot.month,
        "volume": row.slot.volume,
        "number": row.slot.number,
        "state": row.state,
        "redundant": row.redundant,
        "units": IssueSerializer(row.units, many=True).data,
        "issue": IssueSerializer(row.units[0]).data if row.units else None,  # 兼容旧前端
        "items": ItemSerializer(row.items, many=True).data,
        "withdrawn_items": ItemSerializer(row.withdrawn_items, many=True).data,
        "explanation": row.explanation,
    }


class TitleViewSet(viewsets.ModelViewSet):
    queryset = Title.objects.select_related("predecessor").all()
    serializer_class = TitleSerializer

    def perform_create(self, serializer):
        try:
            instance = Title(**serializer.validated_data)
            instance.full_clean()
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        serializer.save()

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        """时间轴：应到 slot × 出版单元 × 实体；内容覆盖与实体数量分列。"""
        title = self.get_object()
        analysis = rules.analyze_title(title)
        slots = []
        for row in analysis.rows:
            data = _serialize_slot_row(row)
            data["verification"] = (
                rules.verification_hint(title, row) if row.state != rules.HELD else None
            )
            slots.append(data)
        return Response(
            {
                "title": TitleSerializer(title).data,
                "slots": slots,
                "supplements": IssueSerializer(analysis.supplements, many=True).data,
                "redundancies": analysis.redundancies,
                "collisions": analysis.collisions,
                "title_notes": analysis.title_notes,
                "stats": analysis.stats,
            }
        )

    @action(detail=True, methods=["get"])
    def gaps(self, request, pk=None):
        """缺藏/缺号清单：逐项解释、可核实（缺号 != 缺藏）。"""
        title = self.get_object()
        analysis = rules.analyze_title(title)
        rows = []
        for row in analysis.rows:
            if row.state == rules.HELD:
                continue
            data = _serialize_slot_row(row)
            data["state_display"] = "缺藏" if row.state == rules.MISSING else "缺号（未登记出版）"
            data["verification"] = rules.verification_hint(title, row)
            rows.append(data)
        return Response(
            {
                "title": TitleSerializer(title).data,
                "title_notes": analysis.title_notes,
                "gaps": rows,
            }
        )

    @action(detail=True, methods=["get"])
    def lineage(self, request, pk=None):
        """刊名沿革链：前身 -> 本刊 -> 后继。"""
        title = self.get_object()
        chain, seen = [], set()
        node = title
        while node and node.pk not in seen:
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

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """停刊更正：实为延迟出版 {note?}"""
        try:
            title = services.resume_title(
                title_id=pk,
                note=request.data.get("note", ""),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(TitleSerializer(title).data)


class IssueViewSet(viewsets.ModelViewSet):
    serializer_class = IssueSerializer

    def get_queryset(self):
        qs = Issue.objects.select_related("title").prefetch_related(
            "numberings", "items__location", "items__bound_volume__location"
        )
        params = self.request.query_params
        if params.get("title"):
            qs = qs.filter(title_id=params["title"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        return qs

    def create(self, request, *args, **kwargs):
        try:
            issue = services.register_issue(
                actor=request.data.get("actor", "system"),
                title_id=request.data.get("title"),
                kind=request.data.get("kind", "REGULAR"),
                pub_year=request.data.get("pub_year"),
                pub_month=request.data.get("pub_month"),
                volume=request.data.get("volume"),
                number=request.data.get("number"),
                number_end=request.data.get("number_end"),
                supplement_no=request.data.get("supplement_no", 0),
                note=request.data.get("note", ""),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        except DjangoValidationError as exc:
            return _domain_error(exc)
        return Response(IssueSerializer(issue).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def renumber(self, request, pk=None):
        """改号 {volume, number, number_end?, reason?}：新增映射版本，实体不变。"""
        try:
            issue, collisions = services.renumber_issue(
                issue_id=pk,
                volume=request.data.get("volume"),
                number=request.data.get("number"),
                number_end=request.data.get("number_end"),
                reason=request.data.get("reason", ""),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        except DjangoValidationError as exc:
            return _domain_error(exc)
        data = IssueSerializer(issue).data
        data["collisions"] = collisions
        if collisions:
            data["warning"] = "改号后与其他单元形成重名，检索时需按单元身份区分"
        return Response(data)

    @action(detail=True, methods=["get"])
    def numberings(self, request, pk=None):
        """该单元的编号映射版本历史。"""
        issue = self.get_object()
        return Response(NumberAssignmentSerializer(issue.numberings.all(), many=True).data)


class NumberingLookupView(APIView):
    """编号检索：按 (卷, 期号[, 时间点]) 查映射版本。

    旧编号仍可检索；重名时返回全部匹配单元，各自指向自己的实体——
    历史目录链接不会指向错误实体。
    """

    def get(self, request):
        title_id = request.query_params.get("title")
        volume = request.query_params.get("volume")
        number = request.query_params.get("number")
        at = request.query_params.get("at")  # ISO 日期时间，可选
        if not (title_id and volume and number):
            return Response(
                {"detail": "需要 title、volume、number 参数"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        qs = (
            NumberAssignment.objects.filter(issue__title_id=title_id, volume=volume)
            .select_related("issue__title")
            .prefetch_related("issue__items__location", "issue__numberings")
            .order_by("valid_from", "id")
        )
        matches = []
        for assignment in qs:
            if not (assignment.number <= int(number) <= (assignment.number_end or assignment.number)):
                continue
            if at:
                from django.utils.dateparse import parse_datetime

                moment = parse_datetime(at)
                if moment is None:
                    return Response({"detail": "at 参数格式不正确"}, status=status.HTTP_400_BAD_REQUEST)
                if not (assignment.valid_from <= moment and (assignment.valid_to is None or assignment.valid_to > moment)):
                    continue
            issue = assignment.issue
            matches.append(
                {
                    "assignment": NumberAssignmentSerializer(assignment).data,
                    "issue": IssueSerializer(issue).data,
                    "items": ItemSerializer(issue.items.all(), many=True).data,
                }
            )
        return Response({"query": {"title": int(title_id), "volume": int(volume),
                                   "number": int(number), "at": at},
                         "matches": matches})


class ItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ItemSerializer

    def get_queryset(self):
        qs = Item.objects.select_related(
            "issue__title", "location", "bound_volume__location"
        ).prefetch_related("issue__numberings")
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

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        """注销一册：{reason?, actor?}（馆员决定，不自动执行）"""
        try:
            item = services.withdraw_item(
                item_id=pk,
                reason=request.data.get("reason", ""),
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
            "bound_items__item__issue__numberings",
            "bound_items__item__issue__title",
            "bound_items__pre_location",
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
    def split(self, request, pk=None):
        """合订册拆分：{item_ids, new_barcode, new_label?, location_id?}"""
        try:
            bv = services.split_bound_volume(
                bound_volume_id=pk,
                item_ids=request.data.get("item_ids"),
                new_barcode=request.data.get("new_barcode"),
                new_label=request.data.get("new_label", ""),
                location_id=request.data.get("location_id"),
                actor=request.data.get("actor", "system"),
            )
        except services.DomainError as exc:
            return _domain_error(exc)
        return Response(BoundVolumeSerializer(bv).data, status=status.HTTP_201_CREATED)

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
