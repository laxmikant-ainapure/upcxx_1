#ifndef _f42075e8_08a8_4472_8972_3919ea92e6ff
#define _f42075e8_08a8_4472_8972_3919ea92e6ff

#include <upcxx/backend.hpp>
#include <upcxx/cuda.hpp>
#include <upcxx/completion.hpp>
#include <upcxx/global_ptr.hpp>
#include <upcxx/rput.hpp>

#include <functional>

namespace upcxx {
  namespace detail {
    void rma_copy_get(void *buf_d, intrank_t rank_s, void const *buf_s, std::size_t size, backend::gasnet::handle_cb *cb);
    void rma_copy_put(intrank_t rank_d, void *buf_d, void const *buf_s, std::size_t size, backend::gasnet::handle_cb *cb);
    void rma_copy_cuda(
        int dev_d, void *buf_d,
        int dev_s, void const *buf_s, std::size_t size,
        cuda::event_cb *cb
      );
  }
  
  template<typename T, memory_kind Ks, memory_kind Kd,
           typename Cxs = completions<future_cx<operation_cx_event>>>
  typename detail::completions_returner<
      /*EventPredicate=*/detail::event_is_here,
      /*EventValues=*/detail::rput_event_values,
      Cxs
    >::return_t
  copy(global_ptr<T,Ks> src, global_ptr<T,Kd> dest, std::size_t n,
       Cxs cxs=completions<future_cx<operation_cx_event>>{{}});

  template<typename T, memory_kind Ks,
           typename Cxs = completions<future_cx<operation_cx_event>>>
  typename detail::completions_returner<
      /*EventPredicate=*/detail::event_is_here,
      /*EventValues=*/detail::rput_event_values,
      Cxs
    >::return_t
  copy(global_ptr<T,Ks> src, T *dest, std::size_t n,
       Cxs cxs=completions<future_cx<operation_cx_event>>{{}}) {
    return upcxx::copy(
      src,
      // Hack! The dest pointer may be to non-shared local memory, so a global_ptr
      // of that is not valid. But, the copy overload we're dispatching to will
      // tear-down the global_ptr and hand the addresses to gasnet which does
      // support non-shared memory for put/get.
      global_ptr<T>(detail::internal_only(), upcxx::rank_me(), dest),
      n,
      std::move(cxs)
    );
  }

  template<typename T, memory_kind Kd,
           typename Cxs = completions<future_cx<operation_cx_event>>>
  typename detail::completions_returner<
      /*EventPredicate=*/detail::event_is_here,
      /*EventValues=*/detail::rput_event_values,
      Cxs
    >::return_t
  copy(T const *src, global_ptr<T,Kd> dest, std::size_t n,
       Cxs cxs=completions<future_cx<operation_cx_event>>{{}}) {
    return upcxx::copy(
      // Hack! The src pointer may be to non-shared local memory, so a global_ptr
      // of that is not valid. But, the copy overload we're dispatching to will
      // tear-down the global_ptr and hand the addresses to gasnet which does
      // support non-shared memory for put/get.
      global_ptr<T>(detail::internal_only(), upcxx::rank_me(), const_cast<T*>(src)),
      dest, n,
      std::move(cxs)
    );
  }
  
