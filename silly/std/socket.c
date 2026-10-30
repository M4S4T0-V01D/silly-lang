/* Native layer of socket.silly: BSD sockets for TCP and UDP over IPv4 and IPv6.
   Calls return -1 (or an empty string with sk_failed() set) on failure, and
   sk_error() describes the last failure on this thread. */
#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <poll.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif

static _Thread_local char sk_msg[256];
static _Thread_local bool sk_bad;

static sl_str sk_str(const char *s, size_t n) {
    uint8_t *p = sl_alloc(n + 1);
    memcpy(p, s, n);
    p[n] = 0;
    return (sl_str){p, (int64_t)n};
}

static int64_t sk_fail(const char *what) {
    bool late = errno == EAGAIN || errno == EWOULDBLOCK;
    snprintf(sk_msg, sizeof sk_msg, "%s: %s", what, late ? "timed out" : strerror(errno));
    sk_bad = true;
    return -1;
}

static sl_str sk_error(void) { return sk_str(sk_msg, strlen(sk_msg)); }
static bool sk_failed(void) { return sk_bad; }

static void sk_nosigpipe(int fd) {
#ifdef SO_NOSIGPIPE
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
#else
    (void)fd;
#endif
}

/* Resolves host:port; on failure fills sk_msg and returns NULL. An empty host
   means every local address (for bind). */
static struct addrinfo *sk_resolve(sl_str host, int64_t port, int type, bool passive) {
    struct addrinfo hints = {0}, *res = NULL;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = type;
    if (passive) hints.ai_flags = AI_PASSIVE;
    char ps[16];
    snprintf(ps, sizeof ps, "%lld", (long long)port);
    const char *h = host.n ? sl_cstr(host) : NULL;
    int r = getaddrinfo(h, ps, &hints, &res);
    if (r != 0) {
        snprintf(sk_msg, sizeof sk_msg, "%s: %s", host.n ? h : "*", gai_strerror(r));
        sk_bad = true;
        return NULL;
    }
    return res;
}

/* A connected TCP socket, trying each address of host in turn. */
static int64_t sk_connect(sl_str host, int64_t port, double timeout) {
    sk_bad = false;
    struct addrinfo *res = sk_resolve(host, port, SOCK_STREAM, false);
    if (!res) return -1;
    int fd = -1;
    for (struct addrinfo *a = res; a; a = a->ai_next) {
        fd = socket(a->ai_family, a->ai_socktype, a->ai_protocol);
        if (fd < 0) continue;
        if (timeout > 0) {
            struct timeval tv = {(time_t)timeout, (suseconds_t)((timeout - (time_t)timeout) * 1e6)};
            setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
        }
        if (connect(fd, a->ai_addr, a->ai_addrlen) == 0) break;
        sk_fail("connect");
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) return -1;
    sk_bad = false;
    sk_nosigpipe(fd);
    int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    return fd;
}

/* A socket bound to host:port; listening if it's TCP. */
static int64_t sk_bind(sl_str host, int64_t port, bool tcp, int64_t backlog) {
    sk_bad = false;
    struct addrinfo *res = sk_resolve(host, port, tcp ? SOCK_STREAM : SOCK_DGRAM, true);
    if (!res) return -1;
    int fd = -1;
    for (struct addrinfo *a = res; a; a = a->ai_next) {
        fd = socket(a->ai_family, a->ai_socktype, a->ai_protocol);
        if (fd < 0) continue;
        int one = 1;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
        if (bind(fd, a->ai_addr, a->ai_addrlen) == 0 && (!tcp || listen(fd, (int)backlog) == 0)) break;
        sk_fail(tcp ? "listen" : "bind");
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) return -1;
    sk_bad = false;
    sk_nosigpipe(fd);
    return fd;
}

static _Thread_local char sk_peer_buf[INET6_ADDRSTRLEN];
static _Thread_local int64_t sk_peer_port;

static void sk_note_addr(struct sockaddr_storage *ss) {
    sk_peer_buf[0] = 0;
    sk_peer_port = 0;
    if (ss->ss_family == AF_INET) {
        struct sockaddr_in *s = (struct sockaddr_in *)ss;
        inet_ntop(AF_INET, &s->sin_addr, sk_peer_buf, sizeof sk_peer_buf);
        sk_peer_port = ntohs(s->sin_port);
    } else if (ss->ss_family == AF_INET6) {
        struct sockaddr_in6 *s = (struct sockaddr_in6 *)ss;
        inet_ntop(AF_INET6, &s->sin6_addr, sk_peer_buf, sizeof sk_peer_buf);
        sk_peer_port = ntohs(s->sin6_port);
    }
}

/* The address noted by the last accept, recvfrom, peer or local call. */
static sl_str sk_addr(void) { return sk_str(sk_peer_buf, strlen(sk_peer_buf)); }
static int64_t sk_port(void) { return sk_peer_port; }

static int64_t sk_accept(int64_t fd) {
    sk_bad = false;
    struct sockaddr_storage ss;
    socklen_t n = sizeof ss;
    int c;
    do c = accept((int)fd, (struct sockaddr *)&ss, &n); while (c < 0 && errno == EINTR);
    if (c < 0) return sk_fail("accept");
    sk_note_addr(&ss);
    sk_nosigpipe(c);
    return c;
}

