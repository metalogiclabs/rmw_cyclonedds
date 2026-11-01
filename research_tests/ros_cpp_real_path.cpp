// Source-native C++ RMW deserialization allocation witness, deliberately bounded.
// Requires genuine test_msgs C++ type support and the selected Cyclone DDS RMW.
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
void track(std::size_t n) { if (monitoring) max_requested = std::max(max_requested,n); }
}
void* operator new(std::size_t n) {
  track(n);
  if (void* p=std::malloc(n?n:1)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete(void* p, std::size_t) noexcept {std::free(p);}
void* operator new[](std::size_t n) {
  track(n);
  if (void* p=std::malloc(n?n:1)) return p;
  throw std::bad_alloc();
}
void operator delete[](void* p) noexcept {std::free(p);}
void operator delete[](void* p, std::size_t) noexcept {std::free(p);}

int main() {
  using Msg = test_msgs::msg::UnboundedSequences;
  rclcpp::Serialization<Msg> coder;
  // Positive control uses genuine message serialization, not hand-built bytes.
  Msg control;
  control.uint64_values={11,13};
  rclcpp::SerializedMessage good;
  coder.serialize_message(&control,&good);
  Msg roundtrip;
  coder.deserialize_message(&good,&roundtrip);
  const bool good_ok=roundtrip.uint64_values==control.uint64_values;
  std::cout<<"valid_roundtrip="<<good_ok<<std::endl;
  if(!good_ok) return 3;

  // CDR encapsulation, 12 preceding empty sequences, then the uint64[]
  // count=8192 with only 8192 remaining bytes instead of >=65536.
  // The target array is the thirteenth member of UnboundedSequences.msg.
  const std::size_t n=8192, previous_sequences=12;
  std::vector<uint8_t> cdr(4 + previous_sequences*4 + 4 + 4 + n, 0);
  cdr[1]=1;  // little endian
  cdr[4 + previous_sequences*4]=0;
  cdr[4 + previous_sequences*4 + 1]=0x20;
  rclcpp::SerializedMessage bad(cdr.size());
  auto& raw=bad.get_rcl_serialized_message();
  std::memcpy(raw.buffer,cdr.data(),cdr.size());
  raw.buffer_length=cdr.size();
  Msg target;
  bool rejected=false;
  max_requested=0;
  monitoring=true;
  try {coder.deserialize_message(&bad,&target);}
  catch (const std::exception&){rejected=true;}
  monitoring=false;
  std::cout<<"truncated_uint64 rejected="<<rejected
           <<" max_alloc_request="<<max_requested
           <<" input_bytes="<<cdr.size()<<std::endl;
  // Confirm the relevant RMW implementation shared library is loaded.
  std::ifstream maps("/proc/self/maps");
  bool found=false;
  for(std::string line;std::getline(maps,line);){
    if(line.find("librmw_cyclonedds_cpp.so")!=std::string::npos){
      found=true;std::cout<<"rmw_library="<<line.substr(line.find('/'))<<std::endl;break;
    }
  }
  std::cout<<"cyclone_loaded="<<found<<std::endl;
  return (rejected&&found) ? 0 : 4;
}
