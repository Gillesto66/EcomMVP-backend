# Auteur : Gilles - Projet : AGC Space - Module : Orders
from django.contrib import admin
from orders.models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['unit_price', 'subtotal_display']
    fields = ['product', 'quantity', 'unit_price', 'subtotal_display']

    def subtotal_display(self, obj):
        return f"{obj.subtotal}€"
    subtotal_display.short_description = 'Sous-total'


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'total', 'referral_code', 'has_commission', 'created_at']
    list_filter = ['status']
    search_fields = ['customer__username', 'referral_code']
    readonly_fields = ['total', 'created_at', 'updated_at']
    inlines = [OrderItemInline]

    def has_commission(self, obj):
        return hasattr(obj, 'commission')
    has_commission.boolean = True
    has_commission.short_description = 'Commission'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'unit_price']
