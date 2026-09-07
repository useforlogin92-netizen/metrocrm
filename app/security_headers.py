from fastapi import Request


NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, private",
    "Pragma": "no-cache",
    "Expires": "0",
}


def install_no_cache_middleware(app) -> None:
    @app.middleware("http")
    async def no_cache_middleware(request: Request, call_next):
        response = await call_next(request)
        for name, value in NO_CACHE_HEADERS.items():
            response.headers[name] = value
        return response
