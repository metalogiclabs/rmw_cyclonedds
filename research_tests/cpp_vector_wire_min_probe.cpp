// Bounded native differential for CDR vector count-before-allocation.
// Each arm runs under <=256 MiB container memory; no large allocation needed.
#include "serdes.hpp"
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <new>
#include <string>
#include <vector>

static thread_local bool track = false;
static thread_local size_t maximum_requested = 0;
void* operator new(size_t n) {
  if (track) maximum_requested = std::max(maximum_requested, n);
  if (void* p = std::malloc(n == 0 ? 1 : n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, size_t) noexcept { std::free(p); }
void* operator new[](size_t n) {
  if (track) maximum_requested = std::max(maximum_requested, n);
  if (void* p = std::malloc(n == 0 ? 1 : n)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, size_t) noexcept { std::free(p); }

template<class T>
bool malformed(const char* name) {
  // CDR encapsulation + count=32 + just 32 payload bytes.
  // uint64 needs 256 wire bytes (plus alignment), string needs >=128.
  std::vector<char> data(4 + 4 + 32, 0);
  data[1] = 1;
  data[4] = 32;
  cycdeser reader(data.data(), data.size());
  std::vector<T> values;
  maximum_requested = 0;
  track = true;
  bool refused = false;
  try { reader >> values; } catch (...) { refused = true; }
  track = false;
  std::cout << name << " refused=" << refused
            << " max_new=" << maximum_requested
            << " bytes=" << data.size() << '\n';
  return refused;
}

bool valid_uint64() {
  std::vector<char> data(4+4+4+16, 0); data[1]=1; data[4]=2;
  data[12]=11; data[20]=13;
  cycdeser reader(data.data(), data.size());
  std::vector<uint64_t> v;
  reader >> v;
  bool ok = v.size()==2 && v[0]==11 && v[1]==13;
  std::cout << "valid_uint64=" << ok << '\n';
  return ok;
}

bool valid_string() {
  // CDR header, sequence size=1, string length=2, ASCII character + NUL.
  std::vector<char> data(4+4+4+2,0); data[1]=1; data[4]=1;
  data[8]=2; data[12]='A';
  cycdeser reader(data.data(),data.size());
  std::vector<std::string> v;
  reader >> v;
  bool ok=v.size()==1 && v[0]=="A";
  std::cout << "valid_string=" << ok << '\n';
  return ok;
}

bool valid_chars() {
  std::vector<char> data(4+4+32,0); data[1]=1; data[4]=32;
  cycdeser reader(data.data(),data.size());
  std::vector<uint8_t> v;
  reader >> v;
  bool ok=v.size()==32 && std::all_of(v.begin(),v.end(),[](uint8_t x){return x==0;});
  std::cout << "valid_chars=" << ok << '\n';
  return ok;
}

int main() {
  bool ok = malformed<uint64_t>("bad_uint64");
  ok = malformed<std::string>("bad_string") && ok;
  ok = valid_uint64() && ok;
  ok = valid_string() && ok;
  ok = valid_chars() && ok;
  return ok ? 0 : 2;
}
