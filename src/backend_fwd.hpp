#ifndef _f93ccf7a_35a8_49c6_b7b2_55c3c1a9640c
#define _f93ccf7a_35a8_49c6_b7b2_55c3c1a9640c

/* This header declares some core user-facing API without
 * pulling in any of its imlpementation. Non-parallel programs can 
 * safely include this so long as they dont use anything besides
 * upcxx::rank_n/me().
 */

#include <cstddef>
#include <cstdint>

//////////////////////////////////////////////////////////////////////
// Public API:

namespace upcxx {
  typedef int intrank_t;
  typedef unsigned int uintrank_t;
  
  enum class progress_level {
    internal,
    user
  };
  
  void init();
  void finalize();
  
  intrank_t rank_n();
  intrank_t rank_me();
  
  void* allocate(std::size_t size,
                 std::size_t alignment = alignof(std::max_align_t));
  void deallocate(void *p);
  
  void progress(progress_level lev = progress_level::user);
  
  void barrier();
}

////////////////////////////////////////////////////////////////////////
// Backend API:

namespace upcxx {
namespace backend {
  // These are actually defined in diagnostic.cpp so that asserts can
  // print the current rank without pulling in the backend for
  // non-parallel programs.
  extern intrank_t rank_n;
  extern intrank_t rank_me;
}}
  
// We dispatch on backend type using preprocessor symbol which is
// defined to be another symbol that otherwise doesn't exist. So we
// define and immediately undefine them.
#define gasnet1_seq 100
#define gasnetex_par 101
#if UPCXX_BACKEND == gasnet1_seq
  #undef gasnet1_seq
  #undef gasnetex_par
  
  namespace upcxx {
  namespace backend {
    struct persona_state {};
  }}
#elif UPCXX_BACKEND == gasnetex_par
  #undef gasnet1_seq
  #undef gasnetex_par
  
  #include <upcxx/backend/gasnet/handle_cb.hpp>
  
  namespace upcxx {
  namespace backend {
    struct persona_state {
      gasnet::handle_cb_queue hcbs;
    };
  }}
#else
  namespace upcxx {
  namespace backend {
    struct persona_state {};
  }}
#endif

////////////////////////////////////////////////////////////////////////
// Public API implementations:

namespace upcxx {
  inline intrank_t rank_n() { return backend::rank_n; }
  inline intrank_t rank_me() { return backend::rank_me; }
}

#endif