"""Serve the compiled React app only at its explicit page routes."""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.deps import get_session_service
from app.api.web_auth import COOKIE_NAME, is_operator
from app.application.auth_sessions import AttemptUnauthorized, SessionService


def register_web_pages(app: FastAPI, directory: Path) -> None:
    def page(status_code: int = 200):
        index = directory / 'index.html'
        if not index.is_file():
            raise HTTPException(status_code=503, detail='Web build unavailable. Build the web project first.')
        return FileResponse(index, status_code=status_code, media_type='text/html',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.get('/login', include_in_schema=False)
    def login_page():
        return page()

    @app.get('/admin', include_in_schema=False)
    def admin_page(request: Request, sessions: SessionService = Depends(get_session_service)):
        token = request.cookies.get(COOKIE_NAME)
        try:
            if not token:
                raise AttemptUnauthorized('Login required')
            account = sessions.authenticate(token)
        except AttemptUnauthorized:
            return RedirectResponse('/login', status_code=303, headers={'Cache-Control': 'no-store'})
        # The public shell contains no account data. React renders the denial and
        # the user's own ID after its authenticated session request.
        return page(200 if is_operator(account) else 403)

    app.mount('/assets', StaticFiles(directory=directory / 'assets', check_dir=False), name='web-assets')
