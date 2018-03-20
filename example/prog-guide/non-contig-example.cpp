#include <cstdint>
#include <cstdlib>
#include <cstddef>

#include <upcxx/allocate.hpp>
#include <upcxx/future.hpp>
#include <upcxx/vis.hpp>
#include <upcxx/dist_object.hpp>


using namespace upcxx;
using namespace std;

#include "non-contig.hpp"


typedef float spatch_t[sdim[2]][sdim[1]][sdim[0]];
typedef float dpatch_t[ddim[2]][ddim[1]][ddim[0]];

int main() {

  init();
  
  
  intrank_t me = rank_me();
  intrank_t n =  rank_n();
  intrank_t nebrHi = (me + 1) % n;
  intrank_t nebrLo = (me + n - 1) % n;


  spatch_t* myPatchSPtr = (spatch_t*)allocate(sizeof(spatch_t));
  dist_object<global_ptr<float> > smesh(global_ptr<float>((float*)myPatchSPtr));
  dpatch_t* myPatchDPtr = (dpatch_t*)allocate(sizeof(dpatch_t));
  dist_object<global_ptr<float> > dmesh(global_ptr<float>((float*)myPatchDPtr));
  

  future<global_ptr<float>> dgpf = dmesh.fetch(nebrHi);
  future<global_ptr<float>> sgpf = smesh.fetch(nebrLo);

  when_all(dgpf, sgpf).wait();
 
  global_ptr<float> d_gp=dgpf.result();
  global_ptr<float> s_gp=sgpf.result();
  {     //   memory transfer done as an rput_strided
    float*  src_base = (*smesh).local(); //raw pointer to local src patch
    global_ptr<float> dst_base = d_gp; // global_ptr to memory location on destination rank
    future<> f1 = rput_strided_example(src_base, dst_base);
    f1.wait();
  }
  {     //   memory transfer done as an rget_strided
    float*  dst_base = (*dmesh).local(); //raw pointer to local destination patch
    global_ptr<float> src_base = s_gp; // global_ptr to memory location on src rank
    future<> f1 = rget_strided_example(src_base, dst_base);
    f1.wait();
  }

  finalize();
  
  return 0;
}
