// Word frequencies, idiomatic C++ (std::string, std::unordered_map).
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

int main(int argc, char **argv) {
    long n = argc > 1 ? std::atol(argv[1]) : 100000;
    std::vector<std::string> words;
    uint64_t s = 42;
    for (long i = 0; i < n; i++) {
        s = s * 6364136223846793005ull + 1442695040888963407ull;
        words.push_back("w" + std::to_string((s >> 33) % 50000));
    }
    std::string text;
    for (size_t i = 0; i < words.size(); i++) { if (i) text += ' '; text += words[i]; }
    std::unordered_map<std::string_view, long> counts;
    std::string_view rest = text;
    for (;;) {
        size_t sp = rest.find(' ');
        counts[rest.substr(0, sp)]++;
        if (sp == std::string_view::npos) break;
        rest.remove_prefix(sp + 1);
    }
    std::vector<std::pair<long, std::string_view>> ranked;
    for (auto &[w, c] : counts) ranked.push_back({-c, w});
    std::sort(ranked.begin(), ranked.end());
    std::printf("%zu\n", counts.size());
    for (int i = 0; i < 5; i++)
        std::printf("%.*s %ld\n", (int)ranked[i].second.size(), ranked[i].second.data(), -ranked[i].first);
}
