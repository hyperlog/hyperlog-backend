import logging

import graphene
import phonenumbers
import requests
from graphene_django import DjangoObjectType
from graphql import GraphQLError
from graphql_jwt.decorators import staff_member_required, login_required

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction

from apps.profiles.models import (
    BaseProfileModel,
    EmailAddress,
    Notification,
    OutsiderMessage,
    ProfileAnalysis,
    StackOverflowProfile,
    ContactInfo,
    Project,
    Repo,
)
from apps.base.schema import GenericResultMutation
from apps.base.utils import (
    create_model_object,
    full_clean_and_save,
    get_error_message,
    get_model_object,
)
from apps.profiles.utils import (
    stack_overflow_get_user_data,
    trigger_analysis,
    get_or_create_repo_from_github,
    get_project_slug_by_name,
)

STACK_OVERFLOW_TOKEN_URL = "https://stackoverflow.com/oauth/access_token/json"
STACK_OVERFLOW_CLIENT_ID = settings.STACK_OVERFLOW_CLIENT_ID
STACK_OVERFLOW_CLIENT_SECRET = settings.STACK_OVERFLOW_CLIENT_SECRET
STACK_OVERFLOW_REDIRECT_URI = settings.STACK_OVERFLOW_REDIRECT_URI


logger = logging.getLogger(__name__)


class ProfileType(DjangoObjectType):
    class Meta:
        model = BaseProfileModel
        exclude = ("_provider",)

    provider = graphene.String()
    emails = graphene.List(graphene.String)

    def resolve_provider(self, info):
        return self._provider

    def resolve_emails(self, info):
        return [each.email for each in self.emails.all()]


class EmailAddressType(DjangoObjectType):
    class Meta:
        model = EmailAddress


class NotificationType(DjangoObjectType):
    class Meta:
        model = Notification


class StackOverflowProfileType(DjangoObjectType):
    class Meta:
        model = StackOverflowProfile


class OutsiderMessageType(DjangoObjectType):
    class Meta:
        model = OutsiderMessage


class PaginatedOutsiderMessagesType(graphene.ObjectType):
    messages = graphene.List(OutsiderMessageType, required=True)
    count = graphene.Int(required=True)
    pages = graphene.Int(required=True)


class ContactInfoType(DjangoObjectType):
    class Meta:
        model = ContactInfo


class RepoType(DjangoObjectType):
    class Meta:
        model = Repo


class ProjectType(DjangoObjectType):
    class Meta:
        model = Project


class Query(graphene.ObjectType):
    profile = graphene.Field(ProfileType, id=graphene.Int(required=True))

    notification = graphene.Field(
        NotificationType, id=graphene.Int(required=True)
    )
    notifications_count = graphene.Int(conditions=graphene.JSONString())

    outsider_messages = graphene.Field(
        PaginatedOutsiderMessagesType,
        page=graphene.Int(required=True),
        on_each_page=graphene.Int(default_value=10),
        order_by=graphene.List(graphene.String, default_value=["-time"]),
        is_archived=graphene.Boolean(),
    )

    projects = graphene.Field(graphene.List(ProjectType, required=True))

    def resolve_notification(self, info, **kwargs):
        return Notification.objects.get(id=kwargs.get("id"))

    def resolve_notifications_count(self, info, **kwargs):
        conditions = kwargs.get("conditions")
        if conditions:
            return Notification.objects.filter(**conditions).count()
        else:
            return Notification.objects.count()

    @staff_member_required
    def resolve_profile(self, info, **kwargs):
        return BaseProfileModel.objects.get(id=kwargs.get("id"))

    @login_required
    def resolve_outsider_messages(
        self, info, page, on_each_page, order_by, **filters
    ):
        user = info.context.user
        messages = user.outsider_messages.filter(**filters).order_by(*order_by)

        pag = Paginator(messages, on_each_page)
        return PaginatedOutsiderMessagesType(
            messages=pag.page(page).object_list,
            count=pag.count,
            pages=pag.num_pages,
        )

    @login_required
    def resolve_projects(self, info):
        user = info.context.user

        return user.projects.all()


