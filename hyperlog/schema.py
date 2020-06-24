import graphene

import apps.users.schema
import apps.profiles.schema
import apps.membership.schema


class Query(
    apps.profiles.schema.Query, apps.users.schema.Query, graphene.ObjectType,
):
    pass


class Mutation(
    apps.membership.schema.Mutation,
    apps.profiles.schema.Mutation,
    apps.users.schema.Mutation,
    graphene.ObjectType,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
