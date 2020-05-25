import graphene
from graphene_django import DjangoObjectType

from apps.profiles.models import BaseProfileModel, EmailAddress


class ProfileType(DjangoObjectType):
    class Meta:
        model = BaseProfileModel
        exclude = ("_provider", "emails")

    provider = graphene.String()
    emails = graphene.List(graphene.String)

    def resolve_provider(self, info):
        return self._provide

    def resolve_emails(self, info):
        return [each.email for each in self.emails]


class EmailAddressType(DjangoObjectType):
    class Meta:
        model = EmailAddress


class Query(graphene.ObjectType):
    # TODO
    pass


class Mutation(graphene.ObjectType):
    # TODO
    pass
