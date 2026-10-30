# url

URLs: splitting, joining, percent-encoding and query strings, like Python's
urllib.parse.

```silly
import url
fn main():
    let u = url.parse(&"https://user@example.com:8080/a/b?q=1&x=two#top")
    print(u.scheme, u.host(), u.port(), u.path, u.query)   # https example.com 8080 /a/b q=1&x=two
    print(url.quote(&"a b/c"))                            # a%20b/c
    print(url.urlencode(&[("q", "silly lang"), ("n", "1")]))  # q=silly+lang&n=1
    print(url.urljoin(&"http://a/b/c/d", &"../g"))        # http://a/b/g
```

## Types

### `URL`

A URL split into its parts (see parse()).

- `scheme: str`
- `netloc: str` — "user:pw@host:port"
- `path: str`
- `query: str` — without the "?"
- `fragment: str` — without the "#"

- `str(self) -> str` — The URL as text again.
- `host(self) -> str` — The host part of netloc, lowercased, without brackets around IPv6 addresses.
- `port(self) -> int` — The port, or -1 if there is none (or it isn't a number).
- `username(self) -> str` — The user name before "@", or "".
- `password(self) -> str` — The password after "user:", or "".
- `params(self) -> list[(str, str)]` — The query's (key, value) pairs, decoded.

## Functions

### `parse(s: &str) -> URL`

Splits a URL into its five parts (urlsplit). Nothing is decoded.

### `unsplit(scheme: &str, netloc: &str, path: &str, query: &str, fragment: &str) -> str`

Puts the five parts back together (urlunsplit).

### `quote(s: &str) -> str`

Percent-encodes everything except letters, digits, "_.-~" and "/".

### `quote_safe(s: &str, safe: &str) -> str`

Percent-encodes everything except letters, digits, "_.-~" and the chars in safe.

### `quote_plus(s: &str) -> str`

Like quote with nothing else safe, and spaces as "+" (for query strings and forms).

### `unquote(s: &str) -> str`

Decodes %XX escapes.

### `unquote_plus(s: &str) -> str`

Decodes %XX escapes and "+" as a space.

### `parse_qsl(q: &str) -> list[(str, str)]`

"a=1&b=x+y" as decoded pairs, in order. Empty parts are skipped; a part without "=" has an empty value.

### `parse_qs(q: &str) -> map[str, list[str]]`

The values for each key, in order.

### `urlencode(pairs: &list[(str, str)]) -> str`

Pairs as a query string, with quote_plus.

### `urljoin(base: &str, ref: &str) -> str`

A reference resolved against a base URL, as a browser would (RFC 3986).
