from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from factories.post_factory import PostFactory
from singletons.config_manager import ConfigManager
from singletons.logger_singleton import LoggerSingleton

from .models import AuthToken, Comment, Post, User


class ConfigManagerTests(TestCase):
    # Singleton config settings should behave like one shared object.
    def setUp(self):
        self.config = ConfigManager()
        self.config.reset_settings()


    def tearDown(self):
        self.config.reset_settings()


    def test_config_manager_returns_same_instance(self):
        # Both variables should point to the same singleton object.
        config1 = ConfigManager()
        config2 = ConfigManager()

        self.assertIs(config1, config2)
        config1.set_setting('DEFAULT_PAGE_SIZE', 50)
        self.assertEqual(config2.get_setting('DEFAULT_PAGE_SIZE'), 50)


class LoggerSingletonTests(TestCase):
    # The logger singleton should always return the same logger instance.
    def test_logger_singleton_returns_same_logger(self):
        # The project should not create a new logger on every call.
        logger1 = LoggerSingleton().get_logger()
        logger2 = LoggerSingleton().get_logger()

        self.assertIs(logger1, logger2)


class PostFactoryTests(TestCase):
    # Factory tests cover the validation rules used by post creation endpoints.
    def setUp(self):
        # One real author is enough to exercise the factory rules.
        self.user = User.objects.create(username='factoryuser', email='factory@example.com')
        self.user.set_password('SecurePass123!')
        self.user.save()


    def test_factory_creates_image_post_with_required_metadata(self):
        # Image posts should pass when the required metadata is present.
        post = PostFactory.create_post(
            post_type=Post.PostTypes.IMAGE,
            title='Factory Image Post',
            content='Image content',
            metadata={'file_size': '2MB'},
            author=self.user,
        )

        self.assertEqual(post.post_type, Post.PostTypes.IMAGE)
        self.assertEqual(post.metadata['file_size'], '2MB')


    def test_factory_rejects_video_post_without_duration(self):
        # Video posts should fail when required metadata is missing.
        with self.assertRaisesMessage(ValueError, "Video posts require 'duration' in metadata"):
            PostFactory.create_post(
                post_type=Post.PostTypes.VIDEO,
                title='Invalid Video Post',
                content='Video content',
                metadata={},
                author=self.user,
            )


