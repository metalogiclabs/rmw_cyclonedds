// Native, bounded CDR sequence preallocation probe.
// No actual crash attempt or oversized allocation is necessary.
#include "serdes.hpp"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <new>
#include <string>
#include <vector>

namespace {
thread_local bool monitoring = false;
thread_local std::size_t maximum_requested = 0;
void record(std::size_t n) {
  if (monitoring) maximum_requested = std::max(maximum_requested, n);
}
}
void* operator new(std::size_t n) {
  record(n);
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void* operator new[](std::size_t n) {
  record(n);
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

template<typename T>
bool truncated_sequence(const char* name) {
  // At least one byte per element is available, but insufficient for the
  // declared 8192 uint64 or std::string elements.
  const std::size_t n = 8192;
  std::vector<char> cdr(4 + 4 + n, 0);
  cdr[1] = 1;  // CDR little-endian
  cdr[4] = 0; cdr[5] = 0x20; // 0x2000 in little-endian
  cycdeser d(cdr.data(), cdr.size());
  std::vector<T> output;
  bool rejected = false;
  maximum_requested = 0;
  monitoring = true;
  try { d >> output; } catch (const std::exception&) { rejected = true; }
  monitoring = false;
  std::cout << name << " rejected=" << rejected
            << " peak_requested=" << maximum_requested
            << " input_bytes=" << cdr.size() << std::endl;
  return rejected;
}

bool valid_uint64() {
  std::vector<char> cdr(4 + 4 + 4 + 16, 0);
  cdr[1] = 1; cdr[4] = 2; cdr[12] = 11; cdr[20] = 13;
  cycdeser d(cdr.data(), cdr.size());
  std::vector<uint64_t> out;
  d >> out;
  bool ok = (out.size() == 2 && out[0] == 11 && out[1] == 13);
  std::cout << "valid_uint64=" << ok << std::endl;
  return ok;
}

bool valid_string() {
  std::vector<char> cdr(4 + 4 + 4 + 2, 0);
  cdr[1] = 1; cdr[4] = 1; cdr[8] = 2; cdr[12] = 'a';
  cycdeser d(cdr.data(), cdr.size());
  std::vector<std::string> out;
  d >> out;
  bool ok = (out.size() == 1 && out[0] == "a");
  std::cout << "valid_string=" << ok << std::endl;
  return ok;
}

int main() {
  try {
    bool a = truncated_sequence<uint64_t>("uint64");
    bool b = truncated_sequence<std::string>("string");
    bool c = valid_uint64();
    bool d = valid_string();
    return (a && b && c && d) ? 0 : 2;
  } catch (const std::exception& e) {
    std::cerr << "harness-exception: " << e.what() << std::endl;
    return 3;
  }
}