class DeleteGithubProfile(GenericResultMutation):
    @login_required
    def mutate(self, info, **kwargs):
        user = info.context.user

        try:
            profile = user.profiles.get(_provider="github")
        except BaseProfileModel.DoesNotExist:
            errors = ["GitHub account is not associated."]
            return DeleteGithubProfile(success=False, errors=errors)

        profile.delete()
        return DeleteGithubProfile(success=True)


class CreateNotification(GenericResultMutation):
    notification = graphene.Field(NotificationType)

    class Arguments:
        user_id = graphene.UUID(required=True)
        heading = graphene.String(required=True)
        sub = graphene.String(required=True)
        read = graphene.Boolean()
        priority = graphene.Int()

    def mutate(self, info, user_id, **kwargs):
        # try to get the user
        user_result = get_model_object(get_user_model(), id=user_id)

        if user_result.success:
            user = user_result.object
        else:
            # User could not be found
            return CreateNotification(success=False, errors=user_result.errors)

        # validate and create notification object
        result = create_model_object(Notification, user=user, **kwargs)
        return CreateNotification(
            success=result.success,
            notification=result.object,
            errors=result.errors if result.success is False else None,
        )


class MarkNotificationAsRead(GenericResultMutation):
    class Arguments:
        id = graphene.Int(required=True)

    def mutate(self, info, id):
        get_notification = get_model_object(Notification, id=id)

        if get_notification.success:
            notification = get_notification.object
            notification.read = True
            notification.save()
            return MarkNotificationAsRead(success=True)
        else:
            return MarkNotificationAsRead(
                success=get_notification.success,
                errors=get_notification.errors,
            )


class SelectRepos(GenericResultMutation):
    """Mutation to select GitHub repos and trigger analysis"""

    class Arguments:
        repos = graphene.NonNull(
            graphene.List(graphene.NonNull(graphene.String))
        )

    @login_required
    def mutate(self, info, repos):
        user = info.context.user

        try:
            gh_profile = user.profiles.get(_provider="github")
        except BaseProfileModel.DoesNotExist:
            raise GraphQLError("GitHub Profile isn't connected!")

        for repo in repos:
            if repo not in gh_profile.profile_analysis.get("repos", []):
                raise GraphQLError(f"Unexpected repo {repo}")

        # remove duplicates and then convert to JSON-encodable format
        gh_profile.profile_analysis["selectedRepos"] = list(set(repos))
        gh_profile.full_clean()
        gh_profile.save()

        github_token = gh_profile.access_token
        analysis_result = trigger_analysis(user, github_token)
        if analysis_result["success"]:
            # Save the analysis log to database
            save_analysis = create_model_object(ProfileAnalysis, user=user)
            if not save_analysis.success:
                logger.critical(
                    "Unable to save ProfileAnalysis to db, errors:\n%(errors)s"
                    % {"errors": "\n".join(save_analysis.errors)}
                )

        return SelectRepos(**analysis_result)


class ConnectStackOverflow(GenericResultMutation):
    class Arguments:
        code = graphene.String(required=True)

    @login_required
    def mutate(self, info, code):
        user = info.context.user

        post_data = {
            "client_id": STACK_OVERFLOW_CLIENT_ID,
            "client_secret": STACK_OVERFLOW_CLIENT_SECRET,
            "code": code,
            "redirect_uri": STACK_OVERFLOW_REDIRECT_URI or "http://localhost",
        }

        oauth_response = requests.post(
            STACK_OVERFLOW_TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="&".join([f"{key}={val}" for key, val in post_data.items()]),
        )
        data = oauth_response.json()

        if (
            oauth_response.status_code != requests.codes.ok
            or "error_message" in data
        ):
            logger.error(
                "Failed while trying to fetch token from StackOverflow\n"
                f"Status Code: {oauth_response.status_code}\n"
                f"Response: {data}"
            )
            return ConnectStackOverflow(
                success=False,
                errors=["Something went wrong. Please try again"],
            )
        else:
            access_token = data["access_token"]

            user_data = stack_overflow_get_user_data(access_token)
            print(user_data)
            if user_data is None:
                return ConnectStackOverflow(
                    success=False,
                    errors=["Something went wrong. Please try again"],
                )

            stack_profile_creation = create_model_object(
                StackOverflowProfile, user=user, **user_data
            )
            print(f"id: {stack_profile_creation.object.id}")
            return ConnectStackOverflow(
                success=stack_profile_creation.success,
                errors=stack_profile_creation.errors,
            )


