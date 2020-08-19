import graphene

import apps.users.schema
import apps.profiles.schema
import apps.widgets.schema


class Query(apps.profiles.schema.Query, apps.users.schema.Query):
    pass


class Mutation(
    apps.profiles.schema.Mutation,
    apps.users.schema.Mutation,
    apps.widgets.schema.Mutation,
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
