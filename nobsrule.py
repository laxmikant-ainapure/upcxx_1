"""
This is a nobs rule-file. See nobs/nobs/ruletree.py for documentation
on the structure and interpretation of a rule-file.
"""

import os
import sys

from nobs import errorlog
from nobs import os_extra
from nobs import subexec

cxx_exts = ('.cpp','.cxx','.c++','.C','.C++')
c_exts = ('.c',)

crawlable_dirs = [
  here('src'),
  here('test')
]

"""
Library sets are encoded as a dictionary of strings to dictionaries
conforming to:
  {libname:str: {
      'primary':bool
      'ld':[str],
      'incdirs':[str], # "-I" directories
      'incfiles':[str] # paths to files residing in "-I" directories.
      'ppflags':[str], # preprocessor flags to compiler minus those necessary for `incdirs` and `incfiles`
      'cgflags':[str], # code-gen flags to compiler
      'ldflags':[str], # flags to ld
      'libfiles':[str], # paths to binary archives
      'libflags':[str], # "-L", "-l", and other trailing linker flags minus those for `libfiles`
      'deplibs':[str] # short-names for dependencies of this library
    }, ...
  }

Each key is the short name of the library (like 'm' for 
'libm') and the value is a dictionary containing the linker command, 
various flags lists, and the list of libraries short-names it is 
dependent on.

Primary libraries are those which are used directly by the consumer,
while non-primary libraries are the secondary dependencies.

`incdirs`, `incfiles` and `libfiles` are not included in the `ppflags`
and `libflags` flag lists. `libset_*flags` queries exist at the bottom of
this file for properly retrieving complete flag lists.

Other routines for manipulating library-sets (named libset_*) exist at
the bottom of this file as well.
"""

