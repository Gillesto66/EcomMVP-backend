# Auteur : Gilles - Projet : AGC Space - Module : Users
import logging
from django.contrib.auth import get_user_model
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from users.serializers import RegisterSerializer, UserSerializer, ChangePasswordSerializer

logger = logging.getLogger('users')
User = get_user_model()


# ── Throttle dédié anti brute-force login ─────────────────────────────────────

class LoginRateThrottle(AnonRateThrottle):
    """
    Limite les tentatives de connexion à 10/minute par IP.
    Protège contre le brute-force sur /auth/login/.
    """
    scope = 'login'


# ── LoginView avec throttle dédié ────────────────────────────────────────────

class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login/
    Surcharge TokenObtainPairView pour ajouter :
      - Throttle anti brute-force (10 req/min par IP)
      - Log des tentatives de connexion (succès et échecs)
    """
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        username = request.data.get('username', '')
        logger.info("Tentative de connexion — username: '%s', IP: %s",
                    username, self._get_client_ip(request))
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            logger.info("Connexion réussie — username: '%s'", username)
        else:
            logger.warning("Échec de connexion — username: '%s', IP: %s",
                           username, self._get_client_ip(request))
        return response

    def _get_client_ip(self, request) -> str:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')


# ── RegisterView ──────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """Inscription d'un nouvel utilisateur."""
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'register'  # 5 req/min par IP — anti-spam inscription

    def create(self, request, *args, **kwargs):
        logger.info("Tentative d'inscription — username: '%s'", request.data.get('username'))
        return super().create(request, *args, **kwargs)


# ── MeView ────────────────────────────────────────────────────────────────────

class MeView(generics.RetrieveUpdateAPIView):
    """Profil de l'utilisateur connecté."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        logger.debug("Récupération du profil pour '%s'", self.request.user.username)
        return self.request.user


# ── ChangePasswordView ────────────────────────────────────────────────────────

class ChangePasswordView(APIView):
    """Changement de mot de passe."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({'detail': 'Mot de passe mis à jour.'}, status=status.HTTP_200_OK)
        logger.warning("Changement de mot de passe invalide pour '%s'", request.user.username)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── LogoutView ────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Révoque le refresh token côté serveur via la blacklist JWT.
    Garantit qu'un token volé ne peut plus être utilisé après déconnexion.

    Body : { "refresh": "<refresh_token>" }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            logger.warning("Logout sans refresh token — user: '%s'", request.user.username)
            return Response(
                {'detail': 'Le champ "refresh" est requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("Logout réussi — refresh token révoqué pour '%s'", request.user.username)
            return Response({'detail': 'Déconnexion réussie.'}, status=status.HTTP_200_OK)
        except TokenError as e:
            logger.warning("Logout — token invalide ou déjà révoqué pour '%s' : %s",
                           request.user.username, str(e))
            return Response({'detail': 'Token invalide ou déjà révoqué.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Erreur inattendue lors du logout pour '%s' : %s",
                         request.user.username, str(e))
            return Response({'detail': 'Erreur lors de la déconnexion.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