class ToggleArchiveOutsiderMessage(graphene.Mutation):
    """
    Archive a message by its ID.
    The message should belong to the logged in user (sent to that user)
    """

    new = graphene.Boolean(required=True)

    class Arguments:
        id = graphene.Int(required=True)

    @login_required
    def mutate(self, info, id):
        user = info.context.user

        try:
            msg = user.outsider_messages.get(id=id)
        except OutsiderMessage.DoesNotExist:
            raise GraphQLError("Message not found")

        msg.is_archived = not msg.is_archived

        # In python 3.8 -> if (err := full_clean_and_save(...)) is not None:
        err = full_clean_and_save(msg)
        if err is not None:
            raise GraphQLError(get_error_message(err))

        return ToggleArchiveOutsiderMessage(new=msg.is_archived)


class AddContactInfo(graphene.Mutation):
    contact_info = graphene.Field(ContactInfoType, required=True)

    class Arguments:
        email = graphene.String()
        phone = graphene.String()
        address = graphene.String()

    @login_required
    def mutate(self, info, **args):
        user = info.context.user

        if getattr(user, "contact_info", False):
            ci = user.contact_info
            for (key, val) in args.items():
                if key == "phone":
                    try:
                        pn = phonenumbers.parse(val)
                    except phonenumbers.phonenumberutil.NumberParseException as e:  # noqa: E501
                        raise GraphQLError(str(e))

                    val = phonenumbers.format_number(
                        pn, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                    )

                setattr(ci, key, val)

            err = full_clean_and_save(ci)
            if err is not None:
                raise GraphQLError(get_error_message(err))
        else:
            contact_info = create_model_object(ContactInfo, user=user, **args)
            if contact_info.success:
                ci = contact_info.object
            else:
                raise GraphQLError(contact_info.errors[0])

        return AddContactInfo(contact_info=ci)


class AddProject(graphene.Mutation):
    project = graphene.Field(ProjectType, required=True)
    messages = graphene.List(graphene.NonNull(graphene.String))

    class Arguments:
        name = graphene.String(required=True)
        repos = graphene.NonNull(
            graphene.List(graphene.NonNull(graphene.String))
        )
        tagline = graphene.String(default_value="")
        description = graphene.String(default_value="")
        icon = graphene.String(default_value="")

    def mutate(self, info, name, repos, tagline, description, icon):
        user = info.context.user
        messages = []

        try:
            gh_profile = user.profiles.get(_provider="github")
        except BaseProfileModel.DoesNotExist:
            raise GraphQLError("GitHub Profile isn't connected!")

        # Iterate over and validate all repos first
        for repo_full_name in repos:
            if repo_full_name not in gh_profile.profile_analysis.get(
                "repos", []
            ):
                raise GraphQLError(f"Unexpected repo {repo_full_name}")

        github_token = gh_profile.access_token

        # TODO: just take the repos now which need to be scanned anew
        actual_repos = []
        for repo_full_name in repos:
            try:
                repo, _ = get_or_create_repo_from_github(
                    repo_full_name, github_token
                )
                actual_repos.append(repo)
            except Exception:
                logger.exception(f"Couldn't get repo {repo_full_name}")
                messages.append(f"Couldn't process repo {repo_full_name}")

        gh_profile.profile_analysis["selectedRepos"] = [
            repo.full_name for repo in actual_repos
        ]
        gh_profile.full_clean()
        gh_profile.save()

        # Now run repo analysis on them
        github_token = gh_profile.access_token
        analysis_result = trigger_analysis(
            user, github_token
        )  # fingers crossed
        if analysis_result["success"]:
            # Save the analysis log to database (mostly for logging timestamp)
            save_analysis = create_model_object(ProfileAnalysis, user=user)
            if not save_analysis.success:
                logger.critical(
                    "Unable to save ProfileAnalysis to db, errors:\n%(errors)s"
                    % {"errors": "\n".join(save_analysis.errors)}
                )
        else:
            logger.error(
                f"Unable to trigger repo analysis for user {user} and token {github_token}"  # noqa: E501
            )

        if not icon:
            if gh_profile.profile_analysis:
                icon = gh_profile.profile_analysis["user_profile"]["avatarUrl"]
            else:
                icon = f"https://avatars.githubusercontent.com/u/{gh_profile.provider_uid}?s=400&v=4"  # noqa: E501

        slug = get_project_slug_by_name(name)

        project = Project(
            slug=slug,
            name=name,
            user=user,
            tagline=tagline if tagline else name,
            description=description,
            icon=icon,
        )
        project.full_clean()

        with transaction.atomic():
            project.save()
            project.repos.add(*actual_repos)

        return AddProject(project=project, messages=messages)


