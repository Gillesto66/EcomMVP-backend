# Auteur : Gilles - Projet : AGC Space - Module : Products
from django.contrib import admin
from products.models import Product, PageTemplate, ProductTemplate, Theme


class ProductTemplateInline(admin.TabularInline):
    model = ProductTemplate
    extra = 0
    fields = ['template', 'is_active', 'assigned_at']
    readonly_fields = ['assigned_at']


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ['owner', 'name', 'updated_at']
    search_fields = ['owner__username', 'name']
    readonly_fields = ['updated_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'owner', 'price', 'stock', 'is_digital', 'is_active', 'created_at']
    list_filter = ['is_digital', 'is_active']
    search_fields = ['name', 'sku']
    inlines = [ProductTemplateInline]


@admin.register(PageTemplate)
class PageTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'is_public', 'created_at']
    list_filter = ['is_public']
    search_fields = ['name']
    readonly_fields = ['critical_css']


@admin.register(ProductTemplate)
class ProductTemplateAdmin(admin.ModelAdmin):
    list_display = ['product', 'template', 'is_active', 'assigned_at']
    list_filter = ['is_active']
