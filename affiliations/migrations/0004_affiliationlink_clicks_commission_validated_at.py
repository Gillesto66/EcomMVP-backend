# Auteur : Gilles - Projet : AGC Space - Migration : clicks_count + validated_at
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('affiliations', '0003_phase3_commission'),
    ]

    operations = [
        migrations.AddField(
            model_name='affiliationlink',
            name='clicks_count',
            field=models.PositiveIntegerField(
                default=0,
                verbose_name='Nombre de clics',
                help_text='Incrémenté à chaque validation de lien (GET /affiliations/validate/)',
            ),
        ),
        migrations.AddField(
            model_name='commission',
            name='validated_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                verbose_name='Date de validation',
                help_text='Renseigné automatiquement lors du passage en statut validated',
            ),
        ),
    ]