@cached
def output_of(cmd_args):
  """
  Returns (returncode,stdout,stderr) generated by invoking the command
  arguments as a child process.
  """
  try:
    import subprocess as sp
    p = sp.Popen(cmd_args, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = p.communicate()
    return (p.returncode, stdout, stderr)
  except OSError as e:
    return (e.errno, None, None)

@rule(cli='cxx')
@coroutine
def cxx(cxt):
  """
  String list for the C++ compiler.
  """
  _, cross_env = yield cxt.gasnet_config()
  ans_cross = cross_env.get('CXX','').split()
  
  ans_default = []
  if env('NERSC_HOST', None) in ('cori','edison'):
    ans_default = ['CC']
  if not ans_default:
    ans_default = ['g++']
  
  ans_user = env('CXX','').split()
  
  if ans_cross and ans_user and ans_user != ans_cross:
    errorlog.warning(
      "Cross C++ compiler (%s) differs from CXX environment variable (%s)." % (
        ' '.join(ans_cross),
        ' '.join(ans_user)
      )
    )
  
  # If the cross-config script set it, use it.
  # Otherwise honor the CXX env-variable.
  # Otherwise use intelligent defaults.
  yield ans_cross or ans_user or ans_default

@rule(cli='cc')
@coroutine
def cc(cxt):
  """
  String list for the C compiler.
  """
  _, cross_env = yield cxt.gasnet_config()
  ans_cross = cross_env.get('CC','').split()
  
  ans_default = []
  if env('NERSC_HOST', None) in ('cori','edison'):
    ans_default = ['cc']
  if not ans_default:
    ans_default = ['gcc']
  
  ans_user = env('CC','').split()
  
  if ans_cross and ans_user and ans_user != ans_cross:
    errorlog.warning(
      "Cross C compiler (%s) differs from CC environment variable (%s)." % (
        ' '.join(ans_cross),
        ' '.join(ans_user)
      )
    )
  
  # If the cross-config script set it, use it.
  # Otherwise honor the CC env-variable.
  # Otherwise use intelligent defaults.
  yield ans_cross or ans_user or ans_default

@rule()
def lang_c11(cxt):
  """
  String list to engage C11 language dialect for the C compiler.
  """
  return ['-std=c11']

@rule()
def lang_cxx11(cxt):
  """
  String list to engage C++11 language dialect for the C++ compiler.
  """
  return ['-std=c++11']

@rule(path_arg='src')
@coroutine
def comp_lang(cxt, src):
  """
  File-specific compiler with source-language dialect flags.
  """
  _, ext = os.path.splitext(src)
  
  if ext in cxx_exts:
    cxx = yield cxt.cxx()
    yield cxx + cxt.lang_cxx11()
  elif ext in c_exts:
    cc = yield cxt.cc()
    yield cc + cxt.lang_c11()
  else:
    raise Exception("Unrecognized source file extension: "+src)

def version_of(cmd):
  return output_of(cmd + ['--version'])

@rule(path_arg='src')
@coroutine
def comp_version(cxt, src):
  """
  Identity string of file-specific compiler.
  """
  _, ext = os.path.splitext(src)
  
  if ext in cxx_exts:
    cxx = yield cxt.cxx()
    yield version_of(cxx)
  elif ext in c_exts:
    cc = yield cxt.cc()
    yield version_of(cc)
  else:
    raise Exception("Unrecognized source file extension: "+src)

@rule(path_arg='src')
@coroutine
def comp_lang_pp(cxt, src):
  """
  File-specific compiler with source-language and preprocessor flags.
  """
  comp = yield cxt.comp_lang(src)
  ipt = yield cxt.include_paths_tree(src)
  libs = yield cxt.libraries(src)
  yield (
    comp + 
    ['-D_GNU_SOURCE=1'] + # Required for full latest POSIX on some systems
    ['-I'+ipt] +
    libset_ppflags(libs)
  )

@rule()
@coroutine
def upcxx_backend(cxt):
  """
  A pseudo-library used to inject the "-DUPCXX_BACKEND=X" preprocessor
  flag and to rope in gasnet.
  """
  upcxx_be = {
    'upcxx-backend': {
      'primary': True,
      'ppflags': ['-D%s=%s'%(
          'UPCXX_BACKEND',
          env("UPCXX_BACKEND", otherwise="gasnet1_seq")
        )],
      'deplibs': ['gasnet']
    }
  }
  
  gasnet = yield cxt.gasnet()
  
  yield libset_merge(upcxx_be, libset_as_secondary(gasnet))

@rule()
def cg_optlev_default(cxt):
  """
  The default code-gen optimization level for compilation. Reads the
  "OPTLEV" environment variable.
  """
  return env('OPTLEV', 2)

@rule(path_arg='src')
def cg_optlev(cxt, src):
  """
  File-specific code-gen optimization level, defaults to `cg_optlev_default`.
  """
  return cxt.cg_optlev_default()

@rule()
def cg_dbgsym(cxt):
  """
  Include debugging symbols.
  """
  return env('DBGSYM', 0)

@rule(path_arg='src')
@coroutine
def comp_lang_pp_cg(cxt, src):
  """
  File-specific compiler with language, preprocessor, and code-gen flags.
  """
  comp = yield cxt.comp_lang_pp(src)
  optlev = cxt.cg_optlev(src)
  dbgsym = cxt.cg_dbgsym()
  libset = yield cxt.libraries(src)
  
  yield (
    comp +
    ['-O%d'%optlev] +
    (['-g'] if dbgsym else []) +
    ['-Wall'] +
    libset_cgflags(libset)
  )

@rule(path_arg='src')
@coroutine
def compiler(cxt, src):
  """
  File-specific compiler lambda. Given a source file path, returns a
  function that given a path of where to place the object file, returns
  the argument list to invoke as a child process.
  """
  comp = yield cxt.comp_lang_pp_cg(src)
  
  yield lambda outfile: comp + ['-c', src, '-o', outfile]

# Rule overriden in sub-nobsrule files.
@rule(cli='requires_gasnet', path_arg='src')
def requires_gasnet(cxt, src):
  return False

# Rule overriden in sub-nobsrule files.
@rule(cli='requires_upcxx_backend', path_arg='src')
def requires_upcxx_backend(cxt, src):
  return False

@rule(path_arg='src')
@coroutine
def libraries(cxt, src):
  """
  File-specific library set required to compile and eventually link the
  file `src`.
  """
  if cxt.requires_gasnet(src):
    maybe_gasnet = yield cxt.gasnet()
  else:
    maybe_gasnet = {}
  
  if cxt.requires_upcxx_backend(src):
    maybe_upcxx_backend = yield cxt.upcxx_backend()
  else:
    maybe_upcxx_backend = {}
  
  yield cxt.libset_merge(maybe_gasnet, maybe_upcxx_backend)

@rule()
def gasnet_user(cxt):
  value = env('GASNET', None)
  
  if not value:
    default_gasnetex_url_b64 = 'aHR0cDovL2dhc25ldC5sYmwuZ292L0VYL0dBU05ldC0yMDE3LjYuMC50YXIuZ3o='
    import base64
    value = base64.b64decode(default_gasnetex_url_b64)
  
  from urlparse import urlparse
  isurl = urlparse(value).netloc != ''
  if isurl:
    return 'tarball-url', value
  
  if not os_extra.exists(value):
    raise errorlog.LoggedError("Non-existent path for GASNET="+value)
  
  value = os.path.abspath(value)
  join = os.path.join
  
  if os_extra.isfile(value):
    return 'tarball', value
  elif os_extra.exists(join(value, 'Makefile')):
    return 'build', value
  elif os_extra.exists(join(value, 'include')) and \
       os_extra.exists(join(value, 'lib')):
    return 'install', value
  else:
    return 'source', value

@rule(cli='gasnet_conduit')
def gasnet_conduit(cxt):
  """
  GASNet conduit to use.
  """
  if env('CROSS','').startswith('cray-aries-'):
    default = 'aries'
  else:
    default = 'smp'
  
  return env('GASNET_CONDUIT', default)

@rule(cli='gasnet_syncmode')
def gasnet_syncmode(cxt):
  """
  GASNet sync-mode to use.
  """
  # this should be computed based off the choice of upcxx backend
  return 'seq'

@rule_memoized(path_arg=0)
class include_paths_tree:
  """
  Setup a shim directory containing a single symlink named 'upcxx' which
  points to 'upcxx/src'. With this directory added via '-I...' to
  compiler flags, allows our headers to be accessed via:
    #include <upcxx/*.hpp>
  """
  def execute(cxt):
    return cxt.mktree({'upcxx': here('src')}, symlinks=True)

@rule_memoized(cli='incs', path_arg=0)
class includes:
  """
  Ask compiler for all the non-system headers pulled in by preprocessing
  the given source file. Returns the list of header paths.
  """
  @traced
  @coroutine
  def get_comp_pp_and_src(me, cxt, src):
    me.depend_files(src)
    
    version = yield cxt.comp_version(src)
    me.depend_fact(key=None, value=version)
    
    comp_pp = yield cxt.comp_lang_pp(src)
    yield comp_pp, src
  
  @coroutine
  def execute(me):
    comp_pp, src = yield me.get_comp_pp_and_src()
    
    # See here for getting this to work with other compilers:
    #  https://projects.coin-or.org/ADOL-C/browser/trunk/autoconf/depcomp?rev=357
    cmd = comp_pp + ['-MM','-MT','x',src]
    
    mk = yield subexec.launch(cmd, capture_stdout=True)
    mk = mk[mk.index(":")+1:]
    
    import shlex
    deps = shlex.split(mk.replace("\\\n",""))[1:] # first is source file
    deps = map(os.path.abspath, deps)
    me.depend_files(*deps)
    
    yield deps

@rule_memoized(cli='obj', path_arg=0)
class compile:
  """
  Compile the given source file. Returns path to object file.
  """
  @traced
  @coroutine
  def get_src_compiler(me, cxt, src):
    compiler = yield cxt.compiler(src)
    version = yield cxt.comp_version(src)
    
    me.depend_fact(key='compiler', value=version)
    
    includes = yield cxt.includes(src)
    me.depend_files(src)
    me.depend_files(*includes)
    
    yield src, compiler
  
  @coroutine
  def execute(me):
    src, compiler = yield me.get_src_compiler()
    
    objfile = me.mkpath(None, suffix=os.path.basename(src)+'.o')
    yield subexec.launch(compiler(objfile))
    yield objfile

class Crawler:
  """
  Base class for memoized rules.
  
  Compile the given source file as well as all source files which can
  be found as sharing its name with a header included by any source
  file reached in this process (transitively closed set). Return pair
  containing set of all object files and the accumulated library
  dependency set.
  """
  @traced
  def get_main_src(me, cxt, main_src):
    return main_src
  
  @traced
  def do_includes(me, cxt, main_src, src):
    return cxt.includes(src)
  
  @traced
  def do_compile_and_libraries(me, cxt, main_src, src):
    return futurize(cxt.compile(src), cxt.libraries(src))
  
  @traced
  def find_src_exts(me, cxt, main_src, base):
    def exists(ext):
      path = base + ext
      me.depend_files(path)
      return os_extra.exists(path)
    srcs = filter(exists, c_exts + cxx_exts)
    return srcs
  
  @coroutine
  def crawl(me):
    main_src = me.get_main_src()
    
    # compile object files
    incs_seen = set()
    objs = []
    libset = {}
    
    def fresh_src(src):
      return async.when_succeeded(
        me.do_includes(src) >> includes_done,
        me.do_compile_and_libraries(src) >> compile_done
      )
    
    top_dir = here() # our "src/" directory
    
    def includes_done(incs):
      tasks = []
      for inc in incs:
        inc = os.path.realpath(inc)
        if inc not in incs_seen:
          incs_seen.add(inc)
          inc, _ = os.path.splitext(inc)
          # `inc` must be in a crawlable directory
          if any(path_within_dir(inc, x) for x in crawlable_dirs):
            for ext in me.find_src_exts(inc):
              tasks.append(fresh_src(inc + ext))
      
      return async.when_succeeded(*tasks)
    
    def compile_done(obj, more_libs):
      objs.append(obj)
      libset_merge_inplace(libset, more_libs)
    
    # wait for all compilations
    yield fresh_src(main_src)
    
    # return pair
    yield (objs, libset)

@rule_memoized(cli='exe', path_arg=0)
class executable(Crawler):
  """
  Compile the given source file as well as all source files which can
  be found as sharing its name with a header included by any source
  file reached in this process (transitively closed set). Take all those
  compiled object files and link them along with their library
  dependencies to proudce an executable. Path to executable returned.
  """
  @traced
  def cxx(me, cxt, main_src):
    return cxt.cxx()
  
  @coroutine
  def execute(me):
    # invoke crawl of base class
    objs, libset = yield me.crawl()
    
    # link
    exe = me.mkpath('exe', suffix='.x')
    
    ld = libset_ld(libset)
    cxx = yield me.cxx()
    if ld is None:
      ld = cxx
    ld = [cxx[0]] + ld[1:] 
    
    ldflags = libset_ldflags(libset)
    libflags = libset_libflags(libset)
    
    yield subexec.launch(ld + ldflags + ['-o',exe] + objs + libflags)
    yield exe

@rule_memoized(cli='lib', path_arg=0)
class library(Crawler):
  @traced
  def get_include_paths_tree(me, cxt, main_src):
    return cxt.include_paths_tree(main_src)
  
  @coroutine
  def execute(me):
    main_src = me.get_main_src()
    top_dir = here()
    
    # Invoke crawl of base class.
    objs, libset = yield me.crawl()
    
    # Headers pulled in from main file. Discard those not within this
    # repo (top_dir) or the nobs artifact cache (path_art).
    incs = yield me.do_includes(main_src)
    incs = [i for i in incs if
      path_within_dir(i, top_dir) or
      path_within_dir(i, me.memodb.path_art)
    ]
    incs = list(set(incs))
    
    inc_dir = yield me.get_include_paths_tree()
    
    par_dir = me.mkpath(key=None)
    os.makedirs(par_dir)
    
    libname, _ = os.path.splitext(main_src)
    libname = os.path.basename(libname)
    
    libpath = os.path.join(par_dir, 'lib' + libname + '.a')
    
    # archive objects to `libpath`
    yield subexec.launch(['ar', 'rcs', libpath] + objs)
    
    yield libset_merge(
      libset_as_secondary(libset),
      {libname: {
        'primary': True,
        'incdirs': [inc_dir],
        'incfiles': incs,
        'libfiles': [libpath],
        'deplibs': list(libset.keys())
      }}
    )

@rule(cli='install', path_arg='main_src')
@coroutine
def install(cxt, main_src, install_path):
  libset = yield cxt.library(main_src)
  
  # select name of the one primary library
  name = [k for k,v in libset.items() if v['primary']]
  assert len(name) == 1
  name = name[0]
  
  install_libset(install_path, name, libset)
  yield None

@rule_memoized()
class gasnet_source:
  """
  Download and extract gasnet source tree.
  """
  @traced
  def get_gasnet_user(me, cxt):
    return cxt.gasnet_user()
  
  @coroutine
  def execute(me):
    kind, value = me.get_gasnet_user()
    assert kind in ('tarball-url', 'tarball', 'source', 'build')
    
    if kind == 'source':
      source_dir = value
    
    elif kind == 'build':
      build_dir = value
      makefile = os.path.join(build_dir, 'Makefile')
      source_dir = makefile_extract(makefile, 'TOP_SRCDIR')
    
    else: # kind in ('tarball','tarball-url')
      if kind == 'tarball':
        tgz = value
        me.depend_files(tgz) # in case the user changes the tarball but not its path
      else: # kind == 'tarball-url'
        url = value
        tgz = me.mktemp()
        
        @async.launched
        def download():
          import urllib
          urllib.urlretrieve(url, tgz)
        
        print>>sys.stderr, 'Downloading %s' % url
        yield download()
        print>>sys.stderr, 'Finished    %s' % url
      
      untar_dir = me.mkpath(key=None)
      os.makedirs(untar_dir)
      
      import tarfile
      with tarfile.open(tgz) as f:
        source_dir = os.path.join(untar_dir, f.members[0].name)
        f.extractall(untar_dir)
    
    yield source_dir

@rule_memoized()
class gasnet_config:
  """
  Returns (argv:list, env:dict) pair corresponding to the context
  in which gasnet's other/contrib/cross-configure-{xxx} script runs
  configure.
  """
  
  @traced
  @coroutine
  def get_cross_and_gasnet_src(me, cxt):
    cross = env('CROSS', None)
    kind, value = cxt.gasnet_user()
    
    if cross and kind == 'install':
      raise errorlog.LoggedError(
        'Configuration Error',
        'It is invalid to use both cross-compile (CROSS) and ' +
        'externally installed gasnet (GASNET).'
      )
    
    gasnet_src = None
    if cross:
      gasnet_src = yield cxt.gasnet_source()
    
    yield (cross, gasnet_src)
  
  @traced
  def touch_env(me, cxt, *names):
    """Place dependendcies on environment variables."""
    for name in names:
      me.depend_fact(key=name, value=env(name, None))
  
  @coroutine
  def execute(me):
    cross, gasnet_src = yield me.get_cross_and_gasnet_src()
    
    if cross is None:
      yield ([], {})
      return
    
    # add "canned" env-var dependencies of scripts here
    if cross == 'cray-aries-slurm':
      me.touch_env('SRUN')
    elif cross == 'bgq':
      me.touch_env('USE_GCC','USE_CLANG')
    
    path = os.path.join
    crosslong = 'cross-configure-' + cross
    crosspath = path(gasnet_src, 'other', 'contrib', crosslong)
    
    if not os_extra.exists(crosspath):
      raise errorlog.LoggedError('Configuration Error', 'Invalid GASNet cross-compile script name (%s).'%cross)
    
    # Create a shallow copy of the gasnet source tree minus the
    # "configure" file.
    tmpd = me.mkdtemp()
    os_extra.mktree(
      tmpd,
      dict([
          (x, path(gasnet_src, x))
          for x in os_extra.listdir(gasnet_src)
          if x != 'configure'
        ] +
        [(crosslong, crosspath)]
      ),
      symlinks=True
    )
    
    # Add our own shim "configure" which will reap the command line args
    # and environment variables and punt them back to stdout.
    with open(path(tmpd, 'configure'), 'w') as f:
      f.write(
"""#!/usr/bin/env python
import os
import sys
sys.stdout.write(repr((sys.argv, os.environ)))
""")
    os.chmod(path(tmpd, 'configure'), 0777)
    
    # Run the cross-configure script.
    import subprocess as subp
    p = subp.Popen([path(tmpd, crosslong)], cwd=tmpd, stdout=subp.PIPE, stdin=subp.PIPE, stderr=subp.STDOUT)
    out, _ = p.communicate('')
    if p.returncode != 0:
      raise errorlog.LoggedError('Configuration Error', 'GASNet cross-compile script (%s) failed.'%cross)
    argv, env = eval(out)
    
    # Skip the first argument since that's just "configure".
    argv = argv[1:]
    
    # Only record the environment delta.
    keep = ('CC','CXX','HOST_CC','HOST_CXX',
            'MPI_CC','MPI_CFLAGS','MPI_LIBS','MPIRUN_CMD')
    env0 = os.environ
    for x in env0:
      if x in keep: continue
      if x.startswith('CROSS_'): continue
      if x not in env: continue
      if env[x] != env0[x]: continue
      del env[x]
    
    yield (argv, env)

@rule_memoized()
class gasnet_configured:
  """
  Returns a configured gasnet build directory.
  """
  @traced
  def get_gasnet_user(me, cxt):
    return cxt.gasnet_user()
  
  @traced
  @coroutine
  def get_config(me, cxt):
    cc = yield cxt.cc()
    cc_ver = version_of(cc)
    me.depend_fact(key='CC', value=cc_ver)
    
    cxx = yield cxt.cxx()
    cxx_ver = version_of(cxx)
    me.depend_fact(key='CXX', value=cxx_ver)
    
    config = yield cxt.gasnet_config()
    source_dir = yield cxt.gasnet_source()
    
    yield (cc, cxx, cxt.cg_optlev_default(), cxt.cg_dbgsym(), config, source_dir)
  
  @coroutine
  def execute(me):
    kind, value = yield me.get_gasnet_user()
    
    if kind == 'build':
      build_dir = value
    else:
      cc, cxx, optlev, debug, config, source_dir = yield me.get_config()
      config_args, config_env = config
      
      build_dir = me.mkpath(key=None)
      os.makedirs(build_dir)
      
      env1 = dict(os.environ)
      env1.update(config_env)
      
      if 'CC' not in env1:
        env1['CC'] = ' '.join(cc + ['-O%d'%optlev])
      if 'CXX' not in env1:
        env1['CXX'] = ' '.join(cxx + ['-O%d'%optlev])
      
      misc_conf_opts = [
        # disable non-EX conduits to prevent configure failures when that hardware is detected
        '--disable-psm','--disable-mxm','--disable-portals4','--disable-ofi',
      ]
      
      print>>sys.stderr, 'Configuring GASNet...'
      yield subexec.launch(
        [os.path.join(source_dir, 'configure')] +
        config_args +
        (['--enable-debug'] if debug else []) +
        misc_conf_opts,
        
        cwd = build_dir,
        env = env1
      )
    
    yield build_dir

@rule_memoized(cli='gasnet')
class gasnet:
  """
  Build gasnet. Return library dependencies dictionary.
  """
  @traced
  def get_config(me, cxt):
    kind, value = cxt.gasnet_user()
    return futurize(
      cxt.gasnet_conduit(),
      cxt.gasnet_syncmode(),
      kind,
      value if kind == 'install' else cxt.gasnet_configured()
    )
  
  @coroutine
  def execute(me):
    conduit, syncmode, kind, build_or_install_dir \
      = yield me.get_config()
    
    if kind != 'install':
      build_dir = build_or_install_dir
      print>>sys.stderr, 'Building GASNet (conduit=%s, threading=%s)...'%(conduit, syncmode)
      yield subexec.launch(
        ['make', syncmode],
        cwd = os.path.join(build_dir, '%s-conduit'%conduit)
      )
    
    makefile = os.path.join(*(
      [build_or_install_dir] +
      (['include'] if kind == 'install' else []) +
      ['%s-conduit'%conduit, '%s-%s.mak'%(conduit, syncmode)]
    ))
    
    GASNET_LD = makefile_extract(makefile, 'GASNET_LD').split()
    GASNET_LDFLAGS = makefile_extract(makefile, 'GASNET_LDFLAGS').split()
    GASNET_CXXCPPFLAGS = makefile_extract(makefile, 'GASNET_CXXCPPFLAGS').split()
    GASNET_CXXFLAGS = makefile_extract(makefile, 'GASNET_CXXFLAGS').split()
    GASNET_LIBS = makefile_extract(makefile, 'GASNET_LIBS').split()
    
    if kind == 'install':
      # use gasnet install in-place
      incdirs = []
      incfiles = []
      libfiles = []
    else:
      # pull "-I..." arguments out of GASNET_CXXCPPFLAGS
      incdirs = [x for x in GASNET_CXXCPPFLAGS if x.startswith('-I')]
      GASNET_CXXCPPFLAGS = [x for x in GASNET_CXXCPPFLAGS if x not in incdirs]
      incdirs = [x[2:] for x in incdirs] # drop "-I" prefix
      
      makefile = os.path.join(build_dir, 'Makefile')
      source_dir = makefile_extract(makefile, 'TOP_SRCDIR')
      incfiles = makefile_extract(makefile, 'include_HEADERS').split()
      incfiles = [os.path.join(source_dir, i) for i in incfiles]
    
      # pull "-L..." arguments out of GASNET_LIBS, keep only the "..."
      libdirs = [x[2:] for x in GASNET_LIBS if x.startswith('-L')]
      # pull "-l..." arguments out of GASNET_LIBS, keep only the "..."
      libnames = [x[2:] for x in GASNET_LIBS if x.startswith('-l')]
      
      # filter libdirs for those made by gasnet
      libdirs = [x for x in libdirs if path_within_dir(x, build_or_install_dir)]
      
      # find libraries in libdirs
      libfiles = []
      libnames_matched = set()
      for libname in libnames:
        lib = 'lib' + libname + '.a'
        for libdir in libdirs:
          libfile = os.path.join(libdir, lib)
          if os.path.exists(libfile):
            # assert same library not found under multiple libdir paths
            assert libname not in libnames_matched
            libfiles.append(libfile)
            libnames_matched.add(libname)
      
      # prune extracted libraries from GASNET_LIBS
      GASNET_LIBS = [x for x in GASNET_LIBS
        if not(
          (x.startswith('-L') and x[2:] in libdirs) or
          (x.startswith('-l') and x[2:] in libnames_matched)
        )
      ]
    
    yield {
      'gasnet': {
        'primary': True,
        'incdirs': incdirs,
        'incfiles': incfiles,
        'ld': GASNET_LD,
        'ldflags': GASNET_LDFLAGS,
        'ppflags': GASNET_CXXCPPFLAGS,
        'cgflags': GASNET_CXXFLAGS,
        'libfiles': libfiles,
        'libflags': GASNET_LIBS,
        'deplibs': [] # all dependencies flattened into libflags by gasnet
      }
    }

@rule(cli='run', path_arg='main_src')
@coroutine
def run(cxt, main_src, *args):
  """
  Build the executable for `main_src` and run it with the given
  argument list `args`.
  """
  exe = yield cxt.executable(main_src)
  os.execvp(exe, [exe] + map(str, args))

########################################################################
## Utilties
########################################################################

def env(name, otherwise):
  """
  Read `name` from the environment returning it as an integer if it
  looks like one otherwise a string. If `name` does not exist in the 
  environment then `otherwise` is returned.
  """
  try:
    got = os.environ[name]
    try: return int(got)
    except ValueError: pass
    return got
  except KeyError:
    return otherwise

def makefile_extract(makefile, varname):
  """
  Extract a variable's value from a makefile.
  -s (or --no-print-directory) is required to ensure correct behavior when nobs was invoked by make
  """
  import subprocess as sp
  p = sp.Popen(['make','-s','-f','-','gimme'], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE)
  tmp = ('include {0}\n' + 'gimme:\n' + '\t@echo $({1})\n').format(makefile, varname)
  val, _ = p.communicate(tmp)
  if p.returncode != 0:
    raise Exception('Makefile %s not found.'%makefile)
  val = val.strip(' \t\n')
  return val

def path_within_dir(path, dirpath):
  rel = os.path.relpath(path, dirpath)
  return path == dirpath or not rel.startswith('..' + os.path.sep)

########################################################################

def libset_merge_inplace(dst, src):
  """
  Merge libraries of `src` into `dst`.
  """
  for k,v in src.items():
    v1 = dict(dst.get(k,v))
    v1_primary = v1['primary']
    
    v1['primary'] = v['primary']
    if v != v1:
      raise Exception("Multiple '%s' libraries with differing configurations." % k)
    
    v1['primary'] = v['primary'] or v1_primary
    dst[k] = v1

def libset_merge(*libsets):
  """
  Combine series of libsets into one returned libset.
  """
  ans = {}
  for x in libsets:
    libset_merge_inplace(ans, x)
  return ans

def libset_as_secondary(libset):
  """
  Return new libset with all libraries in set as non-primary (primary=False).
  """
  ans = {}
  for k,v in libset.items():
    if not v['primary']:
      ans[k] = v
    else:
      ans[k] = dict(v)
      ans[k]['primary'] = False
  return ans

def libset_ppflags(libset):
  flags = []
  for rec in libset.values():
    flags.extend(rec.get('ppflags', []))
  for rec in libset.values():
    for d in rec.get('incdirs', []):
      flag = '-I' + d
      if flag not in flags:
        flags.append(flag)
  return flags

def libset_cgflags(libset):
  flags = []
  for rec in libset.values():
    flags.extend(rec.get('cgflags', []))
  return flags

def libset_ld(libset):
  lds = set(tuple(x.get('ld',())) for x in libset.values())
  lds.discard(())
  if len(lds) == 0:
    return None
  if len(lds) != 1:
    raise Exception("Multiple linkers demanded:" + ''.join(map(lambda x:'\n  '+' '.join(x), lds)))
  return list(lds.pop())

def libset_ldflags(libset):
  flags = []
  for rec in libset.values():
    flags.extend(rec.get('ldflags', []))
  return flags

def libset_libflags(libset):
  """
  Generate link-line library flags from a topsort over
  library-library dependencies.
  """
  sorted_lpaths = []
  sorted_flags = []
  visited = set()
  
  def topsort(xs):
    for x in xs:
      rec = libset.get(x, {x:{'libflags':['-l'+x]}})
      
      topsort(rec.get('deplibs', []))
      
      if x not in visited:
        visited.add(x)

        libfiles = rec.get('libfiles', [])
        
        sorted_lpaths.append(
          ['-L' + os.path.dirname(f) for f in libfiles]
        )
        sorted_flags.append(
          ['-l' + os.path.basename(f)[3:-2] for f in libfiles] +
          rec.get('libflags', [])
        )
  
  def uniquify(xs):
    ys = []
    for x in xs:
      if x not in ys:
        ys.append(x)
    return ys
  
  topsort(libset)
  
  sorted_lpaths.reverse()
  sorted_lpaths = sum(sorted_lpaths, [])
  sorted_lpaths = uniquify(sorted_lpaths)
  
  sorted_flags.reverse()
  sorted_flags = sum(sorted_flags, [])
  
  return sorted_lpaths + sorted_flags

def install_libset(install_path, name, libset):
  """
  Install a library set to the given path. Produces headers and binaries
  in the typical "install_path/{bin,include,lib}" structure. Also
  creates a metadata retrieval script "bin/${name}-meta" (similar in
  content to a pkgconfig script) for querying the various compiler and
  linker flags.
  """
  base_of = os.path.basename
  join = os.path.join
  up = '..' + os.path.sep
  link_or_copy = os_extra.link_or_copy
  
  undo = []
  
  try:
    libfiles_all = []
    installed_libset = {}
    
    for xname,rec in libset.items():
      incdirs = rec.get('incdirs', [])
      incfiles = rec.get('incfiles', [])
      libfiles = rec.get('libfiles')
      
      incfiles1 = []
      libfiles_all.extend(libfiles or [])
      
      # copy includes
      for f in incfiles:
        # copy for each non-upwards relative path
        for d in reversed(incdirs):
          rp = os.path.relpath(f,d)
          if not rp.startswith(up):
            # copy include file to relative path under "install_path/include"
            src = join(d, rp)
            dest = join(install_path, 'include', rp)
            
            incfiles1.append(dest)
            os_extra.ensure_dirs(dest)
            undo.append(dest)
            link_or_copy(src, dest, overwrite=False)
      
      # produce installed version of library record
      rec1 = dict(rec)
      rec1['incdirs'] = [join(install_path, 'include')]
      rec1['incfiles'] = incfiles1
      if libfiles is not None:
        rec1['libfiles'] = [join(install_path, 'lib', base_of(f)) for f in libfiles]
      
      installed_libset[xname] = rec1
    
    # copy libraries
    if len(libfiles_all) != len(set(map(base_of, libfiles_all))):
      raise errorlog.LoggedError(
        'ERROR: Duplicate library names in list:\n  ' + '\n  '.join(libfiles_all)
      )
    
    for f in libfiles_all:
      dest = join(install_path, 'lib', base_of(f))
      undo.append(dest)
      os_extra.ensure_dirs(dest)
      link_or_copy(f, dest, overwrite=False)
    
    # produce metadata script
    meta = join(install_path, 'bin', name+'-meta')
    undo.append(meta)
    os_extra.ensure_dirs(meta)
    with open(meta, 'w') as fo:
      fo.write(
'''#!/bin/sh
PPFLAGS="''' + ' '.join(libset_ppflags(installed_libset)) + '''"
LDFLAGS="''' + ' '.join(libset_ldflags(installed_libset)) + '''"
LIBFLAGS="''' + ' '.join(libset_libflags(installed_libset)) + '''"
[ "$1" != "" ] && eval echo '$'"$1"
''')
    os.chmod(meta, 0777)
    
  except Exception as e:
    for f in undo:
      try: os_extra.rmtree(f)
      except OSError: pass
    
    if isinstance(e, OSError) and e.errno == 17: # File exists
      raise errorlog.LoggedError(
        'Installation aborted because it would clobber files in "'+install_path+'"'
      )
    else:
      raise
