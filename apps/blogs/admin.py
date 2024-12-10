from django.contrib import admin

from apps.blogs.models import Post, Tag


admin.site.register(Post)
admin.site.register(Tag)
