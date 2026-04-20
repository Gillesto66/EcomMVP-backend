# Auteur : Gilles - Projet : AGC Space - Module : Products
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from products.views import ProductViewSet, PageTemplateViewSet, ThemeViewSet, PageRenderView, VendeurStatsView, BuilderInitView, FileUploadView

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'templates', PageTemplateViewSet, basename='pagetemplate')
router.register(r'themes', ThemeViewSet, basename='theme')

urlpatterns = [
    path('', include(router.urls)),
    path('render/<int:product_id>/', PageRenderView.as_view(), name='page-render'),
    path('builder/<int:product_id>/init/', BuilderInitView.as_view(), name='builder-init'),
    path('dashboard/stats/', VendeurStatsView.as_view(), name='vendeur-stats'),
    path('upload/', FileUploadView.as_view(), name='file-upload'),
]
