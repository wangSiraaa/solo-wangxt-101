"""枚举规则：跨年卷、停刊、频率步长、合期覆盖、编号校验。"""
import pytest
from django.core.exceptions import ValidationError

from serials import services
from serials.models import Frequency, IssueKind, TitleStatus
from serials.rules import expected_slots, issue_covers

from .conftest import make_issue, make_title

pytestmark = pytest.mark.django_db


def slot_map(title, upto):
    return {(s.year, s.month): (s.volume, s.number) for s in expected_slots(title, upto)}


def test_monthly_volume_per_year():
    title = make_title(volume_start_number=10)
    slots = slot_map(title, (2025, 3))
    assert slots[(2024, 1)] == (10, 1)
    assert slots[(2024, 12)] == (10, 12)
    assert slots[(2025, 1)] == (11, 1)
    assert slots[(2025, 3)] == (11, 3)


def test_cross_year_volume():
    """跨年卷：每年7月起卷，第37卷 = 2024-07 .. 2025-06。"""
    title = make_title(
        name="海洋学报", start_year=2023, start_month=7,
        volume_start_number=36, volume_start_year=2023, volume_start_month=7,
    )
    slots = slot_map(title, (2025, 8))
    assert slots[(2023, 7)] == (36, 1)
    assert slots[(2024, 6)] == (36, 12)
    assert slots[(2024, 7)] == (37, 1)   # 跨年：2024 下半年仍属第37卷
    assert slots[(2025, 6)] == (37, 12)  # 次年6月卷终
    assert slots[(2025, 7)] == (38, 1)


def test_ceased_title_stops_slots():
    """停刊月份之后不再产生应到 slot。"""
    title = make_title(
        name="地质季刊", frequency=Frequency.QUARTERLY,
        start_year=2024, start_month=1,
        volume_start_year=2024, volume_start_month=1,
        status=TitleStatus.CEASED, ceased_year=2025, ceased_month=4,
    )
    slots = expected_slots(title, upto=(2026, 12))
    assert slots[-1].year == 2025 and slots[-1].month == 4
    assert (slots[-1].volume, slots[-1].number) == (2, 2)
    assert all((s.year, s.month) != (2025, 7) for s in slots)


def test_frequency_step():
    title = make_title(frequency=Frequency.QUARTERLY)
    months = [(s.year, s.month) for s in expected_slots(title, (2024, 12))]
    assert months == [(2024, 1), (2024, 4), (2024, 7), (2024, 10)]


def test_combined_issue_covers_two_numbers(monthly_title):
    issue = make_issue(monthly_title, number=7, number_end=8, kind=IssueKind.COMBINED)
    assert issue_covers(issue) == [(1, 7), (1, 8)]


def test_supplement_covers_nothing(monthly_title):
    issue = make_issue(monthly_title, number=None, volume=None,
                       kind=IssueKind.SUPPLEMENT, supplement_no=1, pub_month=5)
    assert issue_covers(issue) == []


def test_numbering_validation_rules(monthly_title):
    with pytest.raises(services.DomainError):  # 合期止号必须大于起号
        make_issue(monthly_title, number=8, number_end=7, kind=IssueKind.COMBINED)
    with pytest.raises(ValidationError):  # 增刊必须有增刊序号
        make_issue(monthly_title, number=None, volume=None,
                   kind=IssueKind.SUPPLEMENT, supplement_no=0)
    with pytest.raises(services.DomainError):  # 正期必须有卷期编号
        make_issue(monthly_title, number=None, volume=None)


def test_no_issue_after_ceased(monthly_title):
    monthly_title.status = TitleStatus.CEASED
    monthly_title.ceased_year, monthly_title.ceased_month = 2024, 6
    monthly_title.save()
    with pytest.raises(ValidationError):
        make_issue(monthly_title, number=7, pub_month=7)
