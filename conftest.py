# Auteur : Gilles - Projet : AGC Space - Module : Configuration Tests globale
"""
Configuration pytest globale.
- SQLite en mémoire via settings_test.py (pas besoin de PostgreSQL)
- Cache locmem vidé entre chaque test
- Fixtures partagées entre tous les modules
"""
import pytest


@pytest.fixture(autouse=True)
def clear_cache():
    """Vide le cache locmem avant chaque test pour éviter les interférences."""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


# ── Fixtures partagées ────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def vendeur(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username='vendeur', password='pass', email='vendeur@test.com'
    )


@pytest.fixture
def client_user(db):
    from django.contrib.auth import get_user_model
    from users.models import Role
    User = get_user_model()
    user = User.objects.create_user(
        username='client', password='pass', email='client@test.com'
    )
    user.add_role(Role.CLIENT)
    return user


@pytest.fixture
def affilie(db):
    from django.contrib.auth import get_user_model
    from users.models import Role
    User = get_user_model()
    user = User.objects.create_user(
        username='affilie', password='pass', email='affilie@test.com'
    )
    user.add_role(Role.AFFILIE)
    return user


@pytest.fixture
def ecommercant(db):
    from django.contrib.auth import get_user_model
    from users.models import Role
    User = get_user_model()
    user = User.objects.create_user(
        username='vendeur_test', password='pass', email='v@test.com'
    )
    user.add_role(Role.ECOMMERCANT)
    return user


@pytest.fixture
def affiliation_link(product, affilie):
    from affiliations.models import AffiliationLink
    return AffiliationLink.objects.create(
        product=product, affiliate=affilie, commission_rate='0.1500'
    )


@pytest.fixture
def auth_client(api_client, client_user):
    api_client.force_authenticate(user=client_user)
    return api_client


@pytest.fixture
def auth_vendeur(api_client, ecommercant):
    api_client.force_authenticate(user=ecommercant)
    return api_client


@pytest.fixture
def auth_affilie(api_client, affilie):
    api_client.force_authenticate(user=affilie)
    return api_client
