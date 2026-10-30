/* memtime: run a command, print "<wall seconds> <peak RSS KiB>" to stderr.
   A small parent keeps the child's inherited peak RSS (which survives exec) negligible. */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <sys/resource.h>
#include <sys/wait.h>

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: memtime cmd [args...]\n"); return 2; }
    struct timespec a, b;
    clock_gettime(CLOCK_MONOTONIC, &a);
    pid_t pid = fork();
    if (pid == 0) { execvp(argv[1], argv + 1); _exit(127); }
    int status; struct rusage ru;
    wait4(pid, &status, 0, &ru);
    clock_gettime(CLOCK_MONOTONIC, &b);
    fprintf(stderr, "%.6f %ld\n", (b.tv_sec - a.tv_sec) + (b.tv_nsec - a.tv_nsec) / 1e9, ru.ru_maxrss);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
