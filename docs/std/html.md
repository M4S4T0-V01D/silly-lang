# html

Escaping text for HTML, like Python's html.

```silly
import html
fn main():
    print(html.escape(&"<a href=\"x\">Tom & Jerry</a>"))
    # &lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry&lt;/a&gt;
    print(html.unescape(&"&lt;p&gt; caf&eacute; &#169; &#x1F600;"))   # <p> café © 😀
    print(html.strip_tags(&"<b>bold</b> text"))                       # bold text
```

## Functions

### `escape(s: &str) -> str`

Replaces & < > " and ' with entities, so the text is safe in an element or a quoted attribute.

### `escape_text(s: &str) -> str`

Like escape, but leaves quotes alone (for text between tags).

### `unescape(s: &str) -> str`

Replaces entities (&amp; &#169; &#xA9; and the common named ones) with the characters they stand for. The closing ";" is required. Unknown or broken entities are left as they are. Numeric ones that aren't valid characters become U+FFFD.

### `strip_tags(s: &str) -> str`

The text with <tags> and <!-- comments --> removed and entities decoded.
