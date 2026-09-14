import pytest

from serials import services
from serials.models import Frequency, IssueKind, Location, Title, TitleStatus


@pytest.fixture
def locations(db):
    return {
        "xk": Location.objects.create(code="XK-1F", name="一层现刊阅览区"),
        "gk": Location.objects.create(code="GK-2F", name="二层过刊库"),
        "mj": Location.objects.create(code="MJ-B1", name="地下密集书库"),
    }


def make_title(**kw):
    defaults = dict(
        name="测试月刊",
        frequency=Frequency.MONTHLY,
        start_year=2024,
        start_month=1,
        volume_start_number=1,
        volume_start_year=2024,
        volume_start_month=1,
        months_per_volume=12,
        status=TitleStatus.ACTIVE,
    )
    defaults.update(kw)
    return Title.objects.create(**defaults)


def make_issue(title, number=1, volume=1, pub_year=2024, pub_month=None,
               kind=IssueKind.REGULAR, number_end=None, supplement_no=0, note=""):
    """通过服务层登记出版单元（同时建立首版编号映射）。"""
    return services.register_issue(
        title=title,
        kind=kind,
        pub_year=pub_year,
        pub_month=pub_month if pub_month is not None else (number or 1),
        volume=volume,
        number=number,
        number_end=number_end,
        supplement_no=supplement_no,
        note=note,
    )


@pytest.fixture
def monthly_title(db):
    return make_title()
