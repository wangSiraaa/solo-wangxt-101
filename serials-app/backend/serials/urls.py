from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BoundVolumeViewSet,
    IssueViewSet,
    ItemViewSet,
    LocationViewSet,
    NumberingLookupView,
    OperationLogViewSet,
    TitleViewSet,
)

router = DefaultRouter()
router.register("titles", TitleViewSet, basename="title")
router.register("issues", IssueViewSet, basename="issue")
router.register("items", ItemViewSet, basename="item")
router.register("bound-volumes", BoundVolumeViewSet, basename="boundvolume")
router.register("locations", LocationViewSet, basename="location")
router.register("logs", OperationLogViewSet, basename="log")

urlpatterns = [
    # 编号检索（含历史版本）：/api/lookup/numbering/?title=&volume=&number=[&at=]
    path("lookup/numbering/", NumberingLookupView.as_view(), name="numbering-lookup"),
    path("", include(router.urls)),
]
