// Binary trees, idiomatic C++: one heap allocation per node (std::unique_ptr).
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <algorithm>

struct Node { std::unique_ptr<Node> l, r; };

static std::unique_ptr<Node> build(int d) {
    auto n = std::make_unique<Node>();
    if (d > 0) { n->l = build(d - 1); n->r = build(d - 1); }
    return n;
}

static long check(const Node *n) { return n->l ? 1 + check(n->l.get()) + check(n->r.get()) : 1; }

int main(int argc, char **argv) {
    int n = argc > 1 ? std::atoi(argv[1]) : 10;
    int maxd = std::max(6, n);
    std::printf("stretch tree of depth %d\t check: %ld\n", maxd + 1, check(build(maxd + 1).get()));
    auto long_lived = build(maxd);
    for (int d = 4; d <= maxd; d += 2) {
        long iters = 1L << (maxd - d + 4), sum = 0;
        for (long i = 0; i < iters; i++) sum += check(build(d).get());
        std::printf("%ld\t trees of depth %d\t check: %ld\n", iters, d, sum);
    }
    std::printf("long lived tree of depth %d\t check: %ld\n", maxd, check(long_lived.get()));
}
