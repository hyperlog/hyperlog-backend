import graphene
from graphene_django import DjangoObjectType

from apps.profiles.models import BaseProfileModel, EmailAddress, GithubProfile


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
    profiles = graphene.List(ProfileType, provider=graphene.String())
    profile = graphene.Field(ProfileType, id=graphene.Int(required=True))
    profile_emails = graphene.List(EmailAddressType)

    def resolve_profiles(self, info, **kwargs):
        """
        Returns all profiles with given provider or simply all profiles if it
        is not mentioned
        """
        if kwargs.get("provider"):
            return BaseProfileModel.objects.filter(
                _provider=kwargs.get("provider")
            )
        return BaseProfileModel.objects.all()

    def resolve_profile(self, info, **kwargs):
        return BaseProfileModel.get(id=kwargs.get("id"))

    def resolve_profile_emails(self, info, **kwargs):
        return EmailAddress.objects.all()


class CreateGithubProfile(graphene.Mutation):
    profile = graphene.Field(ProfileType)

    class Arguments:
        username = graphene.String(required=True)
        access_token = graphene.String(required=True)
        emails = graphene.List(graphene.String, required=True)

    def mutate(self, info, username, access_token, emails):
        user = info.context.user
        new_profile = GithubProfile.objects.create(
            username=username, access_token=access_token, user=user
        )

        for email in emails:
            EmailAddress.objects.create(email=email, profile=new_profile)

        return CreateGithubProfile(profile=new_profile)


class Mutation(graphene.ObjectType):
    create_github_profile = CreateGithubProfile.Field()
