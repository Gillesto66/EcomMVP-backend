# Auteur : Gilles - Projet : AGC Space - Module : Affiliations
from django.contrib import admin
from affiliations.models import AffiliationLink, Commission


@admin.register(AffiliationLink)
class AffiliationLinkAdmin(admin.ModelAdmin):
    list_display = ['affiliate', 'product', 'commission_rate', 'tracking_code', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['tracking_code', 'affiliate__username', 'product__name']
    readonly_fields = ['tracking_code', 'hmac_signature', 'created_at']


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'affiliate', 'amount', 'commission_rate', 'order_total', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['affiliate__username', 'order__id']
    readonly_fields = ['order', 'affiliation_link', 'affiliate', 'order_total', 'commission_rate', 'amount', 'created_at']
    actions = ['validate_commissions', 'mark_paid']

    @admin.action(description='Valider les commissions sélectionnées')
    def validate_commissions(self, request, queryset):
        updated = queryset.filter(status=Commission.STATUS_PENDING).update(status=Commission.STATUS_VALIDATED)
        self.message_user(request, f"{updated} commission(s) validée(s).")

    @admin.action(description='Marquer comme versées')
    def mark_paid(self, request, queryset):
        updated = queryset.filter(status=Commission.STATUS_VALIDATED).update(status=Commission.STATUS_PAID)
        self.message_user(request, f"{updated} commission(s) marquée(s) comme versées.")