class UpdateProject(graphene.Mutation):
    project = graphene.Field(ProjectType, required=True)
    messages = graphene.List(graphene.NonNull(graphene.String))

    class Arguments:
        slug = graphene.String(required=True)
        name = graphene.String()
        repos = graphene.NonNull(
            graphene.List(graphene.NonNull(graphene.String))
        )
        tagline = graphene.String()
        description = graphene.String()
        icon = graphene.String()

    def mutate(self, info, slug, **kwargs):
        user = info.context.user
        messages = []

        try:
            project = user.projects.get(slug=slug)
        except Project.DoesNotExist:
            raise GraphQLError(f"Project {slug} not found")

        for key in kwargs:
            if key == "repos":
                repos = kwargs[key]
                try:
                    gh_profile = user.profiles.get(_provider="github")
                except BaseProfileModel.DoesNotExist:
                    raise GraphQLError("GitHub Profile isn't connected!")

                # Iterate over and validate all repos first
                for repo_full_name in repos:
                    if repo_full_name not in gh_profile.profile_analysis.get(
                        "repos", []
                    ):
                        raise GraphQLError(f"Unexpected repo {repo_full_name}")

                github_token = gh_profile.access_token

                # TODO: just take the repos now which need to be scanned anew
                actual_repos = []
                for repo_full_name in repos:
                    try:
                        repo, _ = get_or_create_repo_from_github(
                            repo_full_name, github_token
                        )
                        actual_repos.append(repo)
                    except Exception:
                        logger.exception(f"Couldn't get repo {repo_full_name}")
                        messages.append(
                            f"Couldn't process repo {repo_full_name}"
                        )

                gh_profile.profile_analysis["selectedRepos"] = [
                    repo.full_name for repo in actual_repos
                ]
                gh_profile.full_clean()
                gh_profile.save()

                # Now run repo analysis on them
                github_token = gh_profile.access_token
                analysis_result = trigger_analysis(
                    user, github_token
                )  # fingers crossed
                if analysis_result["success"]:
                    # Save the analysis log to database
                    save_analysis = create_model_object(
                        ProfileAnalysis, user=user
                    )
                    if not save_analysis.success:
                        logger.critical(
                            "Unable to save ProfileAnalysis to db, errors:\n%(errors)s"  # noqa: E501
                            % {"errors": "\n".join(save_analysis.errors)}
                        )
                else:
                    logger.error(
                        f"Unable to trigger repo analysis for user {user} and token {github_token}"  # noqa: E501
                    )

                project.repos.add(*actual_repos)

            else:
                setattr(project, key, kwargs[key])

        project.full_clean()
        project.save()

        return UpdateProject(project=project, messages=messages)


class Mutation(graphene.ObjectType):
    delete_github_profile = DeleteGithubProfile.Field()
    create_notification = CreateNotification.Field()
    mark_notification_as_read = MarkNotificationAsRead.Field()
    select_repos = SelectRepos.Field()
    connect_stackoverflow = ConnectStackOverflow.Field()
    toggle_archive_outsider_message = ToggleArchiveOutsiderMessage.Field()
    add_contact_info = AddContactInfo.Field()
    add_project = AddProject.Field()
    update_project = UpdateProject.Field()
