import uuid
from unittest import mock

import graphene
from graphene_django.utils.testing import GraphQLTestCase
from graphql_jwt.shortcuts import get_token, get_user_by_token

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.users.schema import Query, Mutation


class UsersTestCase(GraphQLTestCase):
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
            headers={"HTTP_AUTHORIZATION": f"JWT {self.token}"},
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

    def test_login(self):
        response = self.query(
            """
            mutation($username: String!, $password: String!) {
                login(username: $username, password: $password) {
                    token
                    user {
                        id
                    }
                }
            }
            """,
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

        response = self.query(
            """
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
                }
            }
            """,
            variables=variables,
        )

        self.assertResponseNoErrors(response)

        mock_user_model.assert_called()
        mock_user.full_clean.assert_called()

        data = response.json()

        self.assertFalse(data["data"]["register"]["success"])
        self.assertEqual(
            data["data"]["register"]["errors"], [test_exception.message]
        )

    def tearDown(self):
        self.user.delete()
