function install_common {
  CONDUITS=$(echo $CONDUITS) # newlines become spaces
  conduits_pipes="${CONDUITS// /|}"
  conduits_commas="${CONDUITS// /, }"

  mkdir -p "${DESTDIR}${install_to}/bin"
  cat <<EOF >| "${DESTDIR}${install_to}/bin/upcxx-meta"
#!/bin/bash
# This file is generated during installation - do not edit

function echo_and_die {
  echo \$* >&2
  exit 1
}

# Validate the cross-compile Cray CPU target, if any
UPCXX_CRAY_CPU_TARGET=${CROSS:+$CRAY_CPU_TARGET}
if test -n "\$UPCXX_CRAY_CPU_TARGET" && test "\$UPCXX_CRAY_CPU_TARGET" != "\$CRAY_CPU_TARGET"; then
  echo "WARNING: This UPC++ installation was built for \$UPCXX_CRAY_CPU_TARGET CPUs, but you are currently compiling for \$CRAY_CPU_TARGET"
  echo "WARNING: This can lead to non-working executables and/or serious performance degradation."
  echo "WARNING: Please load the appropriate craype-\$UPCXX_CRAY_CPU_TARGET module, or use a UPC++ install built for this CPU."
  echo " "
fi 1>&2

PARAMS="CPPFLAGS PPFLAGS CFLAGS CXXFLAGS LIBS LIBFLAGS LDFLAGS CXX CC GASNET_CONDUIT GASNET_INSTALL SET DUMP"
FAIL=true
for P in \$PARAMS; do
    if [[ "\$1" == "\$P" ]]; then
        FAIL=false
        break
    fi
done

if [[ \$FAIL == true ]]; then
    echo_and_die "Error: parameter passed to upcxx-meta must be one of \$PARAMS"
fi

case \${UPCXX_CODEMODE} in
"")
  UPCXX_CODEMODE=O3
  ;;
debug|O3)
  ;;
*)
  echo_and_die "UPCXX_CODEMODE must be set to one of: O3 (default), debug"
  ;;
esac

case \${UPCXX_THREADMODE} in
"")
  UPCXX_THREADMODE=seq
  ;;
seq|par)
  ;;
*)
  echo_and_die "UPCXX_THREADMODE must be set to one of: seq (default), par"
  ;;
esac

UPCXX_NETWORK=\${UPCXX_NETWORK:-\$UPCXX_GASNET_CONDUIT} # backwards-compat
case "\${UPCXX_NETWORK}" in
'')
  UPCXX_NETWORK="${conduit_default}"
  ;;
${conduits_pipes})
  ;;
*)
  echo_and_die "UPCXX_NETWORK must be one of: ${conduits_commas}"
  ;;
esac

case \${UPCXX_THREADMODE} in
seq)
  UPCXX_BACKEND=gasnet_seq
  ;;
par)
  UPCXX_BACKEND=gasnet_par
  ;;
esac

meta="${install_to}/upcxx.\${UPCXX_CODEMODE}.\${UPCXX_BACKEND}.\${UPCXX_NETWORK}/bin/upcxx-meta"

if [[ "\$1" == "SET" ]] ; then
  source "\$meta" ""
elif [[ "\$1" == "DUMP" ]] ; then
  # this opens and dumps the variables from the subordinate upcxx-meta
  # do NOT add any subshells or process forks here, as this branch is motivated by performance
  i=0
  while read line; do
    [ \$((i++)) == 0 ] && continue # omit she-bang
    [ "\$line" == "" ] && break    # empty line signals end
    echo "\$line"
  done < "\$meta"
else
  exec "\$meta" \$*
fi
EOF
  chmod 755 "${DESTDIR}${install_to}/bin/upcxx-meta"
  cat <<EOF >| "${DESTDIR}${install_to}/bin/upcxx"
#!/bin/bash
UPCXX_META="${install_to}/bin/upcxx-meta"
export UPCXX_META
source "${install_to}/bin/upcxx.sh" "\$@"
EOF
  chmod 755 "${DESTDIR}${install_to}/bin/upcxx"
  cp ./utils/upcxx.sh "${DESTDIR}${install_to}/bin/upcxx.sh"
  chmod 755 "${DESTDIR}${install_to}/bin/upcxx.sh"
  cp ./utils/upcxx-run "${DESTDIR}${install_to}/bin/upcxx-run"
  chmod 755 "${DESTDIR}${install_to}/bin/upcxx-run"
  # install documentation
  docdir="${DESTDIR}${install_to}/share/doc/upcxx"
  mkdir -p $docdir
  cp -f -R README.md ChangeLog.md LICENSE.txt docs $docdir
  chmod -R a+rX $docdir
  # install cmake module
  cmakedir="${DESTDIR}${install_to}/share/cmake/UPCXX"
  mkdir -p $cmakedir
  cp -f -R utils/cmake/UPCXXConfig.cmake $cmakedir
  chmod -R a+rX $cmakedir
}
