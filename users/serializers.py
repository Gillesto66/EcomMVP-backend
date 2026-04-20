# Auteur : Gilles - Projet : AGC Space - Module : Users
import logging
from django.contrib.auth import get_user_model
from rest_framework import serializers
from users.models import Role

logger = logging.getLogger('users')
User = get_user_model()


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    roles = RoleSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone', 'avatar', 'roles', 'created_at']
        read_only_fields = ['id', 'created_at']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(
        choices=Role.ROLE_CHOICES,
        write_only=True,
        required=False,
        default=Role.CLIENT,
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'phone', 'role']
        extra_kwargs = {
            'email': {'required': True},  # Email obligatoire à l'inscription
        }

    def validate_email(self, value):
        """L'email doit être unique — empêche les doublons de compte."""
        if not value:
            raise serializers.ValidationError("L'adresse email est obligatoire.")
        if User.objects.filter(email__iexact=value).exists():
            logger.warning("Tentative d'inscription avec email déjà utilisé : '%s'", value)
            raise serializers.ValidationError("Un compte avec cette adresse email existe déjà.")
        return value.lower()

    def validate_password(self, value):
        """Validation basique de la robustesse du mot de passe."""
        if value.isdigit():
            raise serializers.ValidationError("Le mot de passe ne peut pas être entièrement numérique.")
        if len(value) < 8:
            raise serializers.ValidationError("Le mot de passe doit contenir au moins 8 caractères.")
        return value

    def create(self, validated_data):
        role_name = validated_data.pop('role', Role.CLIENT)
        try:
            user = User.objects.create_user(
                username=validated_data['username'],
                email=validated_data.get('email', ''),
                password=validated_data['password'],
                phone=validated_data.get('phone', ''),
            )
            user.add_role(role_name)
            logger.info("Nouvel utilisateur enregistré : '%s' avec rôle '%s'", user.username, role_name)
            return user
        except Exception as e:
            logger.error("Erreur lors de l'enregistrement de l'utilisateur : %s", str(e))
            raise


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            logger.warning("Tentative de changement de mot de passe échouée pour '%s'", user.username)
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        if value.isdigit():
            raise serializers.ValidationError("Le nouveau mot de passe ne peut pas être entièrement numérique.")
        return value

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        logger.info("Mot de passe changé avec succès pour '%s'", user.username)
