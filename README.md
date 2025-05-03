# OAuth2 Imitation Service

This project provides a simplified imitation of an OAuth 2.0 service, focusing on the Authorization Code grant flow with extensions for user identification and logout, similar to some real-world single sign-on (SSO) systems. It uses FastAPI and stores data in simple JSON files.

## Features

*   **Authorization Code Grant:** Implements the standard flow (`response_type=one_code`, `grant_type=one_authorization_code`).
*   **Refresh Tokens:** Supports token refreshing (`grant_type=refresh_token`).
*   **User Identification:** Custom grant (`grant_type=one_access_token_identify`) to fetch user details using an access token.
*   **Logout:** Custom grant (`grant_type=one_log_out`) to invalidate access and refresh tokens.
*   **In-Memory/JSON Storage:** Uses simple JSON files (`clients.json`, `users.json`, `auth_codes.json`, `access_tokens.json`, `refresh_tokens.json`) for storing client configurations, user details, and tokens. Data is persisted in the `data/` directory by default.
*   **Docker Support:** Includes a `Dockerfile` for easy containerization.

## Setup

### Prerequisites

*   Python 3.11+
*   Pip

### Installation

1.  **Clone the repository (if applicable):**
    ```bash
    # git clone <repository_url>
    # cd oneid-imitation
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Running the Service

*   **Directly with Uvicorn (for development):**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
    The service will be available at `http://localhost:8000`. The `--reload` flag enables auto-reloading on code changes.

*   **Using Docker:**
    1.  Build the image:
        ```bash
        docker build -t oauth-imitation .
        ```
    2.  Run the container:
        ```bash
        docker run -p 8000:8456 -v "$(pwd)/data":/app/data oauth-imitation
        ```
        The service will be available at `http://localhost:8000`. Port 8456 inside the container is mapped to port 8000 on the host. The `data` directory is mounted as a volume to persist data outside the container.

## Configuration

### Data Storage

*   Data files (`clients.json`, `users.json`, etc.) are stored in the `data/` directory by default.
*   You can change the data directory by setting the `DATA_DIR` environment variable before running the application or the container.

### Clients

*   OAuth clients are defined in `data/clients.json`.
*   Each client has a `client_id`, `client_secret`, a list of allowed `redirect_uris`, and `allowed_scopes`.
*   Example:
    ```json
    {
        "test": {
            "client_secret": "test",
            "redirect_uris": ["http://localhost:8080/login"],
            "allowed_scopes": ["test", "profile", "email"]
        }
    }
    ```

### Users

*   Users are defined in `data/users.json`.
*   Each user has a `username` (key), `password`, `user_id`, and other profile information.
*   Example:
    ```json
    {
        "testuser": {
            "password": "password123",
            "user_id": "testuser",
            "first_name": "Test",
            "sur_name": "User",
            "full_name": "Test User",
            // ... other fields
        }
    }
    ```

## API Endpoints & Flow

The primary endpoint `/sso/oauth/Authorization.do` handles multiple operations based on the request method and parameters.

### 1. Initiate Authorization

*   **Method:** `GET`
*   **Endpoint:** `/sso/oauth/Authorization.do`
*   **Description:** Starts the OAuth flow. Redirects the user agent to the login form.
*   **Query Parameters:**
    *   `response_type`: Must be `one_code`.
    *   `client_id`: Your client application's ID.
    *   `redirect_uri`: The URI to redirect back to after successful login. Must be one of the registered URIs for the client.
    *   `scope` (optional): Space-separated list of requested scopes.
    *   `state` (optional): An opaque value used to maintain state between the request and callback.

*   **Example Request:**
    ```
    GET /sso/oauth/Authorization.do?response_type=one_code&client_id=test&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin&scope=test&state=xyz123
    ```
*   **Response:** `302 Found` redirect to `/oauth_login_form` with parameters passed through.

### 2. User Login

*   **Endpoint:** `/oauth_login_form` (GET - displays form), `/authenticate` (POST - handles submission)
*   **Description:** The user enters their credentials on the form displayed by `/oauth_login_form`. Submitting the form POSTs to `/authenticate`.
*   **Authentication:** `/authenticate` validates the username/password against `users.json`.
*   **Response (on successful login):** `302 Found` redirect back to the client's `redirect_uri` with an authorization `code` and the original `state` (if provided) appended as query parameters.
    *   Example Redirect: `http://localhost:8080/login?code=AUTHORIZATION_CODE_HERE&state=xyz123`
*   **Response (on failed login):** `302 Found` redirect back to `/oauth_login_form` with an error message.

### 3. Exchange Authorization Code for Tokens

