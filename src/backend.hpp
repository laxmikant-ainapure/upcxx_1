#ifndef _eb5831b3_6325_4936_9ebb_321d97838dee
#define _eb5831b3_6325_4936_9ebb_321d97838dee

#include <upcxx/backend_fwd.hpp>
#include <upcxx/future.hpp>
#include <upcxx/persona.hpp>
#include <upcxx/team.hpp>
#include <upcxx/memory_kind.hpp>

#include <cstdint>
#include <memory>
#include <tuple>

////////////////////////////////////////////////////////////////////////////////

namespace upcxx {
  inline bool initialized() {
    return backend::init_count != 0;
  }
  
  inline persona& master_persona() {
    UPCXX_ASSERT_INIT();
    return backend::master;
  }
  
  inline bool progress_required() {
    UPCXX_ASSERT_INIT();
    return detail::the_persona_tls.progress_required();
  }
  inline bool progress_required(persona_scope &bottom) {
    UPCXX_ASSERT_INIT();
    return detail::the_persona_tls.progress_required(bottom);
  }
  
  inline void discharge() {
    UPCXX_ASSERT_INIT();
    while(upcxx::progress_required())
      upcxx::progress(progress_level::internal);
  }
  inline void discharge(persona_scope &ps) {
    UPCXX_ASSERT_INIT();
    while(upcxx::progress_required(ps))
      upcxx::progress(progress_level::internal);
  }
}

////////////////////////////////////////////////////////////////////////////////
// Argument-checking assertions

// These define the maximum-size (in bytes) of an object that by-value API's will accept without an #error
#ifndef UPCXX_MAX_VALUE_SIZE
#define UPCXX_MAX_VALUE_SIZE 512 // user-tunable default
#endif
#ifndef UPCXX_MAX_RPC_ARG_SIZE
#define UPCXX_MAX_RPC_ARG_SIZE 512 // user-tunable default
#endif

#define UPCXX_STATIC_ASSERT_VALUE_SIZE(T, fnname) \
  static_assert(sizeof(T) <= UPCXX_MAX_VALUE_SIZE, \
    "This program is attempting to pass an object with a large static type (over " UPCXX_STRINGIFY(UPCXX_MAX_VALUE_SIZE) " bytes) " \
    "to the by-value overload of upcxx::" #fnname ". This is ill-advised because the by-value overload is " \
    "designed and tuned for small scalar values, and will impose significant data copy overheads " \
    "(and possibly program stack overflow) when used with larger types. Please use the bulk upcxx::" \
    #fnname " overload instead, which manipulates the data by pointer, avoiding costly by-value copies. " \
    "The threshold for this error can be adjusted (at your own peril!) via -DUPCXX_MAX_VALUE_SIZE=n" \
  )
namespace upcxx { namespace detail {
  template <typename T>
  struct type_respects_static_size_limit {
    static constexpr bool value = sizeof(T) <= UPCXX_MAX_RPC_ARG_SIZE;
  };
}}
#define UPCXX_STATIC_ASSERT_RPC_MSG(fnname) \
    "This program is attempting to pass an object with a large static type (over " UPCXX_STRINGIFY(UPCXX_MAX_RPC_ARG_SIZE) " bytes) " \
    "to upcxx::" #fnname ". This is ill-advised because RPC is tuned for top-level argument objects that provide " \
    "fast move operations, and will impose significant data copy overheads (and possibly program stack overflow) " \
    "when used with larger types. Please consider instead passing a Serializable container for your large object, " \
    "such as a upcxx::view (e.g. `upcxx::make_view(&my_large_object, &my_large_object+1)`), to avoid costly data copies. " \
    "The threshold for this error can be adjusted (at your own peril!) via -DUPCXX_MAX_RPC_ARG_SIZE=n" 

////////////////////////////////////////////////////////////////////////////////
// upcxx::backend implementation: non-backend specific

namespace upcxx {
namespace backend {
  // inclusive lower and exclusive upper bounds for local_team ranks
  extern intrank_t pshm_peer_lb, pshm_peer_ub, pshm_peer_n;
  
  // Given index in local_team:
  //   local_minus_remote: Encodes virtual address translation which is added
  //     to the raw encoding to get local virtual address.
  //   vbase: Local virtual address mapping to beginning of peer's segment
  //   size: Size of peer's segment in bytes.
  extern std::unique_ptr<std::uintptr_t[/*local_team.size()*/]> pshm_local_minus_remote;
  extern std::unique_ptr<std::uintptr_t[/*local_team.size()*/]> pshm_vbase;
  extern std::unique_ptr<std::uintptr_t[/*local_team.size()*/]> pshm_size;

  //////////////////////////////////////////////////////////////////////////////
  
  template<typename Fn>
  void during_user(Fn &&fn, persona &active_per) {
    during_level<progress_level::user>(std::forward<Fn>(fn), active_per);
  }
  
  //////////////////////////////////////////////////////////////////////////////
  // fulfill_during_<level=internal>
  
  template<typename ...T>
  void fulfill_during_(
      std::integral_constant<progress_level, progress_level::internal>,
      detail::future_header_promise<T...> *pro, // takes ref
      std::intptr_t anon,
      persona &active_per
    ) {

    detail::the_persona_tls.during(
      active_per, progress_level::internal,
      [=]() {
        detail::promise_fulfill_anonymous(pro, anon);
        pro->dropref();
      },
      /*known_active=*/std::true_type()
    );
  }
  
