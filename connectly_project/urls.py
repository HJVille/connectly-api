from django.contrib import admin
from django.urls import path, include

from posts.views import FeedView, GoogleLogin

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/google/login/', GoogleLogin.as_view(), name='google-login'),
    path('feed/', FeedView.as_view(), name='feed'),
    path('posts/', include('posts.urls')),
]
