import graphene


class GenericResultMutation(graphene.Mutation):
    """A simple success, errors type for mutation/subscription responses"""

    success = graphene.Boolean(required=True)
    errors = graphene.List(graphene.NonNull(graphene.String))

    class Meta:
        abstract = True
