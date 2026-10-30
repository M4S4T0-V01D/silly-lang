# The standard library

`import name` loads any of these. The pages are generated from the comments in
`silly/std/*.silly` by `tools/stddoc.py`; edit the source, then rerun it.

| Module | |
|---|---|
| [`argparse`](argparse.md) | Command-line parsing, like Python's argparse. |
| [`base64`](base64.md) | Base64, Base32 and hex encodings of byte strings, like Python's base64 and binascii. |
| [`binary`](binary.md) | Packing numbers into bytes and back, like Python's struct (which is a keyword here), plus typed Writer and Reader for building and walking binary data. |
| [`bisect`](bisect.md) | Binary search in sorted lists, like Python's bisect. |
| [`collections`](collections.md) | Container types beyond list and map, like Python's collections. |
| [`csv`](csv.md) | Reading and writing CSV, like Python's csv module. |
| [`datetime`](datetime.md) | Calendar dates, times of day and durations, like Python's datetime (naive values: no time zones). |
| [`difflib`](difflib.md) | Comparing sequences of lines (or characters): unified diffs, similarity ratios and close matches, like Python's difflib. |
| [`gfx`](gfx.md) | 2D graphics: canvases, anti-aliased shapes, text, images and a window. |
| [`glob`](glob.md) | Shell-style wildcards: matching names (Python's fnmatch) and finding files (Python's glob). |
| [`hashlib`](hashlib.md) | Message digests and checksums, like Python's hashlib, hmac and zlib.crc32. |
| [`heapq`](heapq.md) | Binary min-heaps kept in a plain list, like Python's heapq. |
| [`html`](html.md) | Escaping text for HTML, like Python's html. |
| [`http`](http.md) | HTTP/1.1 clients and servers, like Python's urllib.request and http.server. |
| [`itertools`](itertools.md) | Combining and slicing lists, like Python's itertools. |
| [`json`](json.md) | Reading and writing JSON. |
| [`logging`](logging.md) | Leveled log messages, like Python's logging. |
| [`math`](math.md) | Math functions backed by the C math library. |
| [`os`](os.md) | Operating-system services: environment, working directory, files and directories. |
| [`path`](path.md) | Path manipulation on strings, like Python's os.path. |
| [`random`](random.md) | Pseudo-random numbers, like Python's random module. |
| [`re`](re.md) | Regular expressions, like Python's re. |
| [`shutil`](shutil.md) | Copying, moving and removing whole files and trees, and finding programs, like Python's shutil. |
| [`socket`](socket.md) | TCP and UDP sockets over IPv4 and IPv6, like Python's socket. |
| [`statistics`](statistics.md) | Averages and spread of lists of numbers, like Python's statistics. |
| [`string`](string.md) | String constants and the helpers that str's built-in methods leave out. |
| [`subprocess`](subprocess.md) | Running other programs and capturing what they print. |
| [`sys`](sys.md) | The running program: its arguments, standard streams, exit and platform. |
| [`tempfile`](tempfile.md) | Temporary files and directories, like Python's tempfile. |
| [`testing`](testing.md) | Unit tests, like Python's unittest. |
| [`textwrap`](textwrap.md) | Wrapping and indenting paragraphs of text. |
| [`time`](time.md) | Clocks, sleeping, and calendar dates and times. |
| [`ui`](ui.md) | themed widgets for gfx windows, in the spirit of Tk's ttk. |
| [`url`](url.md) | splitting, joining, percent-encoding and query strings, like Python's urllib.parse. |
| [`uuid`](uuid.md) | Universally unique identifiers (RFC 9562), like Python's uuid. |
