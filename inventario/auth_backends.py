# inventario/auth_backends.py
"""Backend de autenticación que busca usuario por username sin distinguir mayúsculas."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveUsernameBackend(ModelBackend):
    """
    Autentica por username usando búsqueda case-insensitive (iexact).
    Útil si en DB está "Ari" y el frontend envía "ari", o hubo cambio de mayúsculas.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None or password is None:
            return None
        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
