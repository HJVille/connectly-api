from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from factories.post_factory import PostFactory
from singletons.config_manager import ConfigManager
from singletons.logger_singleton import LoggerSingleton

from .models import AuthToken, Post, User


class ConfigManagerTests(TestCase):
    def test_config_manager_returns_same_instance(self):
        config1 = ConfigManager()
        config2 = ConfigManager()

        self.assertIs(config1, config2)
        config1.set_setting('DEFAULT_PAGE_SIZE', 50)
        self.assertEqual(config2.get_setting('DEFAULT_PAGE_SIZE'), 50)


class LoggerSingletonTests(TestCase):
    def test_logger_singleton_returns_same_logger(self):
        logger1 = LoggerSingleton().get_logger()
        logger2 = LoggerSingleton().get_logger()

        self.assertIs(logger1, logger2)


class PostFactoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='factoryuser', email='factory@example.com')
        self.user.set_password('SecurePass123!')
        self.user.save()


    def test_factory_creates_image_post_with_required_metadata(self):
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
        with self.assertRaisesMessage(ValueError, "Video posts require 'duration' in metadata"):
            PostFactory.create_post(
                post_type=Post.PostTypes.VIDEO,
                title='Invalid Video Post',
                content='Video content',
                metadata={},
                author=self.user,
            )


class HomeworkFiveInteractionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.author = User.objects.create(username='authoruser', email='author@example.com')
        self.author.set_password('SecurePass123!')
        self.author.save()
        self.author_token = AuthToken.objects.create(user=self.author)

        self.other_user = User.objects.create(username='otheruser', email='other@example.com')
        self.other_user.set_password('SecurePass123!')
        self.other_user.save()
        self.other_token = AuthToken.objects.create(user=self.other_user)

        self.post = Post.objects.create(
            title='Homework 5 Post',
            content='Testing interactions',
            post_type=Post.PostTypes.TEXT,
            metadata={},
            author=self.author,
        )


    def test_like_post_success_and_duplicate_like_error(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')

        first_response = self.client.post(f'/posts/posts/{self.post.id}/like/', secure=True)
        second_response = self.client.post(f'/posts/posts/{self.post.id}/like/', secure=True)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()['error'], 'Post already liked.')


    def test_comment_creation_and_retrieval(self):
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
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')

        response = self.client.post(
            f'/posts/posts/{self.post.id}/comment/',
            {'text': '   '},
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Comment text cannot be empty.', response.json()['text'])


class GoogleLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()


    @patch('posts.views.verify_oauth2_token')
    def test_google_login_creates_user_and_returns_token(self, mock_verify):
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
        mock_verify.side_effect = ValueError('Invalid token')

        response = self.client.post(
            '/auth/google/login/',
            {'id_token': 'bad-token'},
            format='json',
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Invalid or expired Google token.')
