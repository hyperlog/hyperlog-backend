import graphene


class GenericResultMutation(graphene.Mutation):
    """A simple success, errors type for mutation/subscription responses"""

    success = graphene.Boolean(required=True)
    errors = graphene.List(graphene.String(required=True))

    class Meta:
        abstract = True
