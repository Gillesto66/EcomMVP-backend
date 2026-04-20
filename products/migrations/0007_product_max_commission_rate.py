# Auteur : Gilles - Projet : AGC Space - Migration : taux max commission vendeur
from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0006_phase6_product_images'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='max_commission_rate',
            field=models.DecimalField(
                max_digits=5,
                decimal_places=4,
                null=True,
                blank=True,
                verbose_name='Taux de commission maximum',
                help_text=(
                    'Taux max que le vendeur autorise pour ses affiliés. '
                    'Ex: 0.3000 = 30%. Si null, le plafond global (50%) s\'applique.'
                ),
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0.0001')),
                    django.core.validators.MaxValueValidator(Decimal('0.5000')),
                ],
            ),
        ),
    ]
