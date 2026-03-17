from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from .models import AuthToken


class TokenAuthentication(BaseAuthentication):
    keyword = 'Token'

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return None

        try:
            keyword, key = auth_header.split()
        except ValueError as exc:
            raise exceptions.AuthenticationFailed('Invalid token header.') from exc

        if keyword != self.keyword:
            return None

        try:
            token = AuthToken.objects.select_related('user').get(key=key)
        except AuthToken.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed('Invalid token.') from exc

        return (token.user, token)
