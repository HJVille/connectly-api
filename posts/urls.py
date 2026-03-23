from django.urls import path
from .views import (
    CommentDetailView,
    CreatePostView,
    PostCommentListCreateView,
    PostLikeView,
    PostListCreate,
    PostDetailView,
    CommentListCreate,
)


urlpatterns = [
    # Post endpoints stay grouped under /posts/.
    path('posts/create/', CreatePostView.as_view(), name='create-post'),
    path('posts/', PostListCreate.as_view(), name='post-list-create'),
    path('posts/<int:pk>/like/', PostLikeView.as_view(), name='post-like'),
    path('posts/<int:pk>/comment/', PostCommentListCreateView.as_view(), name='post-comment'),
    path('posts/<int:pk>/comments/', PostCommentListCreateView.as_view(), name='post-comments'),
    path('posts/<int:pk>/', PostDetailView.as_view(), name='post-detail'),
    # Comment deletion is separated so admin-only access is easy to enforce.
    path('comments/', CommentListCreate.as_view(), name='comment-list-create'),
    path('comments/<int:pk>/', CommentDetailView.as_view(), name='comment-detail'),
]
