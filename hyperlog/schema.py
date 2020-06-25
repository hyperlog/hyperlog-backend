import graphene

import apps.users.schema
import apps.profiles.schema
import apps.widgets.schema


class Query(
    apps.profiles.schema.Query, apps.users.schema.Query, graphene.ObjectType,
):
    pass


class Mutation(
    apps.profiles.schema.Mutation,
    apps.users.schema.Mutation,
    apps.widgets.schema.Mutation,
    graphene.ObjectType,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