  template<typename T, memory_kind Ks, memory_kind Kd, typename Cxs>
  typename detail::completions_returner<
      /*EventPredicate=*/detail::event_is_here,
      /*EventValues=*/detail::rput_event_values,
      Cxs
    >::return_t
  copy(global_ptr<T,Ks> src, global_ptr<T,Kd> dest, std::size_t n, Cxs cxs) {
    const int dev_s = src.device_;
    const int dev_d = dest.device_;
    const intrank_t rank_s = src.rank_;
    const intrank_t rank_d = dest.rank_;
    void *const buf_s = src.raw_ptr_;
    void *const buf_d = dest.raw_ptr_;
    const std::size_t size = n*sizeof(T);

    constexpr int host_device = -1;
    
    using cxs_here_t = detail::completions_state<
      /*EventPredicate=*/detail::event_is_here,
      /*EventValues=*/detail::rput_event_values,
      Cxs>;
    using cxs_remote_t = detail::completions_state<
      /*EventPredicate=*/detail::event_is_remote,
      /*EventValues=*/detail::rput_event_values,
      Cxs>;

    cxs_here_t *cxs_here = new cxs_here_t(std::move(cxs));
    cxs_remote_t cxs_remote(std::move(cxs));

    auto returner = detail::completions_returner<
        /*EventPredicate=*/detail::event_is_here,
        /*EventValues=*/detail::rput_event_values,
        Cxs
      >(*cxs_here);

    if(rank_d == rank_s) {
      UPCXX_ASSERT(rank_d == upcxx::rank_me());

      detail::rma_copy_cuda(dev_d, buf_d, dev_s, buf_s, size,
        cuda::make_event_cb([=]() {
          cxs_here->template operator()<operation_cx_event>();
          const_cast<cxs_remote_t&>(cxs_remote).template operator()<remote_cx_event>();
          delete cxs_here;
        })
      );
    }
    else if(rank_d == upcxx::rank_me()) {
      /* We are the destination, so semantically like a GET, even though a PUT
       * is used to transfer on the network
       */
      void *bounce_d;
      if(dev_d == host_device)
        bounce_d = buf_d;
      else
        bounce_d = upcxx::allocate(size, 64);
      
      backend::send_am_master<progress_level::internal>(
        upcxx::world(), rank_s,
        [=]() {
          auto make_bounce_s_cont = [=](void *bounce_s) {
            return [=]() {
              detail::rma_copy_put(rank_d, bounce_d, bounce_s, size,
              backend::gasnet::make_handle_cb([=]() {
                  if(dev_s != host_device)
                    upcxx::deallocate(bounce_s);
                  
                  backend::send_am_master<progress_level::internal>(
                    upcxx::world(), rank_d,
                    [=]() {
                      auto bounce_d_cont = [=]() {
                        if(dev_d != host_device)
                          upcxx::deallocate(bounce_d);
                        
                        cxs_here->template operator()<operation_cx_event>();
                        delete cxs_here;
                      };
                      
                      if(dev_d == host_device)
                        bounce_d_cont();
                      else
                        detail::rma_copy_cuda(dev_d, buf_d, host_device, bounce_d, size, cuda::make_event_cb(bounce_d_cont));
                    }
                  );
                })
              );
            };
          };
          
          if(dev_s == host_device)
            make_bounce_s_cont(buf_s)();
          else {
            void *bounce_s = upcxx::allocate(size, 64);
            detail::rma_copy_cuda(
              host_device, bounce_s, dev_s, buf_s, size,
              cuda::make_event_cb(make_bounce_s_cont(bounce_s))
            );
          }
        }
      );
    }
    else {
      /* We are the source, so semantically this is a PUT even though we use a
       * GET to transfer over network.
       */
      auto make_bounce_s_cont = [&](void *bounce_s) {
        return [=]() {
          if(dev_s != host_device) {
            // since source side has a bounce buffer, we can signal source_cx as soon
            // as its populated
            cxs_here->template operator()<source_cx_event>();
          }
          
          backend::send_am_master<progress_level::internal>(
            upcxx::world(), rank_d,
            upcxx::bind(
              [=](cxs_remote_t &cxs_remote) {
                void *bounce_d = dev_d == host_device ? buf_d : upcxx::allocate(size, 64);

                detail::rma_copy_get(bounce_d, rank_s, bounce_s, size,
                  backend::gasnet::make_handle_cb([=]() {
                    auto bounce_d_cont = [=]() {
                      if(dev_d != host_device)
                        upcxx::deallocate(bounce_d);
                      
                      const_cast<cxs_remote_t&>(cxs_remote).template operator()<remote_cx_event>();

                      backend::send_am_master<progress_level::internal>(
                        upcxx::world(), rank_s,
                        [=]() {
                          if(dev_s != host_device)
                            upcxx::deallocate(bounce_s);
                          else {
                            // source didnt use bounce buffer, need to source_cx now
                            cxs_here->template operator()<source_cx_event>();
                          }
                          cxs_here->template operator()<operation_cx_event>();
                          
                          delete cxs_here;
                        }
                      );
                    };
                    
                    if(dev_d == host_device)
                      bounce_d_cont();
                    else
                      detail::rma_copy_cuda(dev_d, buf_d, host_device, bounce_d, size, cuda::make_event_cb(bounce_d_cont));
                  })
                );
              }, std::move(cxs_remote)
            )
          );
        };
      };

      if(dev_s == host_device)
        make_bounce_s_cont(buf_s)();
      else {
        void *bounce_s = upcxx::allocate(size, 64);
        detail::rma_copy_cuda(host_device, bounce_s, dev_s, buf_s, size, cuda::make_event_cb(make_bounce_s_cont(bounce_s)));
      }
    }

    return returner();
  }
}
#endif
