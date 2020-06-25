import graphene
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required

from django.contrib.auth import get_user_model

from apps.base.utils import create_model_object, get_model_object
from apps.widgets.models import Widget


class WidgetType(DjangoObjectType):
    class Meta:
        model = Widget


class CreateWidget(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)
    widget = graphene.Field(WidgetType)

    @login_required
    def mutate(self, info):
        user = info.context.user
        create_widget = create_model_object(Widget, user=user)

        return CreateWidget(
            success=create_widget.success,
            errors=create_widget.errors,
            widget=create_widget.object,
        )


class IncrementImpressions(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)
    widget = graphene.Field(WidgetType)

    class Arguments:
        code = graphene.UUID(required=True)

    def mutate(self, info, code):
        User = get_user_model()
        get_user = get_model_object(User, uuid=code)

        if get_user.success:
            user = get_user.object
            widget = getattr(user, "widget", None)
            if widget is not None:
                widget.impressions += 1
                widget.full_clean()
                widget.save()
                return IncrementImpressions(success=True, widget=widget)
            else:
                error = "Widget not initialized"
                return IncrementImpressions(success=False, errors=[error])
        else:
            return IncrementImpressions(success=False, errors=get_user.errors)


class IncrementClicks(graphene.Mutation):
    success = graphene.Boolean()
    errors = graphene.List(graphene.String)
    widget = graphene.Field(WidgetType)

    class Arguments:
        code = graphene.UUID(required=True)

    def mutate(self, info, code):
        User = get_user_model()
        get_user = get_model_object(User, uuid=code)

        if get_user.success:
            user = get_user.object
            widget = getattr(user, "widget", None)
            if widget is not None:
                widget.clicks += 1
                widget.full_clean()
                widget.save()
                return IncrementClicks(success=True, widget=widget)
            else:
                error = "Widget not initialized"
                return IncrementClicks(success=False, errors=[error])
        else:
            return IncrementClicks(success=False, errors=get_user.errors)


class Mutation(graphene.ObjectType):
    create_widget = CreateWidget.Field()
    increment_impressions = IncrementImpressions.Field()
    increment_clicks = IncrementClicks.Field()
