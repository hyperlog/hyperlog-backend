import uuid
from unittest import mock

import graphene
from graphene_django.utils.testing import GraphQLTestCase
from graphql_jwt.shortcuts import get_token, get_user_by_token

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.users.schema import Query, Mutation


class BaseTestCase(GraphQLTestCase):
    GRAPHQL_SCHEMA = graphene.Schema(query=Query, mutation=Mutation)

    def setUp(self):
        self.password = "test_password"
        self.user = get_user_model().objects.create_user(
            username="test_user",
            email="test@example.com",
            password=self.password,
            first_name="test_first",
            last_name="test_last",
        )
        self.token = get_token(self.user)
        self.auth_headers = {"HTTP_AUTHORIZATION": f"JWT {self.token}"}

    def tearDown(self):
        self.user.delete()


class UserQueriesTestCase(BaseTestCase):
    def test_query_user(self):
        response = self.query(
            """
            query($id: String!) {
                user(id: $id) {
                    id
                    username
                    email
                    firstName
                    lastName
                    isEnrolledForMails
                }
            }
            """,
            variables={"id": self.user.id.hex},
        )
        data = response.json()
        expected = {
            "data": {
                "user": {
                    "id": str(self.user.id),
                    "username": self.user.username,
                    "email": self.user.email,
                    "firstName": self.user.first_name,
                    "lastName": self.user.last_name,
                    "isEnrolledForMails": self.user.is_enrolled_for_mails,
                }
            }
        }

        self.assertResponseNoErrors(response)
        self.assertEqual(data, expected)

    def test_query_user_does_not_exist(self):
        response = self.query(
            """
            query($id: String!) {
                user(id: $id) {
                    id
                }
            }
            """,
            variables={"id": str(uuid.uuid4())},  # A random uuid
        )

        self.assertResponseHasErrors(response)

    def test_query_this_user(self):
        response = self.query(
            """
            query {
                thisUser {
                    id
                    username
                    email
                    firstName
                    lastName
                    isEnrolledForMails
                }
            }
            """,
            headers=self.auth_headers,
        )
        data = response.json()
        expected = {
            "data": {
                "thisUser": {
                    "id": str(self.user.id),
                    "username": self.user.username,
                    "email": self.user.email,
                    "firstName": self.user.first_name,
                    "lastName": self.user.last_name,
                    "isEnrolledForMails": self.user.is_enrolled_for_mails,
                }
            }
        }

        self.assertResponseNoErrors(response)
        self.assertEqual(data, expected)

    def test_query_this_user_invalid_token(self):
        response = self.query(
            """
            query {
                thisUser {
                    id
                }
            }
            """,
            headers={"HTTP_AUTHORIZATION": "JWT eyasdfasdfasdf"},
        )

        self.assertResponseHasErrors(response)


class UserAuthTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.login_mutation = """
            mutation($username: String!, $password: String!) {
                login(username: $username, password: $password) {
                    token
                    user {
                        id
                    }
                }
            }
            """
        self.register_mutation = """
            mutation(
                $username: String!,
                $password: String!,
                $email: String!,
                $first_name: String!,
                $last_name: String!
            ) {
                register(
                    username: $username,
                    password: $password,
                    email: $email,
                    firstName: $first_name,
                    lastName: $last_name
                ) {
                    success
                    errors
                    login {
                        token
                        user {
                            id
                            username
                            email
                            firstName
                            lastName
                            registeredAt
                            isEnrolledForMails
                            newUser
                            loginTypes
                            profiles {
                                id
                                provider
                            }
                            notifications {
                                id
                            }
                            widget {
                                id
                            }
                        }
                    }
                }
            }
            """
        self.logout_mutation = """
        mutation {
            logout {
                success
                errors
            }
        }
        """

    def test_login(self):
        response = self.query(
            self.login_mutation,
            variables={
                "username": self.user.username,
                "password": self.password,
            },
        )

        self.assertResponseNoErrors(response)

        data = response.json()
        user_id = data["data"]["login"]["user"]["id"]
        token = data["data"]["login"]["token"]
        user_by_token = get_user_by_token(token)

        self.assertEqual(uuid.UUID(user_id), self.user.id)
        self.assertEqual(user_by_token, self.user)

    def test_register(self):
        variables = {
            "username": "username",
            "password": "password",
            "email": "email@example.com",
            "first_name": "first name",
            "last_name": "",
        }

        response = self.query(self.register_mutation, variables=variables)

        self.assertResponseNoErrors(response)

        data = response.json()
        user_dat = data["data"]["register"]["login"]["user"]
        token = data["data"]["register"]["login"]["token"]
        self.assertIsNotNone(user_dat)
        self.assertIsNotNone(token)

        user_by_token = get_user_by_token(token)
        user_by_id = get_user_model().objects.get(id=user_dat["id"])
        self.assertEqual(user_by_id, user_by_token)

        user_by_id.delete()

    @mock.patch("apps.users.utils.get_user_model")
    def test_register_validation_error(self, mock_get_user_model):
        test_exception = ValidationError("Test")

        mock_user = mock.Mock()
        mock_user.full_clean.side_effect = test_exception
        mock_user_model = mock.Mock(return_value=mock_user)
        mock_get_user_model.return_value = mock_user_model

        variables = {
            "username": self.user.username,
            "password": self.password,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }

        response = self.query(self.register_mutation, variables=variables)

        self.assertResponseNoErrors(response)

        mock_user_model.assert_called()
        mock_user.full_clean.assert_called()

        data = response.json()

        self.assertFalse(data["data"]["register"]["success"])
        self.assertEqual(
            data["data"]["register"]["errors"], [test_exception.message]
        )
        self.assertIsNone(data["data"]["register"]["login"])

    def test_register_username_already_exists(self):
        variables = {
            "username": self.user.username,
            "password": self.password,
            "email": "email@example.com",
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }

        response = self.query(self.register_mutation, variables=variables)

        self.assertResponseNoErrors(response)
        data = response.json()

        self.assertFalse(data["data"]["register"]["success"])
        self.assertIsNone(data["data"]["register"]["login"])
        self.assertIsNotNone(data["data"]["register"]["errors"])

    def test_register_email_already_exists(self):
        variables = {
            "username": "username",
            "password": self.password,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }

        response = self.query(self.register_mutation, variables=variables)

        self.assertResponseNoErrors(response)
        data = response.json()

        self.assertFalse(data["data"]["register"]["success"])
        self.assertIsNone(data["data"]["register"]["login"])
        self.assertIsNotNone(data["data"]["register"]["errors"])

    def test_logout(self):
        response = self.query(self.logout_mutation, headers=self.auth_headers)
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["logout"]["success"])
        self.assertIsNone(data["data"]["logout"]["errors"])


class ValidateParamsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.is_username_valid_mutation = """
            mutation($username: String!) {
                isUsernameValid(username: $username) {
                    success
                    errors
                }
            }
        """
        self.is_email_valid_mutation = """
            mutation($email: String!) {
                isEmailValid(email: $email) {
                    success
                    errors
                }
            }
        """

    def test_is_username_valid_invalid_characters(self):
        username = "asdf asdf"  # whitespace is not allowed in username

        response = self.query(
            self.is_username_valid_mutation, variables={"username": username}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertFalse(data["data"]["isUsernameValid"]["success"])
        self.assertIsNotNone(data["data"]["isUsernameValid"]["errors"])

    def test_is_username_valid_already_exists(self):
        username = self.user.username

        response = self.query(
            self.is_username_valid_mutation, variables={"username": username}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertFalse(data["data"]["isUsernameValid"]["success"])
        self.assertIsNotNone(data["data"]["isUsernameValid"]["errors"])

    def test_is_username_valid_non_latin(self):
        username = "ひほわれよう"  # Japanese

        response = self.query(
            self.is_username_valid_mutation, variables={"username": username}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["isUsernameValid"]["success"])
        self.assertIsNone(data["data"]["isUsernameValid"]["errors"])

    def test_is_username_valid_unicode(self):
        username = "hello👍"

        response = self.query(
            self.is_username_valid_mutation, variables={"username": username}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertFalse(data["data"]["isUsernameValid"]["success"])
        self.assertIsNotNone(data["data"]["isUsernameValid"]["errors"])

    def test_is_username_valid_ok(self):
        username = "a+valid@username.-_123"

        response = self.query(
            self.is_username_valid_mutation, variables={"username": username}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["isUsernameValid"]["success"])
        self.assertIsNone(data["data"]["isUsernameValid"]["errors"])

    def test_is_email_valid_invalid_characters(self):
        email = "asdf@asdf. xyz"

        response = self.query(
            self.is_email_valid_mutation, variables={"email": email}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertFalse(data["data"]["isEmailValid"]["success"])
        self.assertIsNotNone(data["data"]["isEmailValid"]["errors"])

    def test_is_email_valid_invalid_syntax(self):
        email = "asdf@asdf"

        response = self.query(
            self.is_email_valid_mutation, variables={"email": email}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertFalse(data["data"]["isEmailValid"]["success"])
        self.assertIsNotNone(data["data"]["isEmailValid"]["errors"])

    def test_is_email_valid_already_exists(self):
        email = self.user.email

        response = self.query(
            self.is_email_valid_mutation, variables={"email": email}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertFalse(data["data"]["isEmailValid"]["success"])
        self.assertIsNotNone(data["data"]["isEmailValid"]["errors"])

    def test_is_email_valid_ok(self):
        email = "anunusedemail@example.com"

        response = self.query(
            self.is_email_valid_mutation, variables={"email": email}
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["isEmailValid"]["success"])
        self.assertIsNone(data["data"]["isEmailValid"]["errors"])


class UpdateUserTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()

        self.mutation_update_user = """
            mutation($first: String, $last: String) {
                updateUser(firstName: $first, lastName: $last) {
                    success
                    errors
                }
            }
        """
        self.mutation_update_password = """
            mutation($old: String!, $new: String!) {
                updatePassword(old: $old, new: $new) {
                    success
                    errors
                }
            }
        """

    def test_update_user_first_and_last_names_ok(self):
        new_first = "New First"
        new_last = "New Last"

        response = self.query(
            self.mutation_update_user,
            variables={"first": new_first, "last": new_last},
            headers=self.auth_headers,
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["updateUser"]["success"])
        self.assertIsNone(data["data"]["updateUser"]["errors"])

        # Refreshing user to check for changes
        self.user.refresh_from_db(fields=["first_name", "last_name"])
        self.assertEqual(self.user.first_name, new_first)
        self.assertEqual(self.user.last_name, new_last)

    def test_update_user_last_name_blank_ok(self):
        new_last = ""

        response = self.query(
            self.mutation_update_user,
            variables={"last": new_last},
            headers=self.auth_headers,
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["updateUser"]["success"])
        self.assertIsNone(data["data"]["updateUser"]["errors"])

        # Refreshing user to check for changes
        self.user.refresh_from_db(fields=["first_name", "last_name"])
        self.assertEqual(self.user.last_name, new_last)

    def test_update_user_first_name_has_unicode_characters_ok(self):
        new_first = "👍"  # Unicode

        response = self.query(
            self.mutation_update_user,
            variables={"first": new_first},
            headers=self.auth_headers,
        )

        data = response.json()
        self.assertTrue(data["data"]["updateUser"]["success"])
        self.assertIsNone(data["data"]["updateUser"]["errors"])

        self.user.refresh_from_db(fields=["first_name"])
        self.assertEqual(self.user.first_name, new_first)

    def test_update_user_first_name_blank(self):
        new_first = ""

        response = self.query(
            self.mutation_update_user,
            variables={"first": new_first},
            headers=self.auth_headers,
        )

        data = response.json()
        self.assertFalse(data["data"]["updateUser"]["success"])
        self.assertIsNotNone(data["data"]["updateUser"]["errors"])

    def test_update_user_user_not_authenticated(self):
        new_first = ""

        # No headers param
        response = self.query(
            self.mutation_update_user, variables={"first": new_first}
        )
        self.assertResponseHasErrors(response)

    def test_update_password_ok(self):
        new_password = "new password"

        response = self.query(
            self.mutation_update_password,
            variables={"old": self.password, "new": new_password},
            headers=self.auth_headers,
        )
        self.assertResponseNoErrors(response)

        data = response.json()
        self.assertTrue(data["data"]["updatePassword"]["success"])
        self.assertIsNone(data["data"]["updatePassword"]["errors"])

        # Check that new password works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_update_password_user_not_authenticated(self):
        new_password = "new password"

        # Notice the missing headers param
        response = self.query(
            self.mutation_update_password,
            variables={"old": self.password, "new": new_password},
        )
        self.assertResponseHasErrors(response)

        self.assertFalse(self.user.check_password(new_password))

    def test_update_password_old_password_is_incorrect(self):
        new_password = "new password"
        old_password = "something made up"

        response = self.query(
            self.mutation_update_password,
            variables={"old": old_password, "new": new_password},
            headers=self.auth_headers,
        )

        data = response.json()
        self.assertFalse(data["data"]["updatePassword"]["success"])
        self.assertIsNotNone(data["data"]["updatePassword"]["errors"])

        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(new_password))
        self.assertTrue(self.user.check_password(self.password))
