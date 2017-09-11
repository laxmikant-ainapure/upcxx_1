#include <libgen.h>

#define KNORM  "\x1B[0m"
#define KLRED "\x1B[91m"
#define KLGREEN "\x1B[92m"
#define KLBLUE "\x1B[94m"

#ifdef UPCXX_BACKEND
#define PRINT_TEST_HEADER                                               \
    if (!upcxx::rank_me()) {                                            \
        std::cout << KLBLUE << "Test: " << basename(const_cast<char*>(__FILE__)) << KNORM << std::endl; \
        std::cout << KLBLUE << "Ranks: " << upcxx::rank_n() << KNORM << std::endl; \
    }

// include a barrier to ensure all other threads have finished working.
// flush stdout to prevent any garbling of output
#define PRINT_TEST_SUCCESS upcxx::barrier();\
    if (!upcxx::rank_me()) std::cout << std::flush<< KLGREEN << "Test result: SUCCESS" << KNORM << std::endl

#else

#define PRINT_TEST_HEADER                                               \
    std::cout << KLBLUE << "Test: " << basename(const_cast<char*>(__FILE__)) << KNORM << std::endl;

#define PRINT_TEST_SUCCESS \
    std::cout << std::flush<< KLGREEN << "Test result: SUCCESS" << KNORM << std::endl

#endif

