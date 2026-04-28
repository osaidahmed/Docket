import json

import requests


def make_http_error(status, body=None, *, text=None):
    response = requests.Response()
    response.status_code = status
    if text is not None:
        response._content = text.encode() if isinstance(text, str) else text
    else:
        response._content = json.dumps(body or {}).encode()
    return requests.HTTPError(response=response)
