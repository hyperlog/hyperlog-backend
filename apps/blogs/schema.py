import graphene
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from graphql_jwt.decorators import login_required

from django.core.paginator import Paginator

from .models import Post, Tag


VALID_SORTING_CONDITIONS = [
    "published_at",
    "title",
    "slug",
    "reading_time",
    "author__username",
    "author__first_name",
    "author__last_name",
]


VALID_SORTING_CONDITIONS_FOR_OWNER = [
    "created_at",
    "updated_at",
    "published_at",
    "title",
    "slug",
    "reading_time",
    "visibility",
]


class BlogPostType(DjangoObjectType):
    class Meta:
        model = Post


class BlogTagType(DjangoObjectType):
    class Meta:
        model = Tag


class PaginatedBlogPostsType(graphene.ObjectType):
    posts = graphene.List(BlogPostType, required=True)
    count = graphene.Int(required=True)


class PaginatedBlogTagsType(graphene.ObjectType):
    tags = graphene.List(BlogTagType, required=True)
    count = graphene.Int(required=True)


class Query(graphene.ObjectType):
    blog_post_by_id = graphene.Field(
        BlogPostType, uuid=graphene.UUID(required=True)
    )
    public_blog_posts = graphene.Field(
        PaginatedBlogPostsType,
        page=graphene.Int(required=True),
        on_each_page=graphene.Int(required=False, default_value=10),
        sort_by=graphene.List(
            graphene.String,
            required=False,
            default_value=["-published_at"],
            description=(
                "A list of ordering conditions as strings. Could be prefixed "
                "with a '-' (minus sign) for descending order. Valid sorting "
                "conditions are: "
                f"{', '.join(x for x in VALID_SORTING_CONDITIONS)}"
            ),
        ),
        author=graphene.String(
            required=False, description="Username of author to be queried",
        ),
        tags=graphene.List(
            graphene.Int,
            required=False,
            description="A list of tag ids to filter by (union-type filter)",
        ),
        tag_names=graphene.List(
            graphene.String,
            required=False,
            description="A list of tag names to filter by (union-type filter)",
        ),
    )
    my_blog_posts = graphene.Field(
        PaginatedBlogPostsType,
        page=graphene.Int(required=True),
        on_each_page=graphene.Int(required=False, default_value=10),
        sort_by=graphene.List(
            graphene.String,
            required=False,
            default_value=["-updated_at"],
            description=(
                "A list of ordering conditions as strings. Could be prefixed "
                "with a '-' (minus sign) for descending order. Valid sorting "
                "conditions are: "
                f"{', '.join(x for x in VALID_SORTING_CONDITIONS_FOR_OWNER)}"
            ),
        ),
        tags=graphene.List(
            graphene.Int,
            required=False,
            description="A list of tag ids to filter by (union-type filter)",
        ),
        tag_names=graphene.List(
            graphene.String,
            required=False,
            description="A list of tag names to filter by (union-type filter)",
        ),
    )
    blog_tags = graphene.Field(
        PaginatedBlogTagsType,
        page=graphene.Int(required=True),
        on_each_page=graphene.Int(required=False, default_value=10),
    )

    @login_required
    def resolve_blog_post_by_id(self, info, uuid):
        """Query to fetch blog post by UUID"""
        user = info.context.user

        try:
            blog = user.blog_posts.get(uuid=uuid)
        except Post.DoesNotExist:
            raise GraphQLError("Blog post not found")

        return blog

    def resolve_public_blog_posts(self, info, sort_by, **kwargs):
        """
        Query to get blog posts with/without filters and sorting conditions

        `sort_by` - should be a list of strings among the
        VALID_SORTING_CONDITIONS with a '-' (minus sign) prefixed for
        descending order.

        The tag id, and tag name filtering is union-type internally, and
        intersection-type externally. Only recommended to use one of them
        at a time
        """
        # Sanity check sort conditions
        for each in sort_by:
            if each[:1] == "-":
                each = each[1:]

            assert (
                each in VALID_SORTING_CONDITIONS
            ), f"Invalid sort condition {each}"

        author, tags, tag_names = (
            kwargs.get("author"),
            kwargs.get("tags"),
            kwargs.get("tag_names"),
        )
        filter_dict = {}
        if author:
            filter_dict["author__username__iexact"] = author
        if tags:
            filter_dict["tags__in"] = tags
        if tag_names:
            filter_dict["tags__name__in"] = tag_names

        posts = (
            Post.objects.filter(visibility=Post.PUBLIC, **filter_dict)
            .distinct()
            .order_by(*sort_by)
        )

        on_each_page, page = kwargs.get("on_each_page"), kwargs.get("page")

        pag = Paginator(posts, on_each_page)

        return PaginatedBlogPostsType(
            posts=pag.page(page).object_list, count=pag.count
        )

    @login_required
    def resolve_my_blog_posts(self, info, sort_by, **kwargs):
        """
        Query to retrieve all posts written by user

        `sort_by` - sort conditions as in when retrieving all blog posts.
        As per VALID_SORTING_CONDITIONS_FOR_OWNER
        """
        # Sanity check sort conditions
        for each in sort_by:
            if each[:1] == "-":
                each = each[1:]

            assert (
                each in VALID_SORTING_CONDITIONS_FOR_OWNER
            ), f"Invalid sort condition {each}"

        user = info.context.user

        tags, tag_names = kwargs.get("tags"), kwargs.get("tag_names")

        filter_dict = {}
        if tags:
            filter_dict["tags__in"] = tags
        if tag_names:
            filter_dict["tags__name__in"] = tag_names

        posts = (
            user.blog_posts.filter(**filter_dict).distinct().order_by(*sort_by)
        )

        on_each_page, page = kwargs.get("on_each_page"), kwargs.get("page")

        pag = Paginator(posts, on_each_page)

        return PaginatedBlogPostsType(
            posts=pag.page(page).object_list, count=pag.count
        )

    def resolve_blog_tags(self, info, **kwargs):
        tags = Tag.objects.all()

        on_each_page, page = kwargs.get("on_each_page"), kwargs.get("page")
        pag = Paginator(tags, on_each_page)

        return PaginatedBlogTagsType(
            tags=pag.page(page).object_list, count=pag.count
        )


class CreateBlogPost(graphene.Mutation):
    blog_post = graphene.Field(BlogPostType, required=True)

    class Arguments:
        slug = graphene.String(required=True)
        title = graphene.String(required=True)
        subtitle = graphene.String(required=True)
        content = graphene.String(required=True)
        feature_image = graphene.String(required=True)
        url = graphene.String(required=True)

    @login_required
    def mutate(self, info, **kwargs):
        pass


class PublishBlogPost(graphene.Mutation):
    blog_post = graphene.Field(BlogPostType, required=True)

    class Arguments:
        uuid = graphene.UUID(required=True)

    @login_required
    def mutate(self, info, uuid):
        user = info.context.user

        try:
            blog = user.blog_posts.get(uuid=uuid)
        except Post.DoesNotExist:
            raise GraphQLError("Blog post not found")

        blog.visibility = Post.PUBLIC
        blog.full_clean()
        blog.save()

        return PublishBlogPost(blog_post=blog)


class Mutation(graphene.ObjectType):
    create_blog_post = CreateBlogPost.Field()
    publish_blog_post = PublishBlogPost.Field()
