"""馆藏操作服务层：入藏 / 合订 / 拆订 / 移库，全部落操作日志。

并发约定：
  * check_in 对 Issue 行加 SELECT ... FOR UPDATE，再以 (issue, copy_no)
    唯一约束兜底；并发入藏同一期只会产生不同复本号的多条实体，绝不合并。
  * 条码全局唯一，重复条码直接拒绝。
"""
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    BoundVolume,
    BoundVolumeItem,
    BoundVolumeStatus,
    Issue,
    Item,
    ItemStatus,
    Location,
    OperationLog,
    OperationType,
)

MAX_RETRIES = 5


class DomainError(Exception):
    """业务规则错误，视图层转换为 400。"""


class DuplicateBarcode(DomainError):
    pass


class InvalidState(DomainError):
    pass


def _log(type_, *, actor="system", title=None, issue=None, item=None,
         bound_volume=None, from_location=None, to_location=None, payload=None):
    return OperationLog.objects.create(
        type=type_,
        actor=actor or "system",
        title=title,
        issue=issue,
        item=item,
        bound_volume=bound_volume,
        from_location=from_location,
        to_location=to_location,
        payload=payload or {},
    )


# ---------------------------------------------------------------- 入藏

def check_in(*, issue_id, barcode, location_id, actor="system") -> Item:
    """入藏一册。同编号（同期）实体各自成行，并发安全。"""
    barcode = (barcode or "").strip()
    if not barcode:
        raise DomainError("条码不能为空")
    if Item.objects.filter(barcode=barcode).exists():
        raise DuplicateBarcode(f"条码 {barcode} 已存在：同编号实体须使用各自条码，禁止合并")
    last_exc = None
    for _ in range(MAX_RETRIES):
        try:
            with transaction.atomic():
                # 首语句即 UPDATE：PostgreSQL 取行锁、SQLite 立即取写锁，
                # 并发入藏同一期在此串行化，各自拿到不同复本号，绝不合并。
                Issue.objects.filter(pk=issue_id).update(
                    copies_checked_in=F("copies_checked_in") + 1
                )
                issue = Issue.objects.get(pk=issue_id)
                copy_no = issue.copies_checked_in
                location = Location.objects.get(pk=location_id)
                item = Item.objects.create(
                    issue=issue, copy_no=copy_no, barcode=barcode, location=location
                )
                _log(
                    OperationType.CHECK_IN,
                    actor=actor,
                    title=issue.title,
                    issue=issue,
                    item=item,
                    to_location=location,
                    payload={"barcode": barcode, "copy_no": copy_no},
                )
                return item
        except IntegrityError as exc:
            last_exc = exc
            if Item.objects.filter(barcode=barcode).exists():
                raise DuplicateBarcode(f"条码 {barcode} 已存在：同编号实体须使用各自条码，禁止合并")
            continue  # (issue, copy_no) 并发冲突，重试取下一个复本号
        except OperationalError as exc:
            # SQLite 快照升级冲突（PostgreSQL 由行锁保证，不会走到这里）
            last_exc = exc
            if "locked" not in str(exc).lower():
                raise
            continue
    raise DomainError("入藏失败：并发冲突过多，请重试") from last_exc


# ---------------------------------------------------------------- 合订 / 拆订

def bind_items(*, item_ids, barcode, label, location_id, actor="system") -> BoundVolume:
    """把若干在架册合订为一册合订本。子期与册保留，可检索到所在合订本。"""
    barcode = (barcode or "").strip()
    if not barcode:
        raise DomainError("合订本条码不能为空")
    if BoundVolume.objects.filter(barcode=barcode).exists():
        raise DuplicateBarcode(f"合订本条码 {barcode} 已存在")
    item_ids = list(dict.fromkeys(item_ids or []))
    if not item_ids:
        raise DomainError("至少选择一册进行合订")
    with transaction.atomic():
        items = list(
            Item.objects.select_for_update()
            .select_related("issue__title", "location")
            .filter(pk__in=item_ids)
            .order_by("issue__pub_year", "issue__pub_month", "issue_id", "copy_no")
        )
        if len(items) != len(item_ids):
            raise DomainError("存在无效的册 ID")
        bad = [it.barcode for it in items if it.status != ItemStatus.ON_SHELF]
        if bad:
            raise InvalidState(f"以下册不在在架状态，不能合订：{', '.join(bad)}")
        title_ids = {it.issue.title_id for it in items}
        if len(title_ids) != 1:
            raise DomainError("只能合订同一刊名的册")
        title = items[0].issue.title
        location = Location.objects.get(pk=location_id)
        bv = BoundVolume.objects.create(
            title=title,
            barcode=barcode,
            label=label or f"{title.name} 合订本",
            location=location,
        )
        for position, item in enumerate(items, start=1):
            BoundVolumeItem.objects.create(
                bound_volume=bv,
                item=item,
                position=position,
                pre_location=item.location,   # 冻结装订前状态，供拆订逐册恢复
                pre_status=item.status,
            )
            item.status = ItemStatus.BOUND
            item.bound_volume = bv
            item.save(update_fields=["status", "bound_volume"])
        _log(
            OperationType.BIND,
            actor=actor,
            title=title,
            bound_volume=bv,
            to_location=location,
            payload={
                "barcode": barcode,
                "label": bv.label,
                "items": [
                    {"item_id": it.id, "barcode": it.barcode, "issue": it.issue.label}
                    for it in items
                ],
            },
        )
        return bv


