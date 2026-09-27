"""The React dev server (another origin) must be allowed; other sites must not."""

FRONTEND = "http://localhost:5173"


def preflight(client, path, origin):
    return client.options(path, headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    })


def test_preflight_allows_frontend_with_authorization_header(app):
    response = preflight(app.test_client(), "/chat", FRONTEND)

    # The preflight is answered without a token (no 401).
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == FRONTEND
    assert "authorization" in response.headers["Access-Control-Allow-Headers"].lower()


def test_other_origins_are_not_allowed(app):
    response = preflight(app.test_client(), "/chat", "http://evil.example.com")
    assert "Access-Control-Allow-Origin" not in response.headers


def test_error_responses_carry_cors_headers(app):
    # Without this, the browser hides the 401 from React.
    response = app.test_client().post("/chat", json={}, headers={"Origin": FRONTEND})
    assert response.status_code == 401
    assert response.headers["Access-Control-Allow-Origin"] == FRONTEND
