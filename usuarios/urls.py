# usuarios/urls.py
from django.urls import path
from usuarios.views import CustomLoginView

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
]
