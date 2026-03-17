import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import models


def unusable_password():
    return make_password(None)


def generate_token_key():
    return secrets.token_hex(20)

class User(models.Model):
    class Roles(models.TextChoices):
        ADMIN = 'Admin', 'Admin'
        USER = 'User', 'User'

    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128, default=unusable_password)
    role = models.CharField(max_length=10, choices=Roles.choices, default=Roles.USER)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return self.username


    def set_password(self, raw_password):
        self.password = make_password(raw_password)


    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


    @property
    def is_authenticated(self):
        return True


class Post(models.Model):
    content = models.TextField()
    author = models.ForeignKey(User, related_name='posts', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Post by {self.author.username} at {self.created_at}"


class Comment(models.Model):
    text = models.TextField()
    author = models.ForeignKey(User, related_name='comments', on_delete=models.CASCADE)
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Comment by {self.author.username} on Post {self.post.id}"


class AuthToken(models.Model):
    key = models.CharField(max_length=40, unique=True, default=generate_token_key)
    user = models.OneToOneField(User, related_name='auth_token', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"Token for {self.user.username}"
