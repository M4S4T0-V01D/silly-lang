# path

Path manipulation on strings, like Python's os.path. Nothing here touches the disk
except abspath and expanduser, which ask the os module for the cwd and $HOME.

```silly
import path
path.join("src", "main.silly")      # "src/main.silly"
path.splitext("a/b.tar.gz")         # ("a/b.tar", ".gz")
path.normalize("a/./b/../c")        # "a/c"
```

## Functions

### `join(a: str, b: str) -> str`

Joins two paths; an absolute second part replaces the first.

### `join_all(parts: &list[str]) -> str`

Joins any number of parts.

### `is_abs(p: &str) -> bool`

Whether p starts at the root.

### `split(p: &str) -> (str, str)`

(head, tail): everything before the last "/" and the final component.

### `basename(p: &str) -> str`

The final component: basename("a/b.txt") == "b.txt", basename("a/") == "".

### `dirname(p: &str) -> str`

Everything but the final component: dirname("a/b.txt") == "a".

### `splitext(p: &str) -> (str, str)`

(root, ext) with ext starting at the last "." of the final component. A leading dot is not an extension: splitext(".bashrc") == (".bashrc", "").

### `ext(p: &str) -> str`

The extension including its dot, or "".

### `stem(p: &str) -> str`

The final component without its extension.

### `with_ext(p: &str, e: &str) -> str`

Replaces the extension: with_ext("a/b.c", ".txt") == "a/b.txt".

### `parts(p: &str) -> list[str]`

The components between slashes, with a leading "/" kept for absolute paths.

### `normalize(p: &str) -> str`

Removes "." components, doubled slashes and "x/.." pairs, without looking at the disk.

### `abspath(p: &str) -> str`

An absolute, normalized form of the path, based on the current directory.

### `relpath(p: &str, base: &str) -> str`

The path of `p` relative to `base` (both made absolute first).

### `expanduser(p: &str) -> str`

Replaces a leading "~" with $HOME.

### `exists(p: str) -> bool`

Whether p exists.

### `is_file(p: str) -> bool`

Whether p is a regular file.

### `is_dir(p: str) -> bool`

Whether p is a directory.
