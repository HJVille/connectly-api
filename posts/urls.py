from django.urls import path
from .views import (
    AdminUserList,
    CreatePostView,
    UserListCreate,
    UserLogin,
    PostListCreate,
    PostDetailView,
    ProtectedView,
    CommentListCreate,
)


urlpatterns = [
    path('users/', UserListCreate.as_view(), name='user-list-create'),
    path('login/', UserLogin.as_view(), name='user-login'),
    path('protected/', ProtectedView.as_view(), name='protected-view'),
    path('admin/users/', AdminUserList.as_view(), name='admin-user-list'),
    path('posts/create/', CreatePostView.as_view(), name='create-post'),
    path('posts/', PostListCreate.as_view(), name='post-list-create'),
    path('posts/<int:pk>/', PostDetailView.as_view(), name='post-detail'),
    path('comments/', CommentListCreate.as_view(), name='comment-list-create'),
]