def unbind(*, bound_volume_id, actor="system") -> BoundVolume:
    """拆订：逐册恢复装订前的位置与状态（不是只覆盖一个条码）。"""
    with transaction.atomic():
        bv = (
            BoundVolume.objects.select_for_update()
            .select_related("title", "location")
            .get(pk=bound_volume_id)
        )
        if bv.status != BoundVolumeStatus.ACTIVE:
            raise InvalidState(f"合订本 {bv.barcode} 已是拆订状态")
        now = timezone.now()
        restored = []
        records = list(bv.bound_items.select_related("item__issue", "pre_location"))
        for record in records:
            item = record.item
            item.status = record.pre_status
            item.location = record.pre_location
            item.bound_volume = None
            item.save(update_fields=["status", "location", "bound_volume"])
            record.unbound_at = now
            record.save(update_fields=["unbound_at"])
            restored.append(
                {
                    "item_id": item.id,
                    "barcode": item.barcode,
                    "restored_location": record.pre_location.code,
                    "restored_status": record.pre_status,
                }
            )
        bv.status = BoundVolumeStatus.UNBOUND
        bv.unbound_at = now
        bv.save(update_fields=["status", "unbound_at"])
        _log(
            OperationType.UNBIND,
            actor=actor,
            title=bv.title,
            bound_volume=bv,
            from_location=bv.location,
            payload={"barcode": bv.barcode, "restored": restored},
        )
        return bv


# ---------------------------------------------------------------- 移库

def move_item(*, item_id, to_location_id, actor="system") -> Item:
    with transaction.atomic():
        item = Item.objects.select_for_update().select_related("issue__title", "location").get(pk=item_id)
        if item.status == ItemStatus.BOUND:
            raise InvalidState(
                f"册 {item.barcode} 已装订于合订本 {item.bound_volume.barcode}，"
                "请对合订本整体移库"
            )
        to_location = Location.objects.get(pk=to_location_id)
        from_location = item.location
        if from_location.pk == to_location.pk:
            raise DomainError("目标位置与当前位置相同")
        item.location = to_location
        item.save(update_fields=["location"])
        _log(
            OperationType.MOVE_ITEM,
            actor=actor,
            title=item.issue.title,
            issue=item.issue,
            item=item,
            from_location=from_location,
            to_location=to_location,
            payload={"barcode": item.barcode},
        )
        return item


def move_bound_volume(*, bound_volume_id, to_location_id, actor="system") -> BoundVolume:
    with transaction.atomic():
        bv = BoundVolume.objects.select_for_update().get(pk=bound_volume_id)
        if bv.status != BoundVolumeStatus.ACTIVE:
            raise InvalidState(f"合订本 {bv.barcode} 已拆订，不能移库")
        to_location = Location.objects.get(pk=to_location_id)
        from_location = bv.location
        if from_location.pk == to_location.pk:
            raise DomainError("目标位置与当前位置相同")
        bv.location = to_location
        bv.save(update_fields=["location"])
        _log(
            OperationType.MOVE_VOLUME,
            actor=actor,
            title=bv.title,
            bound_volume=bv,
            from_location=from_location,
            to_location=to_location,
            payload={"barcode": bv.barcode},
        )
        return bv


# ---------------------------------------------------------------- 登记辅助

def register_issue(*, actor="system", **fields) -> Issue:
    issue = Issue(**fields)
    issue.full_clean()
    with transaction.atomic():
        issue.save()
        _log(
            OperationType.ISSUE_REGISTER,
            actor=actor,
            title=issue.title,
            issue=issue,
            payload={"label": issue.label, "kind": issue.kind},
        )
    return issue
