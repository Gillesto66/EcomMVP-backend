# Auteur : Gilles - Projet : AGC Space - Module : Users
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from users.views import RegisterView, MeView, ChangePasswordView, LoginView, LogoutView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='user-register'),
    path('login/', LoginView.as_view(), name='token-obtain'),          # Throttle anti brute-force
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', LogoutView.as_view(), name='user-logout'),         # Révocation refresh token
    path('me/', MeView.as_view(), name='user-me'),
    path('me/change-password/', ChangePasswordView.as_view(), name='change-password'),
]
