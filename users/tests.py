# Auteur : Gilles - Projet : AGC Space - Module : Users - Tests
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


# ── Modèles ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRole:
    def test_role_creation(self):
        from users.models import Role
        role = Role.objects.create(name=Role.CLIENT)
        assert str(role) == 'Client'

    def test_tous_les_roles_valides(self):
        from users.models import Role
        noms = [r[0] for r in Role.ROLE_CHOICES]
        assert Role.ECOMMERCANT in noms
        assert Role.CLIENT in noms
        assert Role.AFFILIE in noms


@pytest.mark.django_db
class TestUser:
    def test_creation_utilisateur(self):
        user = User.objects.create_user(username='testuser', email='t@test.com', password='pass123')
        assert user.pk is not None

    def test_has_role_false_sans_role(self):
        from users.models import Role
        user = User.objects.create_user(username='norole', password='pass')
        assert user.has_role(Role.CLIENT) is False

    def test_add_role_et_has_role(self):
        from users.models import Role
        user = User.objects.create_user(username='roleuser', password='pass')
        user.add_role(Role.AFFILIE)
        assert user.has_role(Role.AFFILIE) is True

    def test_multi_roles(self):
        from users.models import Role
        user = User.objects.create_user(username='multi', password='pass')
        user.add_role(Role.CLIENT)
        user.add_role(Role.AFFILIE)
        assert user.has_role(Role.CLIENT) is True
        assert user.has_role(Role.AFFILIE) is True
        assert user.has_role(Role.ECOMMERCANT) is False

    def test_str_retourne_email(self):
        user = User.objects.create_user(username='u', email='gilles@agcspace.com', password='pass')
        assert str(user) == 'gilles@agcspace.com'


# ── Serializers ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegisterSerializer:
    def test_email_obligatoire(self):
        from users.serializers import RegisterSerializer
        s = RegisterSerializer(data={'username': 'u', 'password': 'pass1234'})
        assert not s.is_valid()
        assert 'email' in s.errors

    def test_email_unique(self):
        """Deux comptes ne peuvent pas avoir le même email."""
        User.objects.create_user(username='existing', email='taken@test.com', password='pass')
        from users.serializers import RegisterSerializer
        s = RegisterSerializer(data={
            'username': 'newuser', 'email': 'taken@test.com', 'password': 'pass1234'
        })
        assert not s.is_valid()
        assert 'email' in s.errors

    def test_email_normalise_en_minuscules(self):
        """L'email est normalisé en minuscules à l'inscription."""
        from users.serializers import RegisterSerializer
        s = RegisterSerializer(data={
            'username': 'caseuser', 'email': 'UPPER@TEST.COM', 'password': 'pass1234'
        })
        assert s.is_valid(), s.errors
        user = s.save()
        assert user.email == 'upper@test.com'

    def test_password_entierement_numerique_rejete(self):
        from users.serializers import RegisterSerializer
        s = RegisterSerializer(data={
            'username': 'numpass', 'email': 'n@test.com', 'password': '12345678'
        })
        assert not s.is_valid()
        assert 'password' in s.errors

    def test_password_trop_court_rejete(self):
        from users.serializers import RegisterSerializer
        s = RegisterSerializer(data={
            'username': 'shortpass', 'email': 's@test.com', 'password': 'abc'
        })
        assert not s.is_valid()
        assert 'password' in s.errors


@pytest.mark.django_db
class TestChangePasswordSerializer:
    def test_nouveau_password_numerique_rejete(self):
        from users.serializers import ChangePasswordSerializer
        from rest_framework.test import APIRequestFactory
        user = User.objects.create_user(username='u', password='oldpass1')
        factory = APIRequestFactory()
        req = factory.post('/')
        req.user = user
        s = ChangePasswordSerializer(
            data={'old_password': 'oldpass1', 'new_password': '12345678'},
            context={'request': req}
        )
        assert not s.is_valid()
        assert 'new_password' in s.errors


