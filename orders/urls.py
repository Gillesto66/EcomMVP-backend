# Auteur : Gilles - Projet : AGC Space - Module : Orders
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from orders.views import OrderViewSet, CreateOrderView, VendeurOrdersView, StripeWebhookView

router = DefaultRouter()
router.register(r'', OrderViewSet, basename='order')

urlpatterns = [
    path('create/', CreateOrderView.as_view(), name='order-create'),
    path('vendeur/', VendeurOrdersView.as_view(), name='vendeur-orders'),
    path('stripe/webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('', include(router.urls)),
]
