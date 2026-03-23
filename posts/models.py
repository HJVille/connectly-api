import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import models


def unusable_password():
    # Google-only accounts still need a stored password value.
    return make_password(None)


def generate_token_key():
    # Match the token length used by the custom token login flow.
    return secrets.token_hex(20)


class User(models.Model):
    # The project uses a custom user model for local login, Google login, and RBAC.
    class Roles(models.TextChoices):
        ADMIN = 'Admin', 'Admin'
        USER = 'User', 'User'
        GUEST = 'Guest', 'Guest'

    # Basic identity fields used by the CRUD and authentication endpoints.
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    # Google OAuth stores the Google account ID so later logins can reuse the same user.
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # Passwords are stored as hashes, not plain text.
    password = models.CharField(max_length=128, default=unusable_password)
    # Homework 8 permissions rely on Admin, User, and Guest role values.
    role = models.CharField(max_length=10, choices=Roles.choices, default=Roles.USER)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return self.username


    def set_password(self, raw_password):
        # Local signup and login use hashed passwords.
        self.password = make_password(raw_password)


    def check_password(self, raw_password):
        # Compare submitted login credentials against the stored hash.
        return check_password(raw_password, self.password)


    @property
    def is_authenticated(self):
        # DRF permission checks rely on this property.
        return True


class Post(models.Model):
    # Posts support factory validation, feed display, and Homework 8 privacy checks.
    class PostTypes(models.TextChoices):
        TEXT = 'text', 'Text'
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'

    # Privacy values are checked in the post detail view and filtered out of the feed.
    class PrivacyChoices(models.TextChoices):
        PUBLIC = 'public', 'Public'
        PRIVATE = 'private', 'Private'

    # Title and content are returned in the CRUD endpoints and feed responses.
    title = models.CharField(max_length=255, default='Untitled Post')
    content = models.TextField(blank=True)
    # The factory uses post_type to validate metadata requirements.
    post_type = models.CharField(
        max_length=10,
        choices=PostTypes.choices,
        default=PostTypes.TEXT,
    )
    # Metadata stores extra fields for image and video posts.
    metadata = models.JSONField(blank=True, default=dict)
    # Public posts appear in the feed, while private posts stay owner-only.
    privacy = models.CharField(
        max_length=10,
        choices=PrivacyChoices.choices,
        default=PrivacyChoices.PUBLIC,
    )
    # Feed, likes, and comments all relate back to the post author.
    author = models.ForeignKey(User, related_name='posts', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.post_type} post '{self.title}' by {self.author.username}"


class Comment(models.Model):
    # Comments are tied to a post and the user who submitted them.
    text = models.TextField()
    author = models.ForeignKey(User, related_name='comments', on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Comment by {self.author.username} on Post {self.post.id}"


class Like(models.Model):
    # Likes connect one user to one post for Homework 5 interactions.
    user = models.ForeignKey(User, related_name='likes', on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='likes', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Duplicate likes are blocked at the database level.
        constraints = [
            models.UniqueConstraint(fields=['user', 'post'], name='unique_user_post_like'),
        ]


    def __str__(self):
        return f"{self.user.username} likes Post {self.post.id}"


class AuthToken(models.Model):
    # Custom token records back the protected endpoints used in the homework tests.
    key = models.CharField(max_length=40, unique=True, default=generate_token_key)
    user = models.OneToOneField(User, related_name='auth_token', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Token for {self.user.username}"