*   **Method:** `POST`
*   **Endpoint:** `/sso/oauth/Authorization.do`
*   **Description:** The client application exchanges the received authorization code for access and refresh tokens.
*   **Form Parameters:**
    *   `grant_type`: Must be `one_authorization_code`.
    *   `code`: The authorization code received in the previous step.
    *   `redirect_uri`: The same redirect URI used in the initial authorization request.
    *   `client_id`: Your client application's ID.
    *   `client_secret`: Your client application's secret.

*   **Example Request (Form URL Encoded):**
    ```
    grant_type=one_authorization_code&code=AUTHORIZATION_CODE_HERE&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Flogin&client_id=test&client_secret=test
    ```
*   **Response (Success):** `200 OK` with JSON body:
    ```json
    {
        "access_token": "ACCESS_TOKEN_HERE",
        "token_type": "bearer",
        "expires_in": 3600, // Lifetime in seconds
        "refresh_token": "REFRESH_TOKEN_HERE",
        "scope": "requested scopes granted"
    }
    ```
*   **Response (Error):** `4xx` status code with error details.

### 4. Refresh Access Token

*   **Method:** `POST`
*   **Endpoint:** `/sso/oauth/Authorization.do`
*   **Description:** Obtain a new access token using a refresh token when the original access token expires.
*   **Form Parameters:**
    *   `grant_type`: Must be `refresh_token`.
    *   `refresh_token`: The refresh token obtained previously.
    *   `client_id`: Your client application's ID.
    *   `client_secret`: Your client application's secret.

*   **Example Request (Form URL Encoded):**
    ```
    grant_type=refresh_token&refresh_token=REFRESH_TOKEN_HERE&client_id=test&client_secret=test
    ```
*   **Response (Success):** `200 OK` with JSON body (similar to code exchange, potentially with a new refresh token):
    ```json
    {
        "access_token": "NEW_ACCESS_TOKEN_HERE",
        "token_type": "bearer",
        "expires_in": 3600,
        "refresh_token": "NEW_OR_SAME_REFRESH_TOKEN_HERE",
        "scope": "original scopes"
    }
    ```
*   **Response (Error):** `4xx` status code if the refresh token is invalid, expired, or mismatched.

### 5. Get User Information

*   **Method:** `POST`
*   **Endpoint:** `/sso/oauth/Authorization.do`
*   **Description:** A custom grant type to retrieve information about the user associated with an access token.
*   **Form Parameters:**
    *   `grant_type`: Must be `one_access_token_identify`.
    *   `access_token`: A valid access token.
    *   `scope`: Space-separated list of scopes required for this operation (must be allowed for the client and granted to the token).
    *   `client_id`: Your client application's ID.
    *   `client_secret`: Your client application's secret.

*   **Example Request (Form URL Encoded):**
    ```
    grant_type=one_access_token_identify&access_token=ACCESS_TOKEN_HERE&scope=profile&client_id=test&client_secret=test
    ```
*   **Response (Success):** `200 OK` with JSON body containing user details (excluding password):
    ```json
    {
        "user_id": "testuser",
        "first_name": "Test",
        "sur_name": "User",
        // ... other fields from users.json
    }
    ```
*   **Response (Error):** `401 Unauthorized` if token is invalid/expired, `403 Forbidden` if scope is insufficient, `404 Not Found` if user doesn't exist.

### 6. Log Out

*   **Method:** `POST`
*   **Endpoint:** `/sso/oauth/Authorization.do`
*   **Description:** A custom grant type to invalidate the access token and associated refresh tokens for the user/client combination.
*   **Form Parameters:**
    *   `grant_type`: Must be `one_log_out`.
    *   `access_token`: The access token to invalidate.
    *   `scope`: Space-separated list of scopes required (must be allowed for the client).
    *   `client_id`: Your client application's ID.
    *   `client_secret`: Your client application's secret.

*   **Example Request (Form URL Encoded):**
    ```
    grant_type=one_log_out&access_token=ACCESS_TOKEN_HERE&scope=test&client_id=test&client_secret=test
    ```
*   **Response:** `200 OK` with JSON body:
    ```json
    {
        "status": "logged_out"
    }
    ```
    *(Note: This endpoint always returns success even if the token was already invalid, to prevent leaking information.)*

## Notes

*   **Security:** This is an *imitation* service for development and testing. It lacks many security features of a production OAuth server (e.g., proper session management, rate limiting, robust input validation, secure storage). **Do not use in production.**
*   **Error Handling:** Errors are generally returned with appropriate HTTP status codes (400, 401, 403, 404) and a JSON body like `{"detail": "Error message"}`.
*   **Time Units:** Authorization codes have lifetimes in seconds, while tokens use milliseconds internally for expiry checks (`expires_at`), but return `expires_in` in seconds externally. 