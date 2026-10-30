# socket

TCP and UDP sockets over IPv4 and IPv6, like Python's socket.

```silly
import socket
fn main():
    let server = socket.listen(&"127.0.0.1", 0, 16).unwrap()
    let port = server.local_port()
    let t = spawn(fn() => socket.connect(&"127.0.0.1", port).unwrap().send(&"hi"))
    let c = server.accept().unwrap()
    print(c.recv(100).unwrap())               # hi
    t.join()
```

Every call that can fail returns a Result whose error says what went wrong
("connect: Connection refused"). recv returns "" once the other side has
closed the connection.

## Types

### `Socket`

An open socket: a TCP connection, a listening TCP socket or a UDP socket.

- `fd: int`

- `send(self, data: &str) -> Result[int, str]` — Sends all of data; the number of bytes sent.
- `recv(self, max: int) -> Result[str, str]` — Up to max bytes as they arrive; "" when the other side has closed.
- `recv_all(self) -> Result[str, str]` — Everything until the other side closes.
- `accept(self) -> Result[Socket, str]` — A connection from the queue of a listening socket (waits for one).
- `recvfrom(self, max: int) -> Result[(str, str, int), str]` — A datagram and the address and port it came from (UDP).
- `sendto(self, data: &str, host: &str, port: int) -> Result[int, str]` — Sends one datagram to host:port (UDP).
- `set_timeout(self, secs: f64) -> Result[bool, str]` — Makes recv, accept and send give up with an error after secs (0: wait forever).
- `ready(self, secs: f64) -> Result[bool, str]` — Whether there is something to recv (or accept) within secs; -1.0 waits forever.
- `shutdown(self) -> Result[bool, str]` — Says this side is done sending; the other side's recv then returns "".
- `close(self)`
- `peer(self) -> (str, int)` — The address and port of the other side.
- `local(self) -> (str, int)` — The address and port this socket is bound to.
- `local_port(self) -> int` — The local port (useful after listening on port 0, which picks a free one).

## Functions

### `connect(host: &str, port: int) -> Result[Socket, str]`

A TCP connection to host:port.

### `connect_timeout(host: &str, port: int, secs: f64) -> Result[Socket, str]`

Like connect, giving up after secs.

### `listen(host: &str, port: int, backlog: int) -> Result[Socket, str]`

A TCP socket listening on host:port ("" for every address, port 0 for any free port), queueing up to backlog connections.

### `udp_bind(host: &str, port: int) -> Result[Socket, str]`

A UDP socket bound to host:port, to receive datagrams on.

### `udp(host: &str) -> Result[Socket, str]`

An unbound UDP socket for sending to host's address family.

### `gethostbyname(host: &str) -> Result[str, str]`

The first address host resolves to ("localhost" -> "127.0.0.1").
