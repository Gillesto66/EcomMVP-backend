# Auteur : Gilles - Projet : AGC Space - Module : Affiliations
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from affiliations.views import (
    AffiliationLinkViewSet,
    CommissionViewSet,
    ValidateAffiliationView,
    AffiliationMarketplaceView,
    VendeurAffiliatesView,
    VendeurCommissionsView,
    VendeurValidateCommissionView,
)

router = DefaultRouter()
router.register(r'links', AffiliationLinkViewSet, basename='affiliation-link')
router.register(r'commissions', CommissionViewSet, basename='commission')

urlpatterns = [
    path('', include(router.urls)),
    path('validate/', ValidateAffiliationView.as_view(), name='affiliation-validate'),
    path('marketplace/', AffiliationMarketplaceView.as_view(), name='affiliation-marketplace'),
    # ── Vues Vendeur ──────────────────────────────────────────────────────────
    path('vendeur/affiliates/', VendeurAffiliatesView.as_view(), name='vendeur-affiliates'),
    path('vendeur/commissions/', VendeurCommissionsView.as_view(), name='vendeur-commissions'),
    path('vendeur/commissions/<int:pk>/validate/', VendeurValidateCommissionView.as_view(), name='vendeur-commission-validate'),
]
