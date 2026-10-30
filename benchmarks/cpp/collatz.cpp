// Short-lived lists, idiomatic C++: a std::vector per start value.
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <vector>

static std::vector<int64_t> path(int64_t start) {
    std::vector<int64_t> out;
    int64_t x = start;
    while (x != 1) { out.push_back(x); x = x % 2 == 0 ? x / 2 : 3 * x + 1; }
    out.push_back(1);
    return out;
}

int main(int argc, char **argv) {
    int64_t n = argc > 1 ? std::atoll(argv[1]) : 100000;
    int64_t longest = 0, arg = 0, peak_sum = 0;
    for (int64_t i = 1; i < n; i++) {
        auto p = path(i);
        int64_t peak = 0;
        for (int64_t v : p) if (v > peak) peak = v;
        peak_sum += peak;
        if ((int64_t)p.size() > longest) { longest = p.size(); arg = i; }
    }
    std::printf("%ld %ld %ld\n", (long)arg, (long)longest, (long)peak_sum);
}
