// Bounded allocator witness for the ROS Jazzy cycdeser C++ vector path.
// Both valid and malformed inputs run in-process with <256 MiB virtual memory
// limit imposed by CI.  Measures requested allocation, not RSS.
#include "serdes.hpp"
#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <new>
#include <string>
#include <vector>

namespace {
thread_local bool recording = false;
thread_local std::size_t largest_new = 0;
void record(std::size_t n) {
  if (recording) largest_new = std::max(largest_new,n);
}
}
void* operator new(std::size_t n) {
  record(n);
  if(void *p=std::malloc(n?n:1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete(void* p, std::size_t) noexcept {std::free(p);}
void* operator new[](std::size_t n) {
  record(n);
  if(void *p=std::malloc(n?n:1)) return p;
  throw std::bad_alloc{};
}
void operator delete[](void* p) noexcept {std::free(p);}
void operator delete[](void* p, std::size_t) noexcept {std::free(p);}

template<class T>
bool malformed(const char* name) {
  // 32 elements declared, but only 32 bytes after sequence length.
  // Valid int64 sequence would require 256 payload bytes; valid string
  // sequence needs >= 128 bytes of CDR length fields.
  std::vector<char> bytes(4+4+32, 0);
  bytes[1]=1;  // CDR little-endian encapsulation
  bytes[4]=32;
  cycdeser d(bytes.data(), bytes.size());
  std::vector<T> out;
  largest_new=0;
  recording=true;
  bool refused=false;
  try {d >> out;} catch (...) {refused=true;}
  recording=false;
  std::cout << name << " refused=" << refused
            << " peak_requested_new=" << largest_new
            << " input_bytes=" << bytes.size() << std::endl;
  return refused;
}

bool valid_uint64() {
  // CDR header + sequence length 2 + alignment pad 4 + two uint64.
  std::vector<char> bytes(4+4+4+16,0);
  bytes[1]=1;
  bytes[4]=2;
  bytes[12]=11;
  bytes[20]=13;
  cycdeser d(bytes.data(),bytes.size());
  std::vector<uint64_t> x;
  d >> x;
  bool ok=x.size()==2 && x[0]==11 && x[1]==13;
  std::cout << "valid_uint64=" << ok << std::endl;
  return ok;
}
int main() {
  bool a=malformed<uint64_t>("uint64_vector");
  bool b=malformed<std::string>("string_vector");
  bool c=valid_uint64();
  return (a&&b&&c)?0:2;
}
