/* Native layer of the os, sys, time and subprocess modules: thin POSIX wrappers. */
#include <dirent.h>
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int os_errno;

static sl_str os_str(const char *s) {
    size_t n = strlen(s);
    uint8_t *p = sl_alloc(n + 1);
    memcpy(p, s, n + 1);
    return (sl_str){p, (int64_t)n};
}

/* Lists cross the FFI as one string of NUL-terminated items. */
static void os_item(sl_sb *b, const char *s) {
    (void)b;
    size_t n = strlen(s) + 1;
    memcpy(sl_room(n), s, n);
    sl_ds.top += n;
}

static bool os_ok(int r) {
    if (r != 0) os_errno = errno;
    return r == 0;
}

static sl_str os_error(void) { return os_str(strerror(os_errno)); }
static int64_t os_errno_code(void) { return os_errno; }

/* ---- environment ---- */

static bool os_has_env(sl_str k) { return getenv(sl_cstr(k)) != NULL; }

static sl_str os_getenv(sl_str k) {
    const char *v = getenv(sl_cstr(k));
    return v ? os_str(v) : (sl_str){(const uint8_t *)"", 0};
}

static bool os_setenv(sl_str k, sl_str v) { return os_ok(setenv(sl_cstr(k), sl_cstr(v), 1)); }
static bool os_unsetenv(sl_str k) { return os_ok(unsetenv(sl_cstr(k))); }

extern char **environ;
static sl_str os_environ(void) {
    sl_sb b = sl_sb_begin();
    for (char **e = environ; *e; e++) os_item(&b, *e);
    return sl_sb_end(b);
}

/* ---- process ---- */

static int64_t os_getpid(void) { return getpid(); }
static int64_t os_getppid(void) { return getppid(); }
static int64_t os_getuid(void) { return getuid(); }

static sl_str os_getcwd(void) {
    char buf[4096];
    if (!getcwd(buf, sizeof buf)) { os_errno = errno; return (sl_str){(const uint8_t *)"", 0}; }
    return os_str(buf);
}

static bool os_chdir(sl_str p) { return os_ok(chdir(sl_cstr(p))); }

static int64_t os_system(sl_str cmd) {
    fflush(stdout);
    fflush(stderr);
    int r = system(sl_cstr(cmd));
    if (r == -1) { os_errno = errno; return -1; }
    return WIFEXITED(r) ? WEXITSTATUS(r) : 128 + WTERMSIG(r);
}

static sl_str os_hostname(void) {
    char buf[256];
    if (gethostname(buf, sizeof buf) != 0) return os_str("");
    buf[sizeof buf - 1] = 0;
    return os_str(buf);
}

static sl_str os_uname(int64_t field) {
    struct utsname u;
    if (uname(&u) != 0) return os_str("");
    switch (field) {
    case 0: return os_str(u.sysname);
    case 1: return os_str(u.release);
    case 2: return os_str(u.machine);
    default: return os_str(u.version);
    }
}

/* ---- files and directories ---- */

static bool os_list_ok;
static bool os_listed(void) { return os_list_ok; }

static sl_str os_listdir(sl_str p) {
    const char *path = sl_cstr(p);
    os_list_ok = false;
    DIR *d = opendir(path);
    if (!d) { os_errno = errno; return (sl_str){(const uint8_t *)"", 0}; }
    sl_sb b = sl_sb_begin();
    struct dirent *e;
    while ((e = readdir(d))) {
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        os_item(&b, e->d_name);
    }
    closedir(d);
    os_list_ok = true;
    return sl_sb_end(b);
}

static bool os_mkdir(sl_str p) { return os_ok(mkdir(sl_cstr(p), 0777)); }
static bool os_rmdir(sl_str p) { return os_ok(rmdir(sl_cstr(p))); }
static bool os_remove(sl_str p) { return os_ok(unlink(sl_cstr(p))); }
static bool os_rename(sl_str a, sl_str b) { return os_ok(rename(sl_cstr(a), sl_cstr(b))); }
static bool os_symlink(sl_str target, sl_str p) { return os_ok(symlink(sl_cstr(target), sl_cstr(p))); }
static bool os_chmod(sl_str p, int64_t mode) { return os_ok(chmod(sl_cstr(p), (mode_t)mode)); }

/* kind: 0 missing, 1 file, 2 directory, 3 other; follow=false looks at a link itself */
static int64_t os_kind(sl_str p, bool follow) {
    struct stat st;
    int r = follow ? stat(sl_cstr(p), &st) : lstat(sl_cstr(p), &st);
    if (r != 0) { os_errno = errno; return 0; }
    if (S_ISREG(st.st_mode)) return 1;
    if (S_ISDIR(st.st_mode)) return 2;
    if (S_ISLNK(st.st_mode)) return 4;
    return 3;
}

