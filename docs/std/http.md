# http

HTTP/1.1 clients and servers, like Python's urllib.request and http.server.

```silly
import http
fn main():
    let r = http.get(&"http://example.com/").unwrap()
    print(r.status, r.reason, r.header(&"content-type").unwrap_or(""))
    print(r.body[0:60])

# A server: each request goes to handler, whose Response is sent back.
fn hello(req: http.Request) -> http.Response:
    if req.path == "/":
        return http.html(&"<h1>Hello</h1>")
    return http.response(404, &"no such page\n")

fn serve():
    http.serve(&"127.0.0.1", 8000, hello).unwrap()
```

Plain http:// is spoken directly over a socket; https:// goes through the
curl program, so it needs curl installed. Redirects are followed (up to 5).
The server handles one request at a time and closes each connection after
answering it.

## Types

### `Response`

What a server sent back; also what a server handler returns.

- `status: int`
- `reason: str`
- `headers: list[(str, str)]`
- `body: str`
- `url: str` — where it came from, after redirects

- `header(self, name: &str) -> Option[str]` — The first header called name (in any case).
- `ok(self) -> bool` — Whether the status is 2xx.
- `text(self) -> str`
- `json(self) -> Result[json.Value, str]` — The body parsed as JSON.
- `with_header(self, name: &str, value: &str) -> Response` — A copy with one more header (for building server responses).
- `str(self) -> str`

### `Request`

A request as a server handler sees it.

- `method: str` — "GET", "POST", ...
- `path: str` — decoded, without the query
- `query: str` — raw, without the "?"
- `headers: list[(str, str)]`
- `body: str`
- `client: str` — the client's address

- `header(self, name: &str) -> Option[str]`
- `params(self) -> list[(str, str)]` — The query's (key, value) pairs, decoded.
- `param(self, name: &str) -> Option[str]` — The first value of query parameter name.
- `form(self) -> list[(str, str)]` — The body as form fields (application/x-www-form-urlencoded).
- `json(self) -> Result[json.Value, str]`
- `str(self) -> str`

### `Server`

A listening HTTP server (see server(), quiet_server() and serve()).

- `sock: socket.Socket`
- `quiet: bool` — don't log each request to stderr

- `port(self) -> int` — The port it listens on (the one picked, if it was started on port 0).
- `handle_one(self, handler: fn(Request) -> Response) -> Result[bool, str]` — Waits for one connection, answers its request with handler, and closes it. A broken request gets a 400 and is otherwise ignored.
- `serve_forever(self, handler: fn(Request) -> Response)` — Answers requests until the program is stopped.
- `close(self)`

## Functions

### `reason(status: int) -> str`

The standard phrase for a status code ("Not Found" for 404).

### `response(status: int, body: &str) -> Response`

A plain-text response.

### `html(body: &str) -> Response`

A 200 response with an HTML body.

### `json_response(v: &json.Value) -> Response`

A 200 response with a JSON body.

### `redirect(location: &str) -> Response`

A redirect (302) to location.

### `request_timeout(method: &str, target: &str, headers: &list[(str, str)], body: &str, timeout: f64) -> Result[Response, str]`

Sends a request and returns the response, following redirects. headers are extra request headers; timeout is in seconds (0.0 for none).

### `request(method: &str, target: &str, headers: &list[(str, str)], body: &str) -> Result[Response, str]`

Sends method to target (http:// or https://), following redirects.

### `get(target: &str) -> Result[Response, str]`

A GET of target.

### `fetch(target: &str) -> Result[str, str]`

The body of a GET, or an error if the status isn't 2xx.

### `post(target: &str, body: &str, content_type: &str) -> Result[Response, str]`

A POST of body to target with the given Content-Type.

### `post_form(target: &str, fields: &list[(str, str)]) -> Result[Response, str]`

Posts form fields, url-encoded.

### `post_json(target: &str, v: &json.Value) -> Result[Response, str]`

Posts a JSON value.

### `server(host: &str, port: int) -> Result[Server, str]`

A server listening on host:port (port 0 picks a free one; see port()).

### `quiet_server(host: &str, port: int) -> Result[Server, str]`

Like server, without the request log.

### `serve(host: &str, port: int, handler: fn(Request) -> Response) -> Result[bool, str]`

Serves handler on host:port until the program is stopped.
