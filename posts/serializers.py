from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, Post, Comment


class UserSerializer(serializers.ModelSerializer):
    # Keep passwords write-only while still allowing role assignment on signup.
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'password': {'write_only': True},
        }


    def validate_password(self, value):
        # Reuse Django's built-in password validation rules.
        validate_password(value)
        return value


    def create(self, validated_data):
        # Store hashed passwords in the custom user model.
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    # Local login accepts username and password from the custom user table.
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


    def validate(self, attrs):
        # Authenticate against the custom user model instead of Django auth.
        try:
            user = User.objects.get(username=attrs['username'])
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("Invalid credentials.") from exc

        if not user.check_password(attrs['password']):
            raise serializers.ValidationError("Invalid credentials.")

        attrs['user'] = user
        return attrs


class GoogleLoginSerializer(serializers.Serializer):
    # Google login only needs the Google ID token from the client.
    id_token = serializers.CharField()


class PostDetailSerializer(serializers.ModelSerializer):
    # Detail responses include privacy for Homework 8 owner/private checks.
    class Meta:
        model = Post
        fields = ['id', 'title', 'content', 'post_type', 'metadata', 'privacy', 'author', 'created_at']


class PostSerializer(serializers.ModelSerializer):
    # Feed and list responses include readable comments for interaction context.
    comments = serializers.StringRelatedField(many=True, read_only=True)


    class Meta:
        model = Post
        fields = ['id', 'title', 'content', 'post_type', 'metadata', 'privacy', 'author', 'created_at', 'comments']


class CommentSerializer(serializers.ModelSerializer):
    # Allow blank input first so the custom validator can return the final message.
    text = serializers.CharField(allow_blank=True)

    class Meta:
        model = Comment
        fields = ['id', 'text', 'author', 'post', 'created_at']


    def validate_text(self, value):
        # Reject comments made of only spaces.
        if not value.strip():
            raise serializers.ValidationError("Comment text cannot be empty.")
        return value


    def validate_post(self, value):
        # Comments must point to a real post record.
        if not Post.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Post not found.")
        return value


    def validate_author(self, value):
        # Comments must point to a real author record.
        if not User.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Author not found.")
        return value
