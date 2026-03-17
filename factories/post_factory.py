from posts.models import Post


class PostFactory:
    @staticmethod
    def create_post(post_type, title, content='', metadata=None, author=None):
        metadata = metadata or {}

        if not isinstance(metadata, dict):
            raise ValueError('Metadata must be a JSON object')

        if post_type not in dict(Post.PostTypes.choices):
            raise ValueError('Invalid post type')

        if post_type == Post.PostTypes.IMAGE and 'file_size' not in metadata:
            raise ValueError("Image posts require 'file_size' in metadata")
        if post_type == Post.PostTypes.VIDEO and 'duration' not in metadata:
            raise ValueError("Video posts require 'duration' in metadata")
        if author is None:
            raise ValueError('Author is required')

        return Post.objects.create(
            title=title,
            content=content,
            post_type=post_type,
            metadata=metadata,
            author=author,
        )
