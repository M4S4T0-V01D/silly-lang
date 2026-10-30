// Sieve of Eratosthenes, idiomatic C++: std::vector<bool>-free byte buffer.
#include <cstdio>
#include <cstdlib>
#include <vector>

int main(int argc, char **argv) {
    long n = argc > 1 ? std::atol(argv[1]) : 1000000;
    std::vector<char> composite(n + 1, 0);
    long count = 0, last = 0;
    for (long i = 2; i <= n; i++) {
        if (!composite[i]) {
            count++; last = i;
            for (long j = i * i; j <= n; j += i) composite[j] = 1;
        }
    }
    std::printf("%ld %ld\n", count, last);
}
