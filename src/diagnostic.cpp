#include <upcxx/diagnostic.hpp>

#ifdef UPCXX_BACKEND
  #include <upcxx/backend_fwd.hpp>
#endif

#if UPCXX_BACKEND_GASNET
  #include <upcxx/backend/gasnet/runtime_internal.hpp>
#endif

#include <iostream>
#include <sstream>

////////////////////////////////////////////////////////////////////////

void upcxx::fatal_error(const char *msg, const char *title, const char *func, const char *file, int line) {
  std::stringstream ss;

  ss << std::string(70, '/') << '\n';
  if (!title) title = "fatal error";
  ss << "UPC++ " << title << ":\n";
  #ifdef UPCXX_BACKEND
    ss << " on process ";
    if (upcxx::backend::rank_n > 0 && upcxx::backend::rank_me < upcxx::backend::rank_n) {
      ss << upcxx::backend::rank_me;
    } else { // pre-init or after memory corruption
      ss << "*unknown*";
    }
    #if UPCXX_BACKEND_GASNET
      ss << " (" << gasnett_gethostname() << ")";
    #endif
    ss << '\n';
  #endif
 
  if (file) {
    ss << " at " << file;
    if (line > 0) ss << ':' << line;
    ss << '\n';
  }
  if (func && *func) {
    ss << " in function: " << func;
    if (func[strlen(func)-1] != ')') ss << "()";
    ss << '\n';
  }
  if(msg && msg[0]) {
    ss << '\n' << msg << '\n';
  }
  
  #if UPCXX_BACKEND_GASNET
    if(0 == gasnett_getenv_int_withdefault("GASNET_FREEZE_ON_ERROR", 0, 0)) {
      ss << "\n"
        "To have UPC++ freeze during these errors so you can attach a debugger,\n"
        "rerun the program with GASNET_FREEZE_ON_ERROR=1 in the environment.\n";
    }
  #endif

  ss << std::string(70, '/') << '\n';
  
  #if UPCXX_BACKEND_GASNET
    #ifdef gasnett_fatalerror_nopos
      gasnett_fatalerror_nopos("\n%s", ss.str().c_str());
    #else
      gasnett_fatalerror("\n%s", ss.str().c_str());
    #endif
  #else
    std::cerr << ss.str();
    std::abort();
  #endif
}

void upcxx::assert_failed(const char *func, const char *file, int line, const char *msg) {
  upcxx::fatal_error(msg, "assertion failure", func, file, line);
}

upcxx::say::say() {
  #ifdef UPCXX_BACKEND
    ss << '[' << upcxx::backend::rank_me << "] ";
  #endif
}

upcxx::say::~say() {
  ss << std::endl;
  std::cerr << ss.str();
}
