from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication

from .models import AuthToken


class TokenAuthentication(BaseAuthentication):
    # Read custom API tokens from the Authorization header used in Postman tests.
    keyword = 'Token'

    def authenticate(self, request):
        # Public endpoints can continue without a token.
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
            # Tokens link straight to the custom user record.
            token = AuthToken.objects.select_related('user').get(key=key)
        except AuthToken.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed('Invalid token.') from exc

        return (token.user, token)
