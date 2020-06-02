from itertools import chain

from apps.users.models import DeletedUser, User


def to_dict(instance):
    # https://stackoverflow.com/a/29088221
    opts = instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(instance)
    for f in opts.many_to_many:
        data[f.name] = [i.id for i in f.value_from_object(instance)]
    return data


def delete_user(user: User) -> DeletedUser:
    """Delete a user

    Does the following:
    1. Copy the user's fields into the DeletedUser table (with is_active=False)
    2. Delete the user from the main Users table

    Notes:
    The objects with this model as foreign key will be deleted (e.g. the
    GithubProfile)
    """
    # Get the dict representation of user and rename the ID field
    user_dict = to_dict(user)
    user_dict["old_user_id"] = user_dict.pop("id")

    kwargs = {}
    for field in DeletedUser._meta.get_fields():
        if field.name in user_dict:
            kwargs[field.name] = user_dict.pop(field.name)

    deleted_user = DeletedUser(**kwargs)
    deleted_user.save()
    user.delete()

    return deleted_user
