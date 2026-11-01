// Source-native RMW C++ allocation request versus resident/virtual memory witness.
// Deliberately restricted to one deterministic malformed uint64 sequence family.
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <test_msgs/msg/unbounded_sequences.hpp>
#include <sys/resource.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <new>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
thread_local bool tracking = false;
thread_local std::size_t max_request = 0;
thread_local std::size_t request_count = 0;
thread_local std::size_t large_request_count = 0;
thread_local std::size_t total_requested = 0;

void track(std::size_t bytes) noexcept
{
  if (!tracking) return;
  max_request = std::max(max_request, bytes);
  ++request_count;
  if (bytes >= 4096) ++large_request_count;
  total_requested = bytes > std::numeric_limits<std::size_t>::max() - total_requested ?
    std::numeric_limits<std::size_t>::max() : total_requested + bytes;
}

std::size_t status_kib(const std::string & name)
{
  std::ifstream file("/proc/self/status");
  std::string line;
  while (std::getline(file, line)) {
    if (line.compare(0, name.size() + 1, name + ":") == 0) {
      std::istringstream input(line.substr(name.size() + 1));
      std::size_t value = 0;
      if (input >> value) return value;
    }
  }
  throw std::runtime_error("missing Linux /proc metric: " + name);
}

std::size_t peak_rss_kib()
{
  struct rusage usage {};
  if (getrusage(RUSAGE_SELF, &usage) != 0) throw std::runtime_error("getrusage failed");
  return static_cast<std::size_t>(usage.ru_maxrss);  // Linux KiB.
}

std::string mapped_library()
{
  std::ifstream maps("/proc/self/maps");
  std::string line;
  while (std::getline(maps, line)) {
    if (line.find("librmw_cyclonedds_cpp.so") != std::string::npos) {
      const auto start = line.find('/');
      if (start != std::string::npos) return line.substr(start);
    }
  }
  throw std::runtime_error("native Cyclone RMW library was not mapped");
}

std::uint64_t fnv1a(const std::vector<std::uint8_t> & bytes)
{
  std::uint64_t value = 14695981039346656037ULL;
  for (auto byte : bytes) {
    value ^= byte;
    value *= 1099511628211ULL;
  }
  return value;
}
}

void * operator new(std::size_t n)
{
  track(n);
  if (void * ptr = std::malloc(n ? n : 1)) return ptr;
  throw std::bad_alloc();
}
void operator delete(void * ptr) noexcept {std::free(ptr);}
void operator delete(void * ptr, std::size_t) noexcept {std::free(ptr);}
void * operator new[](std::size_t n)
{
  track(n);
  if (void * ptr = std::malloc(n ? n : 1)) return ptr;
  throw std::bad_alloc();
}
void operator delete[](void * ptr) noexcept {std::free(ptr);}
void operator delete[](void * ptr, std::size_t) noexcept {std::free(ptr);}

int main(int argc, char ** argv)
{
  try {
    if (argc != 3) throw std::runtime_error("usage: witness MODE COUNT");
    const std::string mode = argv[1];
    const auto count = static_cast<std::size_t>(std::stoull(argv[2]));
    if (!((mode == "valid" && count == 8) ||
      (mode == "malformed" && (count == 8192 || count == 65536 || count == 262144))))
    {
      throw std::runtime_error("unapproved mode or count");
    }

    using Msg = test_msgs::msg::UnboundedSequences;
    rclcpp::Serialization<Msg> coder;
    std::vector<std::uint8_t> wire;
    if (mode == "valid") {
      Msg control;
      control.uint64_values = {1, 2, 3, 5, 8, 13, 21, 34};
      rclcpp::SerializedMessage serialized;
      coder.serialize_message(&control, &serialized);
      const auto & raw = serialized.get_rcl_serialized_message();
      wire.assign(raw.buffer, raw.buffer + raw.buffer_length);
    } else {
      // 12 preceding empty sequence counts, then forged uint64 count.
      // Only one byte per claimed uint64 value follows: impossible by CDR.
      const std::size_t offset = 4 + 12 * 4;
      wire.assign(offset + 4 + 4 + count, 0);
      wire[1] = 1;  // little-endian encapsulation
      wire[offset] = static_cast<std::uint8_t>(count & 255);
      wire[offset + 1] = static_cast<std::uint8_t>((count >> 8) & 255);
      wire[offset + 2] = static_cast<std::uint8_t>((count >> 16) & 255);
      wire[offset + 3] = static_cast<std::uint8_t>((count >> 24) & 255);
    }

    rclcpp::SerializedMessage serialized(wire.size());
    auto & raw = serialized.get_rcl_serialized_message();
    std::memcpy(raw.buffer, wire.data(), wire.size());
    raw.buffer_length = wire.size();
    Msg parsed;

    const auto rss_before = status_kib("VmRSS");
    const auto virtual_before = status_kib("VmSize");
    const auto maxrss_before = peak_rss_kib();
    max_request = request_count = large_request_count = total_requested = 0;
    tracking = true;
    bool rejected = false;
    try {
      coder.deserialize_message(&serialized, &parsed);
    } catch (const std::exception &) {
      rejected = true;
    }
    tracking = false;

    const auto rss_after = status_kib("VmRSS");
    const auto virtual_after = status_kib("VmSize");
    const auto peak_virtual = status_kib("VmPeak");
    const auto peak_resident = peak_rss_kib();
    const auto library = mapped_library();
    const char * expected = std::getenv("EXPECTED_LIB_DIR");
    if (!expected || library.find(std::string(expected) + "/") != 0) {
      throw std::runtime_error("wrong runtime RMW library: " + library);
    }
    if (mode == "valid") {
      if (rejected || parsed.uint64_values != std::vector<std::uint64_t>({1, 2, 3, 5, 8, 13, 21, 34})) {
        throw std::runtime_error("valid roundtrip failed");
      }
    } else if (!rejected) {
      throw std::runtime_error("malformed case unexpectedly accepted");
    }

    std::cout << "METRIC {\"mode\":\"" << mode << "\",\"count\":" << count
              << ",\"wire_bytes\":" << wire.size()
              << ",\"wire_fnv1a64\":\"" << std::hex << fnv1a(wire) << std::dec << "\""
              << ",\"rejected\":" << (rejected ? "true" : "false")
              << ",\"max_new_request_bytes\":" << max_request
              << ",\"total_new_requested_bytes\":" << total_requested
              << ",\"new_call_count\":" << request_count
              << ",\"large_new_call_count\":" << large_request_count
              << ",\"vmrss_before_kib\":" << rss_before
              << ",\"vmrss_after_kib\":" << rss_after
              << ",\"vmsize_before_kib\":" << virtual_before
              << ",\"vmsize_after_kib\":" << virtual_after
              << ",\"vmpeak_kib\":" << peak_virtual
              << ",\"ru_maxrss_before_kib\":" << maxrss_before
              << ",\"ru_maxrss_after_kib\":" << peak_resident
              << ",\"library\":\"" << library << "\"}" << std::endl;
    return 0;
  } catch (const std::exception & error) {
    std::cerr << "HARNESS_FAILURE: " << error.what() << '\n';
    return 3;
  }
}
