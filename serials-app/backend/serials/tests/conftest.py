import pytest

from serials.models import Frequency, Location, Title, TitleStatus


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


@pytest.fixture
def monthly_title(db):
    return make_title()
