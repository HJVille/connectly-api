from django.conf import settings
from django.core.cache import cache
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from factories.post_factory import PostFactory
from singletons.config_manager import ConfigManager
from singletons.logger_singleton import LoggerSingleton
from .authentication import TokenAuthentication
from .models import AuthToken, User, Post, Comment, Like
from .permissions import IsAdminRole
from .serializers import (
    CommentSerializer,
    GoogleLoginSerializer,
    LoginSerializer,
    PostDetailSerializer,
    PostSerializer,
    UserSerializer,
)

config_manager = ConfigManager()
logger = LoggerSingleton().get_logger()
FEED_CACHE_VERSION_KEY = 'feed_cache_version'


def is_private_post_hidden(post, user):
    # Private posts are owner-only.
    return post.privacy == Post.PrivacyChoices.PRIVATE and post.author_id != user.id


def get_feed_cache_version():
    # Versioned keys let the feed cache reset in one step.
    version = cache.get(FEED_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(FEED_CACHE_VERSION_KEY, version, None)
    return version


def build_feed_cache_key(user_id, page, page_size):
    # Cache entries vary by user and pagination values.
    return f'feed:user:{user_id}:page:{page}:size:{page_size}:version:{get_feed_cache_version()}'


def invalidate_feed_cache():
    # Bumping the version drops all older feed cache keys at once.
    current_version = get_feed_cache_version()
    cache.set(FEED_CACHE_VERSION_KEY, current_version + 1, None)
    logger.info('Feed cache invalidated.')


def get_public_feed_queryset():
    # Feed only shows public posts.
    return (
        Post.objects.filter(privacy=Post.PrivacyChoices.PUBLIC)
        .select_related('author')
        .prefetch_related('comments', 'comments__author')
        .order_by('-created_at', '-id')
    )


def get_visible_posts_queryset(user):
    # General post listings can include the current user's private posts.
    return (
        Post.objects.filter(Q(privacy=Post.PrivacyChoices.PUBLIC) | Q(author=user))
        .select_related('author')
        .prefetch_related('comments', 'comments__author')
        .order_by('-created_at', '-id')
    )


def get_feed_pagination_values(request):
    # Pull feed defaults from the shared config manager.
    default_page_size = config_manager.get_setting('DEFAULT_PAGE_SIZE')
    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', default_page_size))
    if page < 1 or page_size < 1:
        raise ValueError
    return page, page_size


def create_post_response(request):
    # Shared create flow keeps both post-create endpoints consistent.
    data = request.data
    author_id = data.get('author', request.user.id)

    try:
        # The factory handles post-type and privacy validation before save.
        author = User.objects.get(pk=author_id)
        post = PostFactory.create_post(
            post_type=data['post_type'],
            title=data['title'],
            content=data.get('content', ''),
            metadata=data.get('metadata', {}),
            author=author,
            privacy=data.get('privacy', Post.PrivacyChoices.PUBLIC),
        )
        invalidate_feed_cache()
        logger.info("Post '%s' created successfully by '%s'.", post.title, author.username)
        return Response(
            {'message': 'Post created successfully!', 'post_id': post.id},
            status=status.HTTP_201_CREATED,
        )
    except KeyError as exc:
        logger.warning("Post creation failed: missing field '%s'.", exc.args[0])
        return Response({'error': f"Missing field: {exc.args[0]}"}, status=status.HTTP_400_BAD_REQUEST)
    except User.DoesNotExist:
        logger.warning("Post creation failed: invalid author '%s'.", author_id)
        return Response({'error': 'Author not found.'}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        logger.warning("Post creation failed: %s", exc)
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class UserListCreate(APIView):
    # User list/create endpoint.
    def get(self, request):
        # Return every registered user for the CRUD list endpoint.
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


    def post(self, request):
        # Create local users with hashed passwords and explicit roles.
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            logger.info("User '%s' created successfully.", user.username)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning("User creation failed: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLogin(APIView):
    # Local login returns the custom API token.
    def post(self, request):
        # Successful logins reuse the same token record for the user.
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, _ = AuthToken.objects.get_or_create(user=user)
            logger.info("User '%s' logged in successfully.", user.username)
            return Response(
                {
                    'message': 'Authentication successful!',
                    'user_id': user.id,
                    'username': user.username,
                    'role': user.role,
                    'token': token.key,
                }
            )
        logger.warning("Login failed for username '%s'.", request.data.get('username'))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GoogleLogin(APIView):
    # Google login links the Google account to the local user.
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_data = verify_oauth2_token(
                serializer.validated_data['id_token'],
                GoogleRequest(),
                settings.GOOGLE_OAUTH_CLIENT_ID or None,
            )
        except ValueError:
            logger.warning("Google login failed: invalid or expired token.")
            return Response(
                {'error': 'Invalid or expired Google token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = token_data.get('email')
        google_id = token_data.get('sub')

        if not email or not google_id:
            logger.warning("Google login failed: missing email or Google account ID.")
            return Response(
                {'error': 'Google account information is incomplete.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(google_id=google_id).first()

        if user is None:
            # Existing local accounts are linked by email before creating a new record.
            user = User.objects.filter(email=email).first()

            if user is not None:
                user.google_id = google_id
                user.save(update_fields=['google_id'])
            else:
                base_username = email.split('@')[0]
                username = base_username
                counter = 1

                while User.objects.filter(username=username).exists():
                    username = f'{base_username}{counter}'
                    counter += 1

                user = User.objects.create(
                    username=username,
                    email=email,
                    google_id=google_id,
                )

        token, _ = AuthToken.objects.get_or_create(user=user)
        logger.info("Google login successful for '%s'.", user.username)
        return Response(
            {
                'message': 'Authentication successful!',
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'token': token.key,
            }
        )


class FeedView(APIView):
    # Feed handles pagination and cache reuse in one place.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Cache timeout is configurable through the singleton config manager.
        feed_cache_timeout = config_manager.get_setting('FEED_CACHE_TIMEOUT')

        try:
            page, page_size = get_feed_pagination_values(request)
        except (TypeError, ValueError):
            return Response(
                {'error': 'Page and page_size must be positive integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        feed_cache_key = build_feed_cache_key(request.user.id, page, page_size)
        cached_response = cache.get(feed_cache_key)
        if cached_response is not None:
            # Repeated requests for the same page should use cached data.
            logger.info("Feed cache hit for '%s' on page %s.", request.user.username, page)
            return Response(cached_response)

        logger.info("Feed cache miss for '%s' on page %s.", request.user.username, page)
        posts = get_public_feed_queryset()
        paginator = Paginator(posts, page_size)

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return Response({'error': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PostSerializer(page_obj.object_list, many=True)
        response_data = {
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'total_posts': paginator.count,
            'results': serializer.data,
        }
        cache.set(feed_cache_key, response_data, feed_cache_timeout)
        logger.info("Feed retrieved for '%s' on page %s.", request.user.username, page)
        return Response(response_data)


class AdminUserList(APIView):
    # Admin-only user list endpoint.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        # Homework 8 uses this route to prove admin-only access works.
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class CreatePostView(APIView):
    # Dedicated post-create endpoint.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return create_post_response(request)


class PostListCreate(APIView):
    # General post list/create endpoint.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # The general post list can include the current user's private posts.
        default_page_size = config_manager.get_setting('DEFAULT_PAGE_SIZE')
        try:
            limit = int(request.query_params.get('limit', default_page_size))
        except (TypeError, ValueError):
            limit = default_page_size

        posts = get_visible_posts_queryset(request.user)[:limit]
        serializer = PostSerializer(posts, many=True)
        logger.info("Retrieved %s posts.", len(serializer.data))
        return Response(serializer.data)


    def post(self, request):
        return create_post_response(request)


class PostDetailView(APIView):
    # Post detail plus admin-only delete.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Delete requests require admin access.
        if self.request.method == 'DELETE':
            return [IsAuthenticated(), IsAdminRole()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        # Block private posts for non-owners.
        if is_private_post_hidden(post, request.user):
            return Response({'error': 'This post is private.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = PostDetailSerializer(post)
        return Response(serializer.data)


    def delete(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        post.delete()
        invalidate_feed_cache()
        logger.info("Admin '%s' deleted Post %s.", request.user.username, pk)
        return Response({'message': 'Post deleted successfully.'})


class PostLikeView(APIView):
    # Likes are unique per user and post.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)

        # Homework 5 blocks duplicate likes from the same user.
        if Like.objects.filter(user=request.user, post=post).exists():
            logger.warning("User '%s' attempted to like Post %s multiple times.", request.user.username, post.id)
            return Response({'error': 'Post already liked.'}, status=status.HTTP_400_BAD_REQUEST)

        Like.objects.create(user=request.user, post=post)
        logger.info("User '%s' liked Post %s.", request.user.username, post.id)
        return Response({'message': 'Post liked successfully.'}, status=status.HTTP_201_CREATED)


class PostCommentListCreateView(APIView):
    # Post-specific comment list/create endpoint.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        # Return comments for one post in reverse chronological order.
        post = get_object_or_404(Post, pk=pk)
        comments = Comment.objects.filter(post=post).order_by('-created_at')
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data)


    def post(self, request, pk):
        # Force the authenticated user to be the comment author.
        post = get_object_or_404(Post, pk=pk)
        data = {
            'text': request.data.get('text', ''),
            'author': request.user.id,
            'post': post.id,
        }
        serializer = CommentSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            # New comments change the feed payload.
            invalidate_feed_cache()
            logger.info("User '%s' commented on Post %s.", request.user.username, post.id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning("Comment creation failed on Post %s: %s", post.id, serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentListCreate(APIView):
    # General comment list/create endpoint.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Return all comments for the basic CRUD endpoint.
        comments = Comment.objects.all()
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data)


    def post(self, request):
        # Saving a comment here also invalidates the cached feed.
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            invalidate_feed_cache()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentDetailView(APIView):
    # Comment detail is used for admin-only delete.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def delete(self, request, pk):
        # Only admins can delete comments.
        comment = get_object_or_404(Comment, pk=pk)
        comment.delete()
        invalidate_feed_cache()
        logger.info("Admin '%s' deleted Comment %s.", request.user.username, pk)
        return Response({'message': 'Comment deleted successfully.'})


class ProtectedView(APIView):
    # Simple token-protected check endpoint.
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.info("Protected endpoint accessed by '%s'.", request.user.username)
        return Response({"message": "Authenticated!"})
