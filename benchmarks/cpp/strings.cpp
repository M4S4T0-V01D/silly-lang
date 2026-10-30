// Small strings, idiomatic C++: std::string formatting, splitting into a vector, parsing.
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

static std::vector<std::string> split(const std::string &s, char sep) {
    std::vector<std::string> out;
    size_t start = 0;
    for (;;) {
        size_t p = s.find(sep, start);
        out.push_back(s.substr(start, p - start));
        if (p == std::string::npos) return out;
        start = p + 1;
    }
}

int main(int argc, char **argv) {
    long n = argc > 1 ? std::atol(argv[1]) : 100000;
    long total = 0, chars = 0;
    for (long i = 0; i < n; i++) {
        std::string rec = "id" + std::to_string(i) + ":" + std::to_string(i * 7 % 1000) + ":" + std::to_string(i % 13);
        chars += rec.size();
        auto parts = split(rec, ':');
        total += std::stol(parts[1]) * std::stol(parts[2]);
        if (parts[0].size() >= 2 && parts[0].compare(parts[0].size() - 2, 2, "99") == 0) total += 1;
    }
    std::printf("%ld %ld\n", total, chars);
}
