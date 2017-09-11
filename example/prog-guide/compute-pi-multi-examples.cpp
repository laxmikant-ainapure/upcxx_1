/*
 * This is the main file for all the compute pi code in the guide. It wraps all of the various
 * allocate() calls, using namespaces. Although this is a rather peculiar structure, it is intended
 * for use with individual code snippets extracted directly from the programmer's guide.
*/

#include <libgen.h>
#include <iostream>
#include <cstdlib>
#include <random>
#include <upcxx/upcxx.hpp>
#include "../../test/util.hpp"

using namespace std;

#include "fetch.hpp"

namespace rpc {
    #include "rpc-accumulate.hpp"
}

namespace global_ptrs {
    #include "global-ptrs-accumulate.hpp"
}

namespace distobj {
    #include "distobj-accumulate.hpp"
}

namespace async_distobj {
    #include "async-distobj-accumulate.hpp"
}

namespace atomics {
    #include "atomics-accumulate.hpp"
}

namespace quiesence {
    #include "quiesence-accumulate.hpp"
}

int hit()
{
    double x = static_cast<double>(rand()) / RAND_MAX;
    double y = static_cast<double>(rand()) / RAND_MAX;
    if (x*x + y*y <= 1.0) return 1;
    else return 0;
}

// the prev is passed into the macro to check that the results between the two
// versions are identical
#define ACCM(version, prev)                                             \
    int hits_##version = version::accumulate(my_hits);                  \
	if (!upcxx::rank_me()) {                                            \
        cout << #version << ": pi estimate: " << 4.0 * hits_##version / trials \
             << ", rank 0 alone: " << 4.0 * my_hits / my_trials << endl; \
        UPCXX_ASSERT_ALWAYS(hits_##version == hits_##prev, "hits mismatch between " #version " and " #prev); \
	}

int main(int argc, char **argv)
{
    upcxx::init();
    if (!upcxx::rank_me()) {
        cout << "Testing " << basename((char*)__FILE__) << " with " << upcxx::rank_n() << " ranks" << endl;
    }
    int my_hits = 0;
    int my_trials = 100000;
    if (argc >= 2) my_trials = atoi(argv[1]);
    int trials = upcxx::rank_n() * my_trials;
    if (!upcxx::rank_me()) 
      cout << "Calculating pi with " << trials << " trials, distributed across " << upcxx::rank_n() << " ranks." << endl;
    srand(upcxx::rank_me());
    for (int i = 0; i < my_trials; i++) {
        my_hits += hit();
    }

    ACCM(rpc, rpc);
    ACCM(global_ptrs, rpc);
    ACCM(distobj, global_ptrs);
    ACCM(async_distobj, distobj);
    ACCM(atomics, async_distobj);
    ACCM(quiesence, atomics);
    // now check that the result is reasonable
    if (!upcxx::rank_me()) {
        double pi = 4.0 * hits_rpc / trials;
        cout << "Computed pi to be " << pi << endl;
        UPCXX_ASSERT_ALWAYS(pi >= 3 && pi <= 3.5, "pi is out of range (3, 3.5)");
        cout << KLGREEN << "SUCCESS" << KNORM << endl;
    }

    upcxx::finalize();
    return 0;
}
