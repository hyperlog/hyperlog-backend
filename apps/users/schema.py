import graphene
from graphene_django import DjangoObjectType


class GithubProfileType(DjangoObjectType):
    pass


class UserType(DjangoObjectType):
    id: graphene.ID(required=True)
    name: graphene.String(required=True)
    email: graphene.String(required=True)
    username: graphene.String(required=True)
    github: graphene.Field(GithubProfileType)