/* field: 0 size, 1 mtime (ns), 2 mode, 3 atime (ns), 4 ctime (ns); -1 on error */
static int64_t os_stat(sl_str p, int64_t field) {
    struct stat st;
    if (stat(sl_cstr(p), &st) != 0) { os_errno = errno; return -1; }
    switch (field) {
    case 0: return st.st_size;
    case 1: return (int64_t)st.st_mtim.tv_sec * 1000000000 + st.st_mtim.tv_nsec;
    case 2: return st.st_mode & 07777;
    case 3: return (int64_t)st.st_atim.tv_sec * 1000000000 + st.st_atim.tv_nsec;
    default: return (int64_t)st.st_ctim.tv_sec * 1000000000 + st.st_ctim.tv_nsec;
    }
}

static sl_str os_realpath(sl_str p) {
    char *r = realpath(sl_cstr(p), NULL);
    if (!r) { os_errno = errno; return (sl_str){(const uint8_t *)"", 0}; }
    sl_str s = os_str(r);
    free(r);
    return s;
}

static sl_str os_readlink(sl_str p) {
    char buf[4096];
    ssize_t n = readlink(sl_cstr(p), buf, sizeof buf - 1);
    if (n < 0) { os_errno = errno; return (sl_str){(const uint8_t *)"", 0}; }
    buf[n] = 0;
    return os_str(buf);
}

static bool os_append_file(sl_str p, sl_str data) {
    FILE *f = fopen(sl_cstr(p), "ab");
    if (!f) { os_errno = errno; return false; }
    bool ok = fwrite(data.p, 1, (size_t)data.n, f) == (size_t)data.n;
    if (fclose(f) != 0) ok = false;
    if (!ok) os_errno = errno;
    return ok;
}

static sl_str os_tmpdir(void) {
    const char *t = getenv("TMPDIR");
    return os_str(t && *t ? t : "/tmp");
}

static sl_str os_mkdtemp(sl_str prefix) {
    const char *base = getenv("TMPDIR");
    if (!base || !*base) base = "/tmp";
    const char *pre = sl_cstr(prefix);
    size_t n = strlen(base) + strlen(pre) + 16;
    char *t = sl_alloc(n);
    snprintf(t, n, "%s/%sXXXXXX", base, pre);
    if (!mkdtemp(t)) { os_errno = errno; return (sl_str){(const uint8_t *)"", 0}; }
    return (sl_str){(const uint8_t *)t, (int64_t)strlen(t)};
}

/* ---- standard streams ---- */

static void os_write_err(sl_str s) { fwrite(s.p, 1, (size_t)s.n, stderr); }
static void os_write_out(sl_str s) { fwrite(s.p, 1, (size_t)s.n, stdout); }
static void os_flush(void) { fflush(stdout); fflush(stderr); }
static bool os_isatty(int64_t fd) { return isatty((int)fd); }

static sl_str os_read_stdin(void) {
    sl_sb b = sl_sb_begin();
    size_t got;
    while (1) {
        uint8_t *t = sl_room(1 << 16);
        got = fread(t, 1, 1 << 16, stdin);
        sl_ds.top = t + got;
        if (got < (1 << 16)) break;
    }
    return sl_sb_end(b);
}

/* ---- time ---- */

static double os_time(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int64_t os_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}

static int64_t os_monotonic_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}

static void os_sleep(double s) {
    if (s <= 0) return;
    struct timespec ts = {(time_t)s, (long)((s - (double)(time_t)s) * 1e9)};
    while (nanosleep(&ts, &ts) != 0 && errno == EINTR) {}
}

/* Broken-down time of a Unix timestamp; field 0..8 = year, month (1-12), day, hour,
   minute, second, weekday (0 = Monday), yearday (1-366), utc offset in seconds. */
static int64_t os_tm(int64_t t, bool local, int64_t field) {
    time_t tt = (time_t)t;
    struct tm m;
    if (local) localtime_r(&tt, &m); else gmtime_r(&tt, &m);
    switch (field) {
    case 0: return m.tm_year + 1900;
    case 1: return m.tm_mon + 1;
    case 2: return m.tm_mday;
    case 3: return m.tm_hour;
    case 4: return m.tm_min;
    case 5: return m.tm_sec;
    case 6: return (m.tm_wday + 6) % 7;
    case 7: return m.tm_yday + 1;
    default: return local ? m.tm_gmtoff : 0;
    }
}

