from rest_framework.permissions import BasePermission

from .models import User


class IsAdminRole(BasePermission):
    message = 'Admin role required.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Roles.ADMIN
        )


class IsPostAuthor(BasePermission):
    message = 'You can only access your own posts.'

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.author_id == request.user.id
        )
