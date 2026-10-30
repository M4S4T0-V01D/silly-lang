# shutil

Copying, moving and removing whole files and trees, and finding programs, like
Python's shutil.

```silly
import shutil
fn main():
    shutil.copytree("assets", "build/assets").unwrap()
    shutil.move("out.txt", "build/").unwrap()
    match shutil.which("gcc"):
        case Some(p): print("gcc is", p)
        case None: print("no gcc")
```

## Functions

### `copyfile(src: str, dst: str) -> Result[str, str]`

Copies a file's contents to dst; if dst is a directory, into it under the same name. Returns the path written.

### `copy(src: str, dst: str) -> Result[str, str]`

Like copyfile, and copies the permission bits too.

### `copytree(src: str, dst: str) -> Result[bool, str]`

Copies a directory and everything in it to dst, which must not exist yet. Symbolic links are copied as links.

### `rmtree(p: str) -> Result[bool, str]`

Removes a directory tree (or a file).

### `move(src: str, dst: str) -> Result[str, str]`

Moves a file or tree; into dst when dst is a directory. Falls back to copying and removing when a rename can't cross file systems. Returns the new path.

### `which(name: str) -> Option[str]`

The full path of a program found on $PATH (or the name itself if it holds a "/" and is executable), like the shell's `which`.

### `tree_size(p: str) -> Result[int, str]`

The total size in bytes of a file, or of every file under a directory.