static sl_str os_strftime(sl_str fmt, int64_t t, bool local) {
    time_t tt = (time_t)t;
    struct tm m;
    if (local) localtime_r(&tt, &m); else gmtime_r(&tt, &m);
    char buf[512];
    size_t n = strftime(buf, sizeof buf, sl_cstr(fmt), &m);
    buf[n] = 0;
    return os_str(buf);
}

/* Unix timestamp of a local date and time (mktime), or of a UTC one (timegm). */
static int64_t os_mktime(int64_t y, int64_t mo, int64_t d, int64_t h, int64_t mi, int64_t s, bool local) {
    struct tm m = {0};
    m.tm_year = (int)y - 1900; m.tm_mon = (int)mo - 1; m.tm_mday = (int)d;
    m.tm_hour = (int)h; m.tm_min = (int)mi; m.tm_sec = (int)s; m.tm_isdst = -1;
    return local ? (int64_t)mktime(&m) : (int64_t)timegm(&m);
}

/* ---- subprocess: run a command through /bin/sh, capturing its output ---- */

static int64_t os_run(sl_str cmd, sl_str input, bool feed, sl_str *out, sl_str *err) {
    int pin[2], pout[2], perr[2];
    if (pipe(pin) || pipe(pout) || pipe(perr)) { os_errno = errno; return -1; }
    fflush(stdout);
    fflush(stderr);
    pid_t pid = fork();
    if (pid < 0) { os_errno = errno; return -1; }
    if (pid == 0) {
        dup2(pin[0], 0); dup2(pout[1], 1); dup2(perr[1], 2);
        close(pin[0]); close(pin[1]); close(pout[0]); close(pout[1]); close(perr[0]); close(perr[1]);
        execl("/bin/sh", "sh", "-c", sl_cstr(cmd), (char *)NULL);
        _exit(127);
    }
    close(pin[0]); close(pout[1]); close(perr[1]);
    void (*old_pipe)(int) = signal(SIGPIPE, SIG_IGN);
    /* feed stdin and drain both pipes together so no side can block the other */
    int64_t off = feed ? 0 : input.n;
    if (off >= input.n) { close(pin[1]); pin[1] = -1; }
    size_t cap[2] = {4096, 4096}, len[2] = {0, 0};
    char *buf[2] = {malloc(cap[0]), malloc(cap[1])};
    int fds[2] = {pout[0], perr[0]};
    while (fds[0] >= 0 || fds[1] >= 0 || pin[1] >= 0) {
        fd_set rd, wr;
        FD_ZERO(&rd); FD_ZERO(&wr);
        int mx = -1;
        for (int i = 0; i < 2; i++) if (fds[i] >= 0) { FD_SET(fds[i], &rd); if (fds[i] > mx) mx = fds[i]; }
        if (pin[1] >= 0) { FD_SET(pin[1], &wr); if (pin[1] > mx) mx = pin[1]; }
        if (select(mx + 1, &rd, &wr, NULL, NULL) < 0) { if (errno == EINTR) continue; break; }
        if (pin[1] >= 0 && FD_ISSET(pin[1], &wr)) {
            ssize_t w = write(pin[1], input.p + off, (size_t)(input.n - off));
            if (w > 0) off += w;
            if (w <= 0 || off >= input.n) { close(pin[1]); pin[1] = -1; }
        }
        for (int i = 0; i < 2; i++) {
            if (fds[i] < 0 || !FD_ISSET(fds[i], &rd)) continue;
            if (cap[i] - len[i] < 4096) buf[i] = realloc(buf[i], cap[i] *= 2);
            ssize_t r = read(fds[i], buf[i] + len[i], cap[i] - len[i]);
            if (r > 0) len[i] += (size_t)r;
            else { close(fds[i]); fds[i] = -1; }
        }
    }
    signal(SIGPIPE, old_pipe);
    int st;
    while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {}
    sl_str *dst[2] = {out, err};
    for (int i = 0; i < 2; i++) {
        uint8_t *p = sl_alloc(len[i] + 1);
        memcpy(p, buf[i], len[i]);
        *dst[i] = (sl_str){p, (int64_t)len[i]};
        free(buf[i]);
    }
    return WIFEXITED(st) ? WEXITSTATUS(st) : 128 + WTERMSIG(st);
}

static sl_str os_run_out;
static sl_str os_run_err;

static int64_t os_run_capture(sl_str cmd, sl_str input, bool feed) {
    return os_run(cmd, input, feed, &os_run_out, &os_run_err);
}

static sl_str os_run_stdout(void) { return os_run_out; }
static sl_str os_run_stderr(void) { return os_run_err; }

/* ---- exit (sys.exit shadows the builtin inside its own module) ---- */

static void os_exit(int64_t code) {
    fflush(stdout);
    fflush(stderr);
    exit((int)code);
}
