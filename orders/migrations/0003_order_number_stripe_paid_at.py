# Auteur : Gilles - Projet : AGC Space - Migration : order_number, stripe, paid_at, refunded_at
from django.db import migrations, models
from django.utils import timezone


def populate_order_numbers(apps, schema_editor):
    """
    Remplit les order_number vides pour les commandes existantes.
    Format : ORD-YYYY-XXXXXX (même logique que le modèle).
    Appelé avant la création de l'index UNIQUE pour éviter les doublons.
    """
    Order = apps.get_model('orders', 'Order')
    # Grouper par année pour générer des numéros séquentiels cohérents
    orders_without_number = Order.objects.filter(order_number='').order_by('created_at')
    
    # Compter les commandes existantes par année pour continuer la séquence
    year_counters = {}
    for order in orders_without_number:
        year = order.created_at.year
        if year not in year_counters:
            # Compter les commandes déjà numérotées cette année
            existing_count = Order.objects.filter(
                created_at__year=year
            ).exclude(order_number='').count()
            year_counters[year] = existing_count
        
        year_counters[year] += 1
        order.order_number = f"ORD-{year}-{year_counters[year]:06d}"
        order.save(update_fields=['order_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_initial'),
    ]

    operations = [
        # Étape 1 : Ajouter order_number sans contrainte unique (nullable d'abord)
        migrations.AddField(
            model_name='order',
            name='order_number',
            field=models.CharField(
                max_length=30,
                blank=True,
                default='',
                verbose_name='Numéro de commande',
                help_text='Généré automatiquement : ORD-YYYY-XXXXXX',
            ),
        ),
        # Étape 2 : Remplir les order_number vides pour les lignes existantes
        migrations.RunPython(
            populate_order_numbers,
            reverse_code=migrations.RunPython.noop,
        ),
        # Étape 3 : Ajouter l'index unique maintenant que toutes les lignes ont une valeur
        migrations.AlterField(
            model_name='order',
            name='order_number',
            field=models.CharField(
                max_length=30,
                unique=True,
                blank=True,
                db_index=True,
                verbose_name='Numéro de commande',
                help_text='Généré automatiquement : ORD-YYYY-XXXXXX',
            ),
        ),
        # Étape 4 : Ajouter les autres champs Stripe
        migrations.AddField(
            model_name='order',
            name='stripe_payment_intent_id',
            field=models.CharField(
                max_length=255,
                blank=True,
                null=True,
                unique=True,
                verbose_name='Stripe PaymentIntent ID',
                help_text='ID du PaymentIntent Stripe — renseigné lors du checkout',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='paid_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                verbose_name='Date de paiement',
                help_text='Renseigné automatiquement lors du webhook Stripe payment_intent.succeeded',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='refunded_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                verbose_name='Date de remboursement',
            ),
        ),
    ]
