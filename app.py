from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Response

from src.web.app import RESPONSE_HEADERS, get_response


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/{path:path}")
def serve(request: Request):
    query = parse_qs(request.scope["query_string"].decode("latin-1"))
    status, body, content_type = get_response(request.url.path, query)
    return Response(
        content=body,
        status_code=status,
        headers={**RESPONSE_HEADERS, "Content-Type": content_type},
    )
