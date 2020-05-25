import graphene
import graphql_jwt

import apps.users.schema


class Query(apps.users.schema.Query, graphene.ObjectType):
    pass


class Mutation(apps.users.schema.Mutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
