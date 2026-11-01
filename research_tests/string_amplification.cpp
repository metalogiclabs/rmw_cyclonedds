// Bounded, native public ROS C++ witness for residual wire-to-heap amplification.
// This does not exploit production systems and runs under a strict memory cap.
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <test_msgs/msg/unbounded_sequences.hpp>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <fstream>
#include <iostream>
#include <new>
#include <string>
#include <vector>

namespace {
thread_local bool monitoring = false;
thread_local std::size_t max_requested = 0;
void note(std::size_t n) {
  if (monitoring) max_requested = std::max(max_requested,n);
}
}
void* operator new(std::size_t n) {
  note(n);
  if (void* p=std::malloc(n?n:1)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete(void* p,std::size_t) noexcept {std::free(p);}
void* operator new[](std::size_t n) {
  note(n);
  if (void* p=std::malloc(n?n:1)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept {std::free(p);}
void operator delete[](void* p,std::size_t) noexcept {std::free(p);}

int main() {
  using Msg=test_msgs::msg::UnboundedSequences;
  rclcpp::Serialization<Msg> coder;
  bool all=true;
  for(std::size_t n: {256u,2048u,8192u}) {
    Msg input;
    input.string_values.assign(n,std::string(""));
    rclcpp::SerializedMessage serialized;
    coder.serialize_message(&input,&serialized);
    const auto & raw=serialized.get_rcl_serialized_message();
    const std::size_t length=raw.buffer_length;
    if(length<=8) return 2;
    // Use identical allocation instrumentation for a fully valid decode.
    // This is a control for in-memory representation expansion, not a fault.
    Msg valid_out;
    max_requested=0;
    monitoring=true;
    coder.deserialize_message(&serialized,&valid_out);
    monitoring=false;
    const std::size_t valid_max_requested=max_requested;
    const bool valid=valid_out.string_values==input.string_values;
    // The string sequence is complete. Remove the final scalar field so the
    // message is malformed only AFTER the sequence allocation happens.
    const std::size_t broken_len=length-4;
    rclcpp::SerializedMessage broken(broken_len);
    auto & data=broken.get_rcl_serialized_message();
    std::memcpy(data.buffer,raw.buffer,broken_len);
    data.buffer_length=broken_len;
    Msg rejected_out;
    bool rejected=false;
    max_requested=0;
    monitoring=true;
    try {
      coder.deserialize_message(&broken,&rejected_out);
    } catch(const std::exception&) {
      rejected=true;
    }
    monitoring=false;
    std::cout << "CASE n=" << n << " wire=" << broken_len
              << " max_alloc=" << max_requested
              << " max_valid_alloc=" << valid_max_requested
              << " rejected=" << rejected
              << " valid=" << valid
              << " string_object_bytes=" << sizeof(std::string)
              << std::endl;
    all &= rejected && valid && max_requested >= n*sizeof(std::string)
      && valid_max_requested >= n*sizeof(std::string);
  }
  const char *expected=std::getenv("EXPECTED_LIB_DIR");
  if(!expected) return 3;
  std::ifstream maps("/proc/self/maps");
  bool mapped=false;
  for(std::string line;std::getline(maps,line);) {
    auto pos=line.find("/librmw_cyclonedds_cpp.so");
    if(pos!=std::string::npos) {
      auto slash=line.find('/');
      if(slash!=std::string::npos) {
        const std::string path=line.substr(slash);
        std::cout << "MAPPED " << path << std::endl;
        mapped |= path.find(expected)==0;
      }
    }
  }
  std::cout << "BOUNDARY " << (all && mapped) << std::endl;
  return all && mapped ? 0 : 4;
}
