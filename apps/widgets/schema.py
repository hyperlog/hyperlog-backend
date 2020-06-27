import graphene
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required

from apps.base.utils import create_model_object
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


class Mutation(graphene.ObjectType):
    create_widget = CreateWidget.Field()
