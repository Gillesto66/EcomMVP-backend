# Auteur : Gilles - Projet : AGC Space - Module : Products - Migration Phase 4
"""
Migration Phase 4 : Index GIN sur les champs JSONField (JSONB PostgreSQL).
Ces index sont spécifiques à PostgreSQL et ignorés silencieusement sur SQLite.
"""
from django.db import migrations, connection


def create_gin_indexes(apps, schema_editor):
    """Crée les index GIN uniquement sur PostgreSQL."""
    if connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        statements = [
            """CREATE INDEX IF NOT EXISTS products_pagetemplate_config_gin
               ON products_pagetemplate USING GIN (config jsonb_path_ops)""",
            """CREATE INDEX IF NOT EXISTS products_theme_variables_gin
               ON products_theme USING GIN (variables jsonb_path_ops)""",
            """CREATE INDEX IF NOT EXISTS orders_order_referral_partial
               ON orders_order (referral_code)
               WHERE referral_code IS NOT NULL""",
            """CREATE INDEX IF NOT EXISTS affiliations_link_tracking_code_idx
               ON affiliations_affiliationlink (tracking_code)
               WHERE is_active = true""",
        ]
        for sql in statements:
            try:
                cursor.execute(sql)
            except Exception as e:
                # Index peut déjà exister — pas bloquant
                pass


def drop_gin_indexes(apps, schema_editor):
    """Supprime les index GIN uniquement sur PostgreSQL."""
    if connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        for name in [
            'products_pagetemplate_config_gin',
            'products_theme_variables_gin',
            'orders_order_referral_partial',
            'affiliations_link_tracking_code_idx',
        ]:
            cursor.execute(f'DROP INDEX IF EXISTS {name}')


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0003_phase2_theme_stock_critical_css'),
    ]

    operations = [
        migrations.RunPython(
            create_gin_indexes,
            reverse_code=drop_gin_indexes,
        ),
    ]
