from posts.models import Post


class PostFactory:
    @staticmethod
    def create_post(
        post_type,
        title,
        content='',
        metadata=None,
        author=None,
        privacy=Post.PrivacyChoices.PUBLIC,
    ):
        # Centralize post validation so both post endpoints follow the same rules.
        metadata = metadata or {}

        # Metadata is stored in a JSONField, so the payload must stay object-shaped.
        if not isinstance(metadata, dict):
            raise ValueError('Metadata must be a JSON object')

        # Only the supported post types from the model can be created.
        if post_type not in dict(Post.PostTypes.choices):
            raise ValueError('Invalid post type')

        # Image and video posts each require their own metadata field.
        if post_type == Post.PostTypes.IMAGE and 'file_size' not in metadata:
            raise ValueError("Image posts require 'file_size' in metadata")
        if post_type == Post.PostTypes.VIDEO and 'duration' not in metadata:
            raise ValueError("Video posts require 'duration' in metadata")
        # Posts cannot be created without a linked author.
        if author is None:
            raise ValueError('Author is required')
        # Homework 8 privacy values are validated here before save.
        if privacy not in dict(Post.PrivacyChoices.choices):
            raise ValueError('Invalid privacy setting')

        return Post.objects.create(
            title=title,
            content=content,
            post_type=post_type,
            metadata=metadata,
            privacy=privacy,
            author=author,
        )
