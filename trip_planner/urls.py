from django.contrib import admin
from django.urls import path
from routing.views import index, health, plan_trip

urlpatterns = [
    path("", index),
    path("admin/", admin.site.urls),
    path("health/", health),
    path("api/plan", plan_trip),
]
