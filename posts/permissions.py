from rest_framework.permissions import BasePermission

from .models import User


class IsAdminRole(BasePermission):
    # Shared admin-role check used by Homework 8 delete and admin list endpoints.
    message = 'Admin role required.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Roles.ADMIN
        )


class IsPostAuthor(BasePermission):
    # Separate owner check for author-only access rules.
    message = 'You can only access your own posts.'

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.author_id == request.user.id
        )
