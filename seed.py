# Auteur : Gilles - Projet : AGC Space - Module : Seed
"""
Script de seed pour initialiser des données de test.
Usage : python seed.py
"""
import os
import django
import logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agc_core.settings')
django.setup()

logger = logging.getLogger('agc_core')

from django.contrib.auth import get_user_model
from users.models import Role
from products.models import Product, PageTemplate, ProductTemplate
from affiliations.models import AffiliationLink

User = get_user_model()


def run():
    logger.info("=== Démarrage du seed AGC Space ===")

    # Rôles
    for role_name, _ in Role.ROLE_CHOICES:
        Role.objects.get_or_create(name=role_name)
    logger.info("Rôles créés.")

    # Utilisateurs
    vendeur, _ = User.objects.get_or_create(username='vendeur_test', defaults={'email': 'vendeur@agcspace.com'})
    vendeur.set_password('agcspace123')
    vendeur.save()
    vendeur.add_role(Role.ECOMMERCANT)

    client, _ = User.objects.get_or_create(username='client_test', defaults={'email': 'client@agcspace.com'})
    client.set_password('agcspace123')
    client.save()
    client.add_role(Role.CLIENT)

    affilie, _ = User.objects.get_or_create(username='affilie_test', defaults={'email': 'affilie@agcspace.com'})
    affilie.set_password('agcspace123')
    affilie.save()
    affilie.add_role(Role.AFFILIE)
    logger.info("Utilisateurs créés : vendeur_test, client_test, affilie_test (mdp: agcspace123)")

    # Produit
    product, _ = Product.objects.get_or_create(
        sku='FORM-DJG-001',
        defaults={
            'owner': vendeur,
            'name': 'Formation Django REST Framework',
            'description': 'Maîtrisez Django et DRF de zéro à la production.',
            'price': '97.00',
            'is_digital': True,
        }
    )
    logger.info("Produit créé : '%s'", product.name)

    # PageTemplate
    config = {
        "blocks": [
            {"type": "hero", "image": "/media/hero.jpg", "text": "Maîtrisez Django en 30 jours"},
            {"type": "features", "items": ["DRF", "JWT", "PostgreSQL", "Tests"]},
            {"type": "testimonials", "items": []},
            {"type": "buy_button", "label": "Acheter maintenant", "style": "primary"},
        ]
    }
    template, _ = PageTemplate.objects.get_or_create(
        name='Template Formation',
        defaults={'config': config, 'created_by': vendeur, 'is_public': True}
    )
    ProductTemplate.objects.get_or_create(product=product, template=template, defaults={'is_active': True})
    logger.info("PageTemplate créé et associé au produit.")

    # Lien d'affiliation
    link, _ = AffiliationLink.objects.get_or_create(
        product=product,
        affiliate=affilie,
        defaults={'commission_rate': '0.1500'}
    )
    logger.info("Lien d'affiliation créé — tracking_code: %s", link.tracking_code)

    logger.info("=== Seed terminé avec succès ===")
    print("\n✅ Seed terminé. Utilisateurs : vendeur_test / client_test / affilie_test (mdp: agcspace123)")
    print(f"   URL affiliation test : /shop/{product.pk}/?ref={link.tracking_code}")


if __name__ == '__main__':
    run()
