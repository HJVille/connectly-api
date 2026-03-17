from django.test import TestCase

from factories.post_factory import PostFactory
from singletons.config_manager import ConfigManager
from singletons.logger_singleton import LoggerSingleton

from .models import Post, User


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