# ── API Auth ──────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAuthAPI:
    def test_register_succes(self, api_client):
        resp = api_client.post('/api/v1/auth/register/', {
            'username': 'newuser', 'email': 'new@test.com',
            'password': 'securepass123', 'role': 'client',
        })
        assert resp.status_code == 201

    def test_register_email_manquant(self, api_client):
        resp = api_client.post('/api/v1/auth/register/', {
            'username': 'nomail', 'password': 'securepass123',
        })
        assert resp.status_code == 400
        assert 'email' in resp.data

    def test_register_email_duplique(self, api_client):
        User.objects.create_user(username='existing', email='dup@test.com', password='pass')
        resp = api_client.post('/api/v1/auth/register/', {
            'username': 'autre', 'email': 'dup@test.com', 'password': 'securepass123',
        })
        assert resp.status_code == 400
        assert 'email' in resp.data

    def test_login_jwt(self, api_client):
        User.objects.create_user(username='loginuser', password='pass12345')
        resp = api_client.post('/api/v1/auth/login/', {
            'username': 'loginuser', 'password': 'pass12345'
        })
        assert resp.status_code == 200
        assert 'access' in resp.data
        assert 'refresh' in resp.data

    def test_login_mauvais_mdp(self, api_client):
        User.objects.create_user(username='badpass', password='correct123')
        resp = api_client.post('/api/v1/auth/login/', {
            'username': 'badpass', 'password': 'wrongpassword'
        })
        assert resp.status_code == 401

    def test_me_authentifie(self, api_client):
        user = User.objects.create_user(username='meuser', email='me@test.com', password='pass')
        api_client.force_authenticate(user=user)
        resp = api_client.get('/api/v1/auth/me/')
        assert resp.status_code == 200
        assert resp.data['username'] == 'meuser'

    def test_me_non_authentifie(self, api_client):
        resp = api_client.get('/api/v1/auth/me/')
        assert resp.status_code == 401

    def test_me_update_profil(self, api_client):
        """L'utilisateur peut mettre à jour son profil."""
        user = User.objects.create_user(username='updateme', email='upd@test.com', password='pass')
        api_client.force_authenticate(user=user)
        resp = api_client.patch('/api/v1/auth/me/', {'phone': '0612345678'})
        assert resp.status_code == 200
        assert resp.data['phone'] == '0612345678'


# ── Logout & Blacklist JWT ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLogout:
    def _get_tokens(self, api_client, username='logoutuser', password='pass12345'):
        """Helper : crée un user et retourne ses tokens JWT."""
        User.objects.create_user(username=username, password=password)
        resp = api_client.post('/api/v1/auth/login/', {
            'username': username, 'password': password
        })
        return resp.data['access'], resp.data['refresh']

    def test_logout_succes(self, api_client):
        """Logout révoque le refresh token côté serveur."""
        access, refresh = self._get_tokens(api_client)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        resp = api_client.post('/api/v1/auth/logout/', {'refresh': refresh})
        assert resp.status_code == 200
        assert 'Déconnexion réussie' in resp.data['detail']

    def test_logout_sans_refresh_token(self, api_client):
        """Logout sans refresh token retourne 400."""
        user = User.objects.create_user(username='nort', password='pass12345')
        api_client.force_authenticate(user=user)
        resp = api_client.post('/api/v1/auth/logout/', {})
        assert resp.status_code == 400

    def test_logout_token_blackliste_ne_peut_plus_refresh(self, api_client):
        """Après logout, le refresh token est blacklisté et ne peut plus être utilisé."""
        access, refresh = self._get_tokens(api_client, 'blacklistuser', 'pass12345')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        # Logout → blacklist le refresh token
        api_client.post('/api/v1/auth/logout/', {'refresh': refresh})
        # Tentative de refresh avec le token révoqué
        resp = api_client.post('/api/v1/auth/token/refresh/', {'refresh': refresh})
        assert resp.status_code == 401

    def test_logout_non_authentifie(self, api_client):
        """Logout sans être authentifié retourne 401."""
        resp = api_client.post('/api/v1/auth/logout/', {'refresh': 'fake_token'})
        assert resp.status_code == 401

    def test_logout_token_deja_blackliste(self, api_client):
        """Double logout avec le même token retourne 400."""
        access, refresh = self._get_tokens(api_client, 'doublelogout', 'pass12345')
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        api_client.post('/api/v1/auth/logout/', {'refresh': refresh})
        # Deuxième logout avec le même token
        resp = api_client.post('/api/v1/auth/logout/', {'refresh': refresh})
        assert resp.status_code == 400


# ── Change Password ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestChangePassword:
    def test_change_password_succes(self, api_client):
        user = User.objects.create_user(username='chgpass', password='oldpass123')
        api_client.force_authenticate(user=user)
        resp = api_client.post('/api/v1/auth/me/change-password/', {
            'old_password': 'oldpass123',
            'new_password': 'newpass456',
        })
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password('newpass456')

    def test_change_password_ancien_incorrect(self, api_client):
        user = User.objects.create_user(username='wrongold', password='correct123')
        api_client.force_authenticate(user=user)
        resp = api_client.post('/api/v1/auth/me/change-password/', {
            'old_password': 'wrongpassword',
            'new_password': 'newpass456',
        })
        assert resp.status_code == 400

    def test_change_password_nouveau_numerique_rejete(self, api_client):
        user = User.objects.create_user(username='numchg', password='oldpass123')
        api_client.force_authenticate(user=user)
        resp = api_client.post('/api/v1/auth/me/change-password/', {
            'old_password': 'oldpass123',
            'new_password': '12345678',
        })
        assert resp.status_code == 400
