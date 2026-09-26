from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health),
    path("chat/", views.chat),
    path("voice/", views.voice),
]
