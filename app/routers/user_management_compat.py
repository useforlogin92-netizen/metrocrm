"""Compatibility route for the user-management create URL.

The actual create operation is POST-only at /admin/users/create. A legacy UI
can still navigate to that URL with GET, which otherwise produces FastAPI's
405 Method Not Allowed response. Redirect GET requests back to the user
management page where the create form is rendered.
"""
from fastapi import Request
from fastapi.responses import RedirectResponse

from app import main

app = main.app


@app.get("/admin/users/create")
def admin_users_create_page(request: Request):
    """Open the existing user-management page instead of exposing a POST URL."""
    return RedirectResponse("/admin/users", status_code=303)
