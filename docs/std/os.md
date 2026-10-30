# os

Operating-system services: environment, working directory, files and directories.

```silly
import os
fn main():
    print(os.getcwd())
    for name in os.listdir(".").unwrap():
        if os.is_dir(name):
            print(name + "/")
    os.makedirs("out/logs").unwrap()
```

Calls that can fail return Result[T, str] with the system's error message.

## Constants

- `SEP: str = "/"` — The path separator, and the separator of lists of paths such as PATH.
- `PATHSEP: str = ":"`
- `LINESEP: str = "\n"`

## Functions

### `getenv(key: str) -> Option[str]`

The value of an environment variable, or None if it isn't set.

### `getenv_or(key: str, default: str) -> str`

The value of an environment variable, or `default` if it isn't set.

### `setenv(key: str, value: str) -> Result[bool, str]`

Sets an environment variable for this process and its children.

### `unsetenv(key: str) -> Result[bool, str]`

Removes an environment variable.

### `environ() -> map[str, str]`

Every environment variable, in the order the system keeps them.

### `getpid() -> int`

This process's id.

### `getppid() -> int`

The parent process's id.

### `getuid() -> int`

The user id this process runs as.

### `getcwd() -> str`

The current working directory.

### `chdir(path: str) -> Result[bool, str]`

Changes the current working directory.

### `system(cmd: str) -> int`

Runs a shell command, letting it use this program's terminal; returns its exit status.

### `hostname() -> str`

This machine's host name.

### `sysname() -> str`

The operating system's name, such as "Linux".

### `release() -> str`

The kernel release, such as "6.9.1".

### `machine() -> str`

The CPU architecture, such as "x86_64".

### `listdir(path: str) -> Result[list[str], str]`

The names in a directory (not "." or ".."), sorted.

### `mkdir(path: str) -> Result[bool, str]`

Creates one directory (see makedirs for parents too).

### `makedirs(path: str) -> Result[bool, str]`

Creates a directory and any missing parents; an existing directory is fine.

### `remove(path: str) -> Result[bool, str]`

Removes a file (or a symbolic link).

### `rmdir(path: str) -> Result[bool, str]`

Removes an empty directory.

### `remove_all(path: str) -> Result[bool, str]`

Removes a file, or a directory and everything in it.

### `rename(src: str, dst: str) -> Result[bool, str]`

Moves src to dst, replacing dst if it exists.

### `symlink(target: str, path: str) -> Result[bool, str]`

Creates a symbolic link at path pointing to target.

### `readlink(path: str) -> Result[str, str]`

Where the symbolic link at path points.

### `chmod(path: str, mode: int) -> Result[bool, str]`

Sets permission bits, such as 0o755.

### `exists(path: str) -> bool`

Whether path exists (following links).

### `is_file(path: str) -> bool`

Whether path is a regular file.

### `is_dir(path: str) -> bool`

Whether path is a directory.

### `is_link(path: str) -> bool`

Whether path is a symbolic link (not following it).

### `file_size(path: str) -> Result[int, str]`

The size of the file at path in bytes.

### `mtime(path: str) -> Result[f64, str]`

Last modification time as a Unix timestamp in seconds.

### `mode(path: str) -> Result[int, str]`

Permission bits of a file.

### `realpath(path: str) -> Result[str, str]`

The absolute path with every symbolic link resolved; the file must exist.

### `read(path: str) -> Result[str, str]`

The whole contents of the file at path.

### `write(path: str, data: str) -> Result[bool, str]`

Replaces the file at path with data, creating it if needed.

### `append(path: str, data: str) -> Result[bool, str]`

Adds data to the end of the file at path, creating it if needed.

### `copy(src: str, dst: str) -> Result[bool, str]`

Copies a file's contents.

### `walk(root: str) -> Result[list[str], str]`

Every file under a directory, as paths starting with `root`, in sorted order.

### `tmpdir() -> str`

The directory for temporary files ($TMPDIR or /tmp).

### `mkdtemp(prefix: str) -> Result[str, str]`

Creates a new, empty, uniquely named directory under tmpdir().
