// Binary trees, C++ with the same layout as the Silly version: each tree is a
// std::vector of (left, right) index pairs.
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <vector>
#include <utility>
#include <algorithm>

using Tree = std::vector<std::pair<int32_t, int32_t>>;

static int32_t build(Tree &ns, int d) {
    if (d == 0) ns.push_back({-1, -1});
    else { int32_t l = build(ns, d - 1); int32_t r = build(ns, d - 1); ns.push_back({l, r}); }
    return (int32_t)ns.size() - 1;
}

static long check(const Tree &ns, int32_t i) {
    auto [l, r] = ns[i];
    return l < 0 ? 1 : 1 + check(ns, l) + check(ns, r);
}

static long tree_check(int d) { Tree t; build(t, d); return check(t, (int32_t)t.size() - 1); }

int main(int argc, char **argv) {
    int n = argc > 1 ? std::atoi(argv[1]) : 10;
    int maxd = std::max(6, n);
    std::printf("stretch tree of depth %d\t check: %ld\n", maxd + 1, tree_check(maxd + 1));
    Tree long_lived;
    build(long_lived, maxd);
    for (int d = 4; d <= maxd; d += 2) {
        long iters = 1L << (maxd - d + 4), sum = 0;
        for (long i = 0; i < iters; i++) sum += tree_check(d);
        std::printf("%ld\t trees of depth %d\t check: %ld\n", iters, d, sum);
    }
    std::printf("long lived tree of depth %d\t check: %ld\n", maxd, check(long_lived, (int32_t)long_lived.size() - 1));
}
