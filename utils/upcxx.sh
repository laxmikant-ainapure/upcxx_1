#!/bin/bash

function error {
  echo "upcxx: error:" "$@" >&2
  exit 1
}

doverbose=0
function verbose {
  if [[ $doverbose == 1 ]]; then
    echo "upcxx:" "$@" >&2
  fi
}

if ! test -x "$UPCXX_META" ; then
  error UPCXX_META not found
fi
prefix="`dirname $UPCXX_META`/.."
if ! test -d "$prefix" ; then
  error install prefix $prefix not found
fi

dolink=1
doversion=
dodebug=
doopt=
shopt -u nocasematch # ensure case-sensitive match below
for arg in "$@" ; do
  case $arg in 
    -MD) : ;; # -MD does not imply preprocess
    -E|-c|-S|-M*) dolink=0 ;;
    -v|-vv) doverbose=1 ;;
    -V|-version|--version) 
      doversion=1
    ;;
    -g*) dodebug=1 ;;
    -O*) doopt=1 ;;
  esac
done
verbose dolink=$dolink
verbose UPCXX_META=$UPCXX_META

if [[ $dodebug && !$doopt ]] ; then
  UPCXX_CODEMODE=debug
elif [[ ( $doopt && !$dodebug ) || $doversion ]] ; then
  UPCXX_CODEMODE=O3
elif [[ $UPCXX_CODEMODE ]] ; then
  :
else
  error "please specify exactly one of -O or -g, otherwise set UPCXX_CODEMODE={O3,debug}"
fi
export UPCXX_CODEMODE

for var in UPCXX_CODEMODE UPCXX_GASNET_CONDUIT UPCXX_THREADMODE ; do
  eval verbose $var=\$$var
done

for var in CXX CXXFLAGS CPPFLAGS LDFLAGS LIBS ; do 
  val=`$UPCXX_META $var`
  eval $var=\$val
  verbose "$UPCXX_META $var: $val"
done
EXTRAFLAGS=""
if [[ $doversion ]] ; then
  header="$prefix/upcxx.*/include/upcxx/upcxx.hpp"
  version=`(grep "#define UPCXX_VERSION" $header | head -1 | cut -d' ' -f 3 ) 2> /dev/null`
  githash=`(cat $prefix/share/doc/upcxx/docs/version.git ) 2> /dev/null`
  gexhash=`(cat $prefix/gasnet.*/share/doc/GASNet/version.git | head -1 ) 2> /dev/null`
  if [[ -n $gexhash ]] ; then
    gexhash=" / $gexhash"
  fi
  echo "UPC++ version $version $githash$gexhash"
  echo "Copyright (c) 2018, The Regents of the University of California,"
  echo "through Lawrence Berkeley National Laboratory."
  echo "https://upcxx.lbl.gov"
  echo ""
  $CXX --version
  exit 0
fi

function doit {
  verbose "$@"
  exec "$@"
}

if [[ $dolink == 0 ]] ; then
  doit $CXX $EXTRAFLAGS $CXXFLAGS $CPPFLAGS "$@"
else
  doit $CXX $EXTRAFLAGS $CXXFLAGS $CPPFLAGS $LDFLAGS "$@" $LIBS
fi
error failed to run compiler $CXX