class HomeworkFiveInteractionTests(TestCase):
    # Homework 5 covers likes and comments on protected post endpoints.
    def setUp(self):
        self.client = APIClient()

        # The author owns the post used in the interaction tests.
        self.author = User.objects.create(username='authoruser', email='author@example.com')
        self.author.set_password('SecurePass123!')
        self.author.save()
        self.author_token = AuthToken.objects.create(user=self.author)

        # The second user performs the like and comment actions.
        self.other_user = User.objects.create(username='otheruser', email='other@example.com')
        self.other_user.set_password('SecurePass123!')
        self.other_user.save()
        self.other_token = AuthToken.objects.create(user=self.other_user)

        # This post is reused by the Homework 5 interaction checks.
        self.post = Post.objects.create(
            title='Homework 5 Post',
            content='Testing interactions',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.author,
        )


    def test_like_post_success_and_duplicate_like_error(self):
        # The first like should succeed and the repeated like should be blocked.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')

        first_response = self.client.post(f'/posts/posts/{self.post.id}/like/', secure=True)
        second_response = self.client.post(f'/posts/posts/{self.post.id}/like/', secure=True)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()['error'], 'Post already liked.')


    def test_comment_creation_and_retrieval(self):
        # A created comment should appear in the post comment list.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')

        create_response = self.client.post(
            f'/posts/posts/{self.post.id}/comment/',
            {'text': 'Great post!'},
            format='json',
            secure=True,
        )
        list_response = self.client.get(f'/posts/posts/{self.post.id}/comments/', secure=True)

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()[0]['text'], 'Great post!')


    def test_empty_comment_is_rejected(self):
        # Whitespace-only comments should fail serializer validation.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')

        response = self.client.post(
            f'/posts/posts/{self.post.id}/comment/',
            {'text': '   '},
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Comment text cannot be empty.', response.json()['text'])


class HomeworkEightPrivacyAndRBACTests(TestCase):
    # Homework 8 covers privacy checks and admin-only delete actions.
    def setUp(self):
        self.client = APIClient()

        # user1 owns the posts created in these tests.
        self.user = User.objects.create(username='user1', email='user1@example.com')
        self.user.set_password('SecurePass123!')
        self.user.save()
        self.user_token = AuthToken.objects.create(user=self.user)

        # guest1 is used to verify non-owner and non-admin access.
        self.guest = User.objects.create(
            username='guest1',
            email='guest1@example.com',
            role=User.Roles.GUEST,
        )
        self.guest.set_password('SecurePass123!')
        self.guest.save()
        self.guest_token = AuthToken.objects.create(user=self.guest)

        # admin_1 is used for the admin-only delete checks.
        self.admin = User.objects.create(
            username='admin_1',
            email='admin1@example.com',
            role=User.Roles.ADMIN,
        )
        self.admin.set_password('SecurePass123!')
        self.admin.save()
        self.admin_token = AuthToken.objects.create(user=self.admin)

        # One public and one private post cover the access-control cases.
        self.public_post = Post.objects.create(
            title='Public Post',
            content='Visible post',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            privacy=Post.PrivacyChoices.PUBLIC,
            author=self.user,
        )
        self.private_post = Post.objects.create(
            title='Private Post',
            content='Hidden post',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            privacy=Post.PrivacyChoices.PRIVATE,
            author=self.user,
        )
        # The comment is used for the admin delete comment test.
        self.comment = Comment.objects.create(
            text='Delete this comment',
            author=self.guest,
            post=self.public_post,
        )


    def test_private_post_is_hidden_from_other_users(self):
        # guest1 should not be able to open user1's private post.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.guest_token.key}')

        response = self.client.get(f'/posts/posts/{self.private_post.id}/', secure=True)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'This post is private.')


    def test_private_post_is_visible_to_owner(self):
        # user1 should still be able to open their own private post.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')

        response = self.client.get(f'/posts/posts/{self.private_post.id}/', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['privacy'], Post.PrivacyChoices.PRIVATE)


    def test_feed_only_returns_public_posts(self):
        # The guest feed should hide private posts.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.guest_token.key}')

        response = self.client.get('/feed/?page=1&page_size=10', secure=True)
        titles = [item['title'] for item in response.json()['results']]

        self.assertEqual(response.status_code, 200)
        self.assertIn('Public Post', titles)
        self.assertNotIn('Private Post', titles)


    def test_non_admin_cannot_delete_post(self):
        # Non-admin roles should be blocked from delete endpoints.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.guest_token.key}')

        response = self.client.delete(f'/posts/posts/{self.public_post.id}/', secure=True)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['detail'], 'Admin role required.')


    def test_admin_can_delete_post(self):
        # Admin should be allowed to delete a post successfully.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

        response = self.client.delete(f'/posts/posts/{self.public_post.id}/', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Post deleted successfully.')
        self.assertFalse(Post.objects.filter(id=self.public_post.id).exists())


    def test_admin_can_delete_comment(self):
        # Admin should be allowed to delete a comment successfully.
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')

        response = self.client.delete(f'/posts/comments/{self.comment.id}/', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Comment deleted successfully.')
        self.assertFalse(Comment.objects.filter(id=self.comment.id).exists())


class GoogleLoginTests(TestCase):
    # Google login is tested with mocked token verification.
    def setUp(self):
        # APIClient is enough because token verification is mocked in each test.
        self.client = APIClient()


    @patch('posts.views.verify_oauth2_token')
    def test_google_login_creates_user_and_returns_token(self, mock_verify):
        # A new Google account should create a local user and token.
        mock_verify.return_value = {
            'sub': 'google-user-123',
            'email': 'googleuser@example.com',
        }

        response = self.client.post(
            '/auth/google/login/',
            {'id_token': 'valid-google-token'},
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['message'], 'Authentication successful!')
        self.assertTrue(User.objects.filter(email='googleuser@example.com', google_id='google-user-123').exists())


    @patch('posts.views.verify_oauth2_token')
    def test_google_login_links_existing_user_by_email(self, mock_verify):
        # Existing emails should be linked instead of creating duplicate users.
        user = User.objects.create(username='existinguser', email='existing@example.com')

        mock_verify.return_value = {
            'sub': 'google-user-456',
            'email': 'existing@example.com',
        }

        response = self.client.post(
            '/auth/google/login/',
            {'id_token': 'valid-google-token'},
            format='json',
            secure=True,
        )

        user.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.google_id, 'google-user-456')


    @patch('posts.views.verify_oauth2_token')
    def test_google_login_rejects_invalid_token(self, mock_verify):
        # Invalid Google tokens should return a clean client error.
        mock_verify.side_effect = ValueError('Invalid token')

        response = self.client.post(
            '/auth/google/login/',
            {'id_token': 'bad-token'},
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid or expired Google token.')


class HomeworkSevenFeedTests(TestCase):
    # Homework 7 focuses on feed order and pagination behavior.
    def setUp(self):
        self.client = APIClient()
        self.config = ConfigManager()
        self.config.reset_settings()
        # Clear cached feed data so each test starts from a known state.
        cache.clear()

        # One authenticated user owns the sample feed posts.
        self.user = User.objects.create(username='feeduser', email='feed@example.com')
        self.user.set_password('SecurePass123!')
        self.user.save()
        self.token = AuthToken.objects.create(user=self.user)

        # Three posts are enough to verify sorting and two-page pagination.
        self.oldest_post = Post.objects.create(
            title='Oldest Post',
            content='Old content',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.user,
        )
        self.middle_post = Post.objects.create(
            title='Middle Post',
            content='Middle content',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.user,
        )
        self.newest_post = Post.objects.create(
            title='Newest Post',
            content='Newest content',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.user,
        )

        # Adjust timestamps so the expected feed order is stable in the tests.
        now = timezone.now()
        Post.objects.filter(id=self.oldest_post.id).update(created_at=now - timedelta(days=2))
        Post.objects.filter(id=self.middle_post.id).update(created_at=now - timedelta(days=1))
        Post.objects.filter(id=self.newest_post.id).update(created_at=now)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')


    def tearDown(self):
        # Reset shared cache and config values after each feed test.
        cache.clear()
        self.config.reset_settings()


    def test_feed_returns_posts_sorted_by_date_with_pagination(self):
        # Page 1 should return the newest posts first.
        response = self.client.get('/feed/?page=1&page_size=2', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page'], 1)
        self.assertEqual(response.json()['page_size'], 2)
        self.assertEqual(response.json()['total_pages'], 2)
        self.assertEqual(response.json()['total_posts'], 3)
        self.assertEqual(response.json()['results'][0]['title'], 'Newest Post')
        self.assertEqual(response.json()['results'][1]['title'], 'Middle Post')


    def test_feed_second_page_returns_remaining_posts(self):
        # Page 2 should return the remaining older post.
        response = self.client.get('/feed/?page=2&page_size=2', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)
        self.assertEqual(response.json()['results'][0]['title'], 'Oldest Post')


    def test_feed_rejects_non_existent_page(self):
        # Requests for pages outside the paginator range should fail cleanly.
        response = self.client.get('/feed/?page=3&page_size=2', secure=True)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'Page not found.')


    def test_feed_rejects_invalid_page_values(self):
        # Zero or negative pagination values should be rejected.
        response = self.client.get('/feed/?page=0&page_size=0', secure=True)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Page and page_size must be positive integers.')


class HomeworkNinePerformanceTests(TestCase):
    # Homework 9 checks pagination defaults, cache reuse, and cache invalidation.
    def setUp(self):
        self.client = APIClient()
        self.config = ConfigManager()
        self.config.reset_settings()
        # Start each performance test with an empty feed cache.
        cache.clear()

        # One authenticated user owns the sample feed posts.
        self.user = User.objects.create(username='perfuser', email='perf@example.com')
        self.user.set_password('SecurePass123!')
        self.user.save()
        self.token = AuthToken.objects.create(user=self.user)

        # Three posts are enough to test page splitting and cache refresh.
        self.oldest_post = Post.objects.create(
            title='Performance Oldest Post',
            content='Old content',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.user,
        )
        self.middle_post = Post.objects.create(
            title='Performance Middle Post',
            content='Middle content',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.user,
        )
        self.newest_post = Post.objects.create(
            title='Performance Newest Post',
            content='Newest content',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.user,
        )

        # Stable timestamps keep the expected page results predictable.
        now = timezone.now()
        Post.objects.filter(id=self.oldest_post.id).update(created_at=now - timedelta(days=2))
        Post.objects.filter(id=self.middle_post.id).update(created_at=now - timedelta(days=1))
        Post.objects.filter(id=self.newest_post.id).update(created_at=now)

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')


    def tearDown(self):
        # Shared cache and config changes should not leak across tests.
        cache.clear()
        self.config.reset_settings()


    def test_feed_uses_default_page_size_from_config_manager(self):
        # The feed should read its fallback page size from ConfigManager.
        self.config.set_setting('DEFAULT_PAGE_SIZE', 2)

        response = self.client.get('/feed/', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['page_size'], 2)
        self.assertEqual(len(response.json()['results']), 2)


    def test_feed_cache_hits_on_repeated_request(self):
        # The second request for the same page should reuse cached data.
        with self.assertLogs('connectly_logger', level='INFO') as first_logs:
            first_response = self.client.get('/feed/?page=1&page_size=2', secure=True)

        with self.assertLogs('connectly_logger', level='INFO') as second_logs:
            second_response = self.client.get('/feed/?page=1&page_size=2', secure=True)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.json(), second_response.json())
        self.assertTrue(any('Feed cache miss' in message for message in first_logs.output))
        self.assertTrue(any('Feed cache hit' in message for message in second_logs.output))


    def test_feed_cache_is_repopulated_after_cache_clear(self):
        # Clearing the cache should force the next request to rebuild the feed.
        self.client.get('/feed/?page=1&page_size=2', secure=True)
        cache.clear()

        with self.assertLogs('connectly_logger', level='INFO') as logs:
            response = self.client.get('/feed/?page=1&page_size=2', secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('Feed cache miss' in message for message in logs.output))


    def test_creating_post_invalidates_cached_feed(self):
        # Creating a new public post should invalidate and refresh the cached feed.
        self.client.get('/feed/?page=1&page_size=2', secure=True)

        create_response = self.client.post(
            '/posts/posts/create/',
            {
                'title': 'Performance Latest Post',
                'content': 'Newest cached content',
                'post_type': 'text',
                'metadata': {},
                'privacy': 'public',
            },
            format='json',
            secure=True,
        )

        with self.assertLogs('connectly_logger', level='INFO') as logs:
            feed_response = self.client.get('/feed/?page=1&page_size=2', secure=True)

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(feed_response.status_code, 200)
        self.assertEqual(feed_response.json()['results'][0]['title'], 'Performance Latest Post')
        self.assertTrue(any('Feed cache miss' in message for message in logs.output))