static bool sk_peer(int64_t fd) {
    struct sockaddr_storage ss;
    socklen_t n = sizeof ss;
    if (getpeername((int)fd, (struct sockaddr *)&ss, &n) != 0) { sk_fail("getpeername"); return false; }
    sk_note_addr(&ss);
    return true;
}

static bool sk_local(int64_t fd) {
    struct sockaddr_storage ss;
    socklen_t n = sizeof ss;
    if (getsockname((int)fd, (struct sockaddr *)&ss, &n) != 0) { sk_fail("getsockname"); return false; }
    sk_note_addr(&ss);
    return true;
}

/* Sends all of data; the count sent, or -1. */
static int64_t sk_send(int64_t fd, sl_str data) {
    sk_bad = false;
    int64_t done = 0;
    while (done < data.n) {
        ssize_t r = send((int)fd, data.p + done, (size_t)(data.n - done), MSG_NOSIGNAL);
        if (r < 0) {
            if (errno == EINTR) continue;
            return sk_fail("send");
        }
        done += r;
    }
    return done;
}

/* Up to max bytes; "" at the end of the stream (sk_failed tells them apart). */
static sl_str sk_recv(int64_t fd, int64_t max) {
    sk_bad = false;
    if (max <= 0) max = 65536;
    uint8_t *p = sl_alloc((size_t)max + 1);
    ssize_t r;
    do r = recv((int)fd, p, (size_t)max, 0); while (r < 0 && errno == EINTR);
    if (r < 0) {
        sk_fail("recv");
        r = 0;
    }
    p[r] = 0;
    return (sl_str){p, (int64_t)r};
}

static int64_t sk_sendto(int64_t fd, sl_str data, sl_str host, int64_t port) {
    sk_bad = false;
    struct addrinfo *res = sk_resolve(host, port, SOCK_DGRAM, false);
    if (!res) return -1;
    ssize_t r = sendto((int)fd, data.p, (size_t)data.n, MSG_NOSIGNAL, res->ai_addr, res->ai_addrlen);
    freeaddrinfo(res);
    if (r < 0) return sk_fail("sendto");
    return r;
}

static sl_str sk_recvfrom(int64_t fd, int64_t max) {
    sk_bad = false;
    if (max <= 0) max = 65536;
    uint8_t *p = sl_alloc((size_t)max + 1);
    struct sockaddr_storage ss;
    socklen_t n = sizeof ss;
    ssize_t r;
    do r = recvfrom((int)fd, p, (size_t)max, 0, (struct sockaddr *)&ss, &n); while (r < 0 && errno == EINTR);
    if (r < 0) {
        sk_fail("recvfrom");
        r = 0;
    } else {
        sk_note_addr(&ss);
    }
    p[r] = 0;
    return (sl_str){p, (int64_t)r};
}

/* An unbound UDP socket for sending, of the family host resolves to. */
static int64_t sk_udp(sl_str host) {
    sk_bad = false;
    struct addrinfo *res = sk_resolve(host, 0, SOCK_DGRAM, false);
    if (!res) return -1;
    int fd = socket(res->ai_family, SOCK_DGRAM, 0);
    freeaddrinfo(res);
    if (fd < 0) return sk_fail("socket");
    return fd;
}

static bool sk_timeout(int64_t fd, double secs) {
    struct timeval tv = {0, 0};
    if (secs > 0) {
        tv.tv_sec = (time_t)secs;
        tv.tv_usec = (suseconds_t)((secs - (double)tv.tv_sec) * 1e6);
    }
    if (setsockopt((int)fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv) != 0 ||
        setsockopt((int)fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv) != 0) {
        sk_fail("setsockopt");
        return false;
    }
    return true;
}

/* Whether fd has data (or a connection) within secs; -1 on error. */
static int64_t sk_ready(int64_t fd, double secs) {
    struct pollfd p = {(int)fd, POLLIN, 0};
    int r;
    do r = poll(&p, 1, secs < 0 ? -1 : (int)(secs * 1000)); while (r < 0 && errno == EINTR);
    if (r < 0) return sk_fail("poll");
    return r > 0;
}

static bool sk_shutdown(int64_t fd) {
    if (shutdown((int)fd, SHUT_WR) != 0) { sk_fail("shutdown"); return false; }
    return true;
}

static void sk_close(int64_t fd) { close((int)fd); }

/* The first address host resolves to, as text; IPv4 ones first. */
static sl_str sk_lookup(sl_str host) {
    sk_bad = false;
    struct addrinfo *res = sk_resolve(host, 0, SOCK_STREAM, false);
    if (!res) return sk_str("", 0);
    struct addrinfo *pick = res;
    for (struct addrinfo *a = res; a; a = a->ai_next)
        if (a->ai_family == AF_INET) { pick = a; break; }
    struct sockaddr_storage ss;
    memcpy(&ss, pick->ai_addr, pick->ai_addrlen);
    freeaddrinfo(res);
    sk_note_addr(&ss);
    return sk_addr();
}