  template<typename ...T>
  void fulfill_during_(
      std::integral_constant<progress_level, progress_level::internal>,
      detail::future_header_promise<T...> *pro, // takes ref
      std::tuple<T...> &&vals,
      persona &active_per
    ) {

    pro->base_header_result.construct_results(std::move(vals));
    
    fulfill_during_(
      std::integral_constant<progress_level, progress_level::internal>(),
      pro, /*anon*/1,
      active_per
    );
  }
  
  //////////////////////////////////////////////////////////////////////////////
  // fulfill_during_<level=user>
  
  template<typename ...T>
  void fulfill_during_(
      std::integral_constant<progress_level, progress_level::user>,
      detail::future_header_promise<T...> *pro, // takes ref
      std::tuple<T...> &&vals,
      persona &active_per
    ) {

    pro->base_header_result.construct_results(std::move(vals));
    
    detail::the_persona_tls.fulfill_during_user_of_active(active_per, /*move ref*/pro, /*deps*/1);
  }
  
  template<typename ...T>
  void fulfill_during_(
      std::integral_constant<progress_level, progress_level::user>,
      detail::future_header_promise<T...> *pro, // takes ref
      std::intptr_t anon,
      persona &active_per
    ) {
    detail::the_persona_tls.fulfill_during_user_of_active(active_per, /*move ref*/pro, anon);
  }
  
  //////////////////////////////////////////////////////////////////////////////
  
  template<progress_level level, typename ...T>
  void fulfill_during(
      detail::future_header_promise<T...> *pro, // takes ref
      std::tuple<T...> vals,
      persona &active_per
    ) {
    fulfill_during_(
        std::integral_constant<progress_level,level>(),
        /*move ref*/pro, std::move(vals), active_per
      );
  }
  
  template<progress_level level, typename ...T>
  void fulfill_during(
      detail::future_header_promise<T...> *pro, // takes ref
      std::intptr_t anon,
      persona &active_per
    ) {
    fulfill_during_(
        std::integral_constant<progress_level,level>(),
        /*move ref*/pro, anon, active_per
      );
  }
  
  //////////////////////////////////////////////////////////////////////////////
  
  inline bool rank_is_local(intrank_t r) {
    UPCXX_ASSERT(r >= 0 && r < backend::rank_n, "Invalid argument to rank_is_local: " << r);
    return all_ranks_definitely_local || std::uintptr_t(r) - std::uintptr_t(pshm_peer_lb) < std::uintptr_t(pshm_peer_n);
    // Is equivalent to...
    // return pshm_peer_lb <= r && r < pshm_peer_ub;
  }
  
  inline void* localize_memory_nonnull(intrank_t rank, std::uintptr_t raw) {
    UPCXX_ASSERT(
      pshm_peer_lb <= rank && rank < pshm_peer_ub,
      "Rank "<<rank<<" is not local with current rank ("<<upcxx::rank_me()<<")."
    );

    intrank_t peer = rank - pshm_peer_lb;
    std::uintptr_t u = raw + pshm_local_minus_remote[peer];

    UPCXX_ASSERT(
      u - pshm_vbase[peer] < pshm_size[peer], // unsigned arithmetic handles both sides of the interval test
      "Memory address (raw="<<raw<<", local="<<reinterpret_cast<void*>(u)<<") is not within shared segment of rank "<<rank<<"."
    );

    return reinterpret_cast<void*>(u);
  }
  
  inline void* localize_memory(intrank_t rank, std::uintptr_t raw) {
    if(raw == reinterpret_cast<std::uintptr_t>(nullptr))
      return nullptr;
    
    return localize_memory_nonnull(rank, raw);
  }
  
  inline std::uintptr_t globalize_memory_nonnull(intrank_t rank, void const *addr) {
    UPCXX_ASSERT(
      pshm_peer_lb <= rank && rank < pshm_peer_ub,
      "Rank "<<rank<<" is not local with current rank ("<<upcxx::rank_me()<<")."
    );
    
    std::uintptr_t u = reinterpret_cast<std::uintptr_t>(addr);
    intrank_t peer = rank - pshm_peer_lb;
    std::uintptr_t raw = u - pshm_local_minus_remote[peer];
    
    UPCXX_ASSERT(
      u - pshm_vbase[peer] < pshm_size[peer], // unsigned arithmetic handles both sides of the interval test
      "Memory address (raw="<<raw<<", local="<<addr<<") is not within shared segment of rank "<<rank<<"."
    );
    
    return raw;
  }

  void validate_global_ptr(bool allow_null, intrank_t rank, void *raw_ptr, std::int32_t device,
                           memory_kind KindSet, size_t T_align, const char *T_name, 
                           const char *short_context, const char *context);
}}
  
////////////////////////////////////////////////////////////////////////////////
// Include backend-specific headers:

#if UPCXX_BACKEND_GASNET_SEQ || UPCXX_BACKEND_GASNET_PAR
  #include <upcxx/backend/gasnet/runtime.hpp>
#else
  #error "Invalid UPCXX_BACKEND."
#endif

#endif // #ifdef guard
