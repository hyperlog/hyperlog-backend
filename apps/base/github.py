import logging

import requests


GITHUB_GRAPHQL_API_URL = "https://api.github.com/graphql"
GITHUB_REST_API_BASE_URL = "https://api.github.com"
GITHUB_OAUTH_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

logger = logging.getLogger(__name__)


def get_rest_url_for_endpoint(route):
    """
    Route is the path to exact api endpoint after the base API URL.
    For example, /user or /user/emails
    """
    return f"{GITHUB_REST_API_BASE_URL}{route}"


def execute_github_gql_query(query, token):
    """
    Executes a query against the GitHub GraphQL API and returns the JSON
    response as a Python dict.

    Note: Raises an exception for requests which return status codes other than
    200 (e.g. Bad Credentials) but does not do so for errors thrown by GitHub's
    GraphQL API (e.g. Queried field doesn't exist). Such errors can be found if
    the response json has an 'error' key.
    """
    # Try making the query
    r = requests.post(
        GITHUB_GRAPHQL_API_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"token {token}",
        },
        json={"query": query},
    )
    json_data = r.json()

    # Raise Exception if request wasn't successful
    if r.status_code != requests.codes.ok:
        raise Exception(f"GitHub request failed\n{json_data}")
    else:
        return json_data


def get_user_emails(token):
    """
    Gets the user's emails (with the `GET /user/emails` REST endpoint)

    Returns a List of email objects with each email as a Dict[str -> Any] obj.
    Each email object has 4 keys:
    1. 'email' - str
    2. 'primary' - bool
    3. 'verified' - bool
    4. 'visibility' - str
    """
    url = get_rest_url_for_endpoint("/user/emails")

    # Try hitting the REST API
    r = requests.get(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"token {token}",
        },
    )
    json_data = r.json()

    # Raise Exception if request was unsuccessful
    if r.status_code != requests.codes.ok:
        raise Exception(f"GitHub request failed\n{json_data}")
    else:
        return json_data


def github_trade_code_for_token(code, client_id, client_secret):
    """
    Attempts to use GitHub OAuth to trade the Authorization code for a token.

    Returns the token (str type) if it's present in GitHub's response and
    otherwise returns None.

    A None response should be interpreted as an error
    """
    response = requests.post(
        GITHUB_OAUTH_ACCESS_TOKEN_URL,
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        },
    ).json()

    return response.get("access_token")


def github_get_user_data(token):
    """
    Attempts a GraphQL query to the GitHub GraphQL API to get the user details:
    1. databaseId
    2. login
    3. name

    Returns a dict (with keys: "databaseId", "login" and "name")
    """
    query = """
    {
      viewer {
        databaseId
        login
        name
      }
    }
    """

    try:
        gql_response = execute_github_gql_query(query, token)
    except Exception:
        logger.exception("Couldn't execute GitHub query")
        return None

    if "error" in gql_response:
        logger.error(f"GitHub API error\n{gql_response}")
        return None

    return gql_response["data"]["viewer"]


def github_get_gh_id(token):
    """Gets the GitHub ID for a user"""
    query = """
    {
      viewer {
        databaseId
      }
    }
    """

    try:
        response = execute_github_gql_query(query, token)
    except Exception:
        logger.exception("Couldn't execute GitHub query")
        return None

    if "error" in response:
        logger.error(f"GitHub API error\n{response}")
        return None

    return response["data"]["viewer"]["databaseId"]


def github_get_primary_email(token):
    """Gets the primary email of the GitHub user"""
    try:
        emails = iter(get_user_emails(token))
    except Exception:
        logger.exception("Error while fetching emails from GitHub")
        return None

    return next(email["email"] for email in emails if email["primary"] is True)
