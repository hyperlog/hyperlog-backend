import requests


GITHUB_GRAPHQL_API_URL = "https://api.github.com/graphql"
GITHUB_REST_API_BASE_URL = "https://api.github.com"


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
