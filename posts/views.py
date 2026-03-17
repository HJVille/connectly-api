from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
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
from .permissions import IsAdminRole, IsPostAuthor
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


class UserListCreate(APIView):
    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            logger.info("User '%s' created successfully.", user.username)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning("User creation failed: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLogin(APIView):
    def post(self, request):
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
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        default_page_size = config_manager.get_setting('DEFAULT_PAGE_SIZE')

        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', default_page_size))
            if page < 1 or page_size < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {'error': 'Page and page_size must be positive integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        posts = Post.objects.all().order_by('-created_at', '-id')
        paginator = Paginator(posts, page_size)

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return Response({'error': 'Page not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PostSerializer(page_obj.object_list, many=True)
        logger.info("Feed retrieved for '%s' on page %s.", request.user.username, page)
        return Response(
            {
                'page': page,
                'page_size': page_size,
                'total_pages': paginator.num_pages,
                'total_posts': paginator.count,
                'results': serializer.data,
            }
        )


class AdminUserList(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class CreatePostView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        author_id = data.get('author', request.user.id)

        try:
            author = User.objects.get(pk=author_id)
            post = PostFactory.create_post(
                post_type=data['post_type'],
                title=data['title'],
                content=data.get('content', ''),
                metadata=data.get('metadata', {}),
                author=author,
            )
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


class PostListCreate(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        default_page_size = config_manager.get_setting('DEFAULT_PAGE_SIZE')
        try:
            limit = int(request.query_params.get('limit', default_page_size))
        except (TypeError, ValueError):
            limit = default_page_size

        posts = Post.objects.all()[:limit]
        serializer = PostSerializer(posts, many=True)
        logger.info("Retrieved %s posts.", len(serializer.data))
        return Response(serializer.data)


    def post(self, request):
        return CreatePostView().post(request)


class PostDetailView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsPostAuthor]

    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        self.check_object_permissions(request, post)
        serializer = PostDetailSerializer(post)
        return Response(serializer.data)


class PostLikeView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)

        if Like.objects.filter(user=request.user, post=post).exists():
            logger.warning("User '%s' attempted to like Post %s multiple times.", request.user.username, post.id)
            return Response({'error': 'Post already liked.'}, status=status.HTTP_400_BAD_REQUEST)

        Like.objects.create(user=request.user, post=post)
        logger.info("User '%s' liked Post %s.", request.user.username, post.id)
        return Response({'message': 'Post liked successfully.'}, status=status.HTTP_201_CREATED)


class PostCommentListCreateView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        comments = Comment.objects.filter(post=post).order_by('-created_at')
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data)


    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        data = {
            'text': request.data.get('text', ''),
            'author': request.user.id,
            'post': post.id,
        }
        serializer = CommentSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            logger.info("User '%s' commented on Post %s.", request.user.username, post.id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning("Comment creation failed on Post %s: %s", post.id, serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentListCreate(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        comments = Comment.objects.all()
        serializer = CommentSerializer(comments, many=True)
        return Response(serializer.data)


    def post(self, request):
        serializer = CommentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProtectedView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.info("Protected endpoint accessed by '%s'.", request.user.username)
        return Response({"message": "Authenticated!"})
