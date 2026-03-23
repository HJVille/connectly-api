from django.contrib import admin
from django.urls import path, include

from posts.views import AdminUserList, FeedView, GoogleLogin, ProtectedView, UserListCreate, UserLogin

urlpatterns = [
    path('admin/', admin.site.urls),
    # Authentication endpoints stay outside the posts namespace.
    path('auth/login/', UserLogin.as_view(), name='user-login'),
    path('auth/google/login/', GoogleLogin.as_view(), name='google-login'),
    path('auth/protected/', ProtectedView.as_view(), name='protected-view'),
    # User management endpoints stay separate from post operations.
    path('users/', UserListCreate.as_view(), name='user-list-create'),
    path('users/admin/', AdminUserList.as_view(), name='admin-user-list'),
    path('feed/', FeedView.as_view(), name='feed'),
    path('posts/', include('posts.urls')),
]
