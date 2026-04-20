# Auteur : Gilles - Projet : AGC Space - Module : Users
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from users.models import User, Role


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['id', 'name']


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'phone', 'is_active', 'created_at']
    list_filter = ['roles', 'is_active', 'is_staff']
    search_fields = ['username', 'email']
    filter_horizontal = ['roles', 'groups', 'user_permissions']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('AGC Space', {'fields': ('phone', 'avatar', 'roles')}),
    )
