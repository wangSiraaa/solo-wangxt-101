"""卷期枚举规则与缺藏分析（纯逻辑，不写库）。

规则要点：
  * 发行年月与卷期编号分离：slot 由发行规则推出，卷号按 volume_start_*
    与 months_per_volume 推算，因此天然支持跨年卷（如每年 7 月起卷）。
  * 合期：一期物理合刊覆盖 number..number_end 多个 slot，被覆盖的 slot
    不算缺号，更不算缺藏。
  * 增刊：不占正期 slot，单独列出。
  * 停刊：ceased_year/ceased_month 之后不再产生应到 slot。
  * 缺号 != 缺藏：NOT_PUBLISHED（无出版登记）与 MISSING（已出版但无实体）
    是两种不同状态，逐项给出核实提示。
"""
from dataclasses import dataclass, field
from datetime import date

from .models import FREQUENCY_STEP_MONTHS, IssueKind, TitleStatus

# slot 状态
HELD = "HELD"                      # 在藏
MISSING = "MISSING"                # 缺藏：已出版登记，但无任何实体
NOT_PUBLISHED = "NOT_PUBLISHED"    # 缺号：无出版登记（未必缺藏）


def month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def index_to_year_month(idx: int) -> tuple[int, int]:
    return idx // 12, idx % 12 + 1


@dataclass(frozen=True)
class Slot:
    """应到期：某刊按规则在某发行年月应有一期。"""

    year: int
    month: int
    volume: int
    number: int


def expected_slots(title, upto: tuple[int, int] | None = None) -> list[Slot]:
    """按枚举规则生成应到 slot 序列（创刊月起，至停刊月或 upto 止）。"""
    if upto is None:
        today = date.today()
        upto = (today.year, today.month)
    start = month_index(title.start_year, title.start_month)
    if title.status == TitleStatus.CEASED:
        end = month_index(title.ceased_year, title.ceased_month)
    else:
        end = month_index(*upto)
    step = FREQUENCY_STEP_MONTHS[title.frequency]
    v0 = month_index(title.volume_start_year, title.volume_start_month)
    slots: list[Slot] = []
    idx = start
    while idx <= end:
        volume_offset = (idx - v0) // title.months_per_volume
        volume = title.volume_start_number + volume_offset
        volume_start_idx = v0 + volume_offset * title.months_per_volume
        number = (idx - volume_start_idx) // step + 1
        year, month = index_to_year_month(idx)
        slots.append(Slot(year=year, month=month, volume=volume, number=number))
        idx += step
    return slots


def issue_covers(issue) -> list[tuple[int, int]]:
    """该期覆盖的 (卷, 期号) 列表。合期覆盖多个，增刊不覆盖。"""
    if issue.kind == IssueKind.SUPPLEMENT or issue.volume is None or issue.number is None:
        return []
    end = issue.number_end or issue.number
    return [(issue.volume, n) for n in range(issue.number, end + 1)]


def coverage_map(title):
    """(卷, 期号) -> Issue 的覆盖映射；重复覆盖记入 conflicts 供核实。"""
    cov: dict[tuple[int, int], object] = {}
    conflicts: list[dict] = []
    issues = title.issues.exclude(kind=IssueKind.SUPPLEMENT).order_by("id")
    for issue in issues:
        for key in issue_covers(issue):
            if key in cov:
                conflicts.append(
                    {
                        "volume": key[0],
                        "number": key[1],
                        "first_issue_id": cov[key].id,
                        "duplicate_issue_id": issue.id,
                    }
                )
            else:
                cov[key] = issue
    return cov, conflicts


@dataclass
class SlotRow:
    slot: Slot
    state: str
    issue: object | None = None
    items: list = field(default_factory=list)


@dataclass
class Analysis:
    title: object
    rows: list[SlotRow]
    supplements: list
    conflicts: list

    @property
    def stats(self) -> dict:
        return {
            "expected": len(self.rows),
            "held": sum(1 for r in self.rows if r.state == HELD),
            "missing": sum(1 for r in self.rows if r.state == MISSING),
            "not_published": sum(1 for r in self.rows if r.state == NOT_PUBLISHED),
        }


def analyze_title(title, upto: tuple[int, int] | None = None) -> Analysis:
    """逐 slot 判定在藏 / 缺藏 / 缺号，结果可逐项核实。"""
    slots = expected_slots(title, upto)
    cov, conflicts = coverage_map(title)
    issues = {i.id: i for i in title.issues.all()}
    items_by_issue: dict[int, list] = {}
    for issue_id in issues:
        items_by_issue[issue_id] = list(
            issues[issue_id].items.select_related("location", "bound_volume__location")
        )
    rows: list[SlotRow] = []
    for slot in slots:
        issue = cov.get((slot.volume, slot.number))
        if issue is None:
            rows.append(SlotRow(slot=slot, state=NOT_PUBLISHED))
            continue
        items = items_by_issue.get(issue.id, [])
        rows.append(SlotRow(slot=slot, state=HELD if items else MISSING, issue=issue, items=items))
    supplements = list(
        title.issues.filter(kind=IssueKind.SUPPLEMENT)
        .order_by("pub_year", "pub_month", "supplement_no")
        .prefetch_related("items__location", "items__bound_volume__location")
    )
    return Analysis(title=title, rows=rows, supplements=supplements, conflicts=conflicts)


def verification_hint(title, row: SlotRow) -> str:
    """缺藏 / 缺号的逐项核实提示。"""
    s = row.slot
    if row.state == MISSING:
        return (
            f"第{s.volume}卷第{s.number}期（{s.year}年{s.month}月）已有出版登记"
            f"「{row.issue.label}」，但无任何馆藏实体。请逐项核对："
            f"1) 采购与登到记录；2) 架位与在途；3) 是否尚在装订车间。"
        )
    return (
        f"按《{title.name}》枚举规则，{s.year}年{s.month}月应有第{s.volume}卷第{s.number}期，"
        f"但无出版登记。缺号不等于缺藏：请与出版方核实该期是否出版"
        f"（可能休刊、或应以合期/增刊形式登记）。"
    )
