# Auteur : Gilles - Projet : AGC Space - Module : Users
import logging
from django.contrib.auth.models import AbstractUser
from django.db import models

logger = logging.getLogger('users')


class Role(models.Model):
    """Rôles disponibles dans la plateforme AGC Space."""

    ECOMMERCANT = 'ecommercant'
    CLIENT = 'client'
    AFFILIE = 'affilie'

    ROLE_CHOICES = [
        (ECOMMERCANT, 'E-commerçant'),
        (CLIENT, 'Client'),
        (AFFILIE, 'Affilié'),
    ]

    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)

    class Meta:
        verbose_name = 'Rôle'
        verbose_name_plural = 'Rôles'

    def __str__(self):
        return self.get_name_display()


class User(AbstractUser):
    """
    Utilisateur AGC Space.
    Étend AbstractUser avec support multi-rôles et champs métier.
    """

    roles = models.ManyToManyField(
        Role,
        blank=True,
        related_name='users',
        verbose_name='Rôles',
    )
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        return self.email or self.username

    def has_role(self, role_name: str) -> bool:
        """Vérifie si l'utilisateur possède un rôle donné."""
        result = self.roles.filter(name=role_name).exists()
        logger.debug(
            "Vérification rôle '%s' pour user '%s' : %s",
            role_name, self.username, result
        )
        return result

    def add_role(self, role_name: str) -> None:
        """Ajoute un rôle à l'utilisateur."""
        try:
            role, _ = Role.objects.get_or_create(name=role_name)
            self.roles.add(role)
            logger.info("Rôle '%s' ajouté à l'utilisateur '%s'", role_name, self.username)
        except Exception as e:
            logger.error(
                "Erreur lors de l'ajout du rôle '%s' à '%s' : %s",
                role_name, self.username, str(e)
            )
            raise
