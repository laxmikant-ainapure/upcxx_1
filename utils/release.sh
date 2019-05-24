#!/bin/bash

set -e

REPO=${REPO:-origin}
BRANCH=${BRANCH:-master}

REPOURL=$(git remote get-url $REPO)
RELEASE=$(git describe ${REPO}/${BRANCH})
OFFLINE=${RELEASE}-offline

if [[ -e ${OFFLINE} ]]; then
  echo "ERROR: refusing to overwrite ${OFFLINE}."
  exit 1
fi

# Indirection to deal w/ Linux vs macOS differences
if [[ $(uname -s) = 'Darwin' ]]; then
  MD5_CMD='md5 -r'
  B64_CMD='base64 -D'
  WWW_CMD='curl -LOsS'
else
  MD5_CMD='md5sum'
  B64_CMD='base64 -d'
  WWW_CMD='wget -q'
fi

echo "Building releases from BRANCH=$BRANCH in REPO=$REPO ($REPOURL)"

set -x

# Build main "online" installer:
RELEASE_TGZ=${RELEASE}.tar.gz
git archive --remote=${REPO} ${BRANCH} --prefix=${RELEASE}/ --format=tar.gz --output=${RELEASE_TGZ}
if ! gzip -t ${RELEASE_TGZ}; then
  echo 'ERROR: release tarball failed "gzip -t"' >&2
  exit 1
fi
UPCXX_HASH=$(zcat ${RELEASE_TGZ} | git get-tar-commit-id)

# Extract GASNet-EX URL:
GASNET_URL=$(tar xOfz ${RELEASE_TGZ} ${RELEASE}/nobsrule.py | grep -m1 'GASNet-.*\.tar\.gz' | cut -d\' -f2)
GASNET=$(basename "${GASNET_URL}" .tar.gz)

# Build alternative "offline" installer:
git archive --remote=${REPO} ${BRANCH} --prefix=${OFFLINE}/ --format=tar --output=${OFFLINE}.tar
mkdir -p ${OFFLINE}/src
(cd ${OFFLINE}/src && $WWW_CMD "${GASNET_URL}")
GASNET_TGZ=${OFFLINE}/src/${GASNET}.tar.gz
GEX_MD5SUM="$( $MD5_CMD ${GASNET_TGZ} | cut -d\  -f1 )"
if ! gzip -t $GASNET_TGZ; then
  echo 'ERROR: GASNet-EX tarball failed "gzip -t"' >&2
  exit 1
fi
# Rename GEX tarball to full version name (undo patch obfuscation)
GASNET=$(tar tf $GASNET_TGZ | head -1 | cut -d/ -f1)
GASNET_TGZ_NEW=${OFFLINE}/src/${GASNET}.tar.gz
if test "$GASNET_TGZ" != "$GASNET_TGZ_NEW" ; then
  mv $GASNET_TGZ $GASNET_TGZ_NEW
  GASNET_TGZ=$GASNET_TGZ_NEW
fi

GEX_DESCRIBE=$(tar xOzf ${GASNET_TGZ} ${GASNET}/version.git)
tar -r -f ${OFFLINE}.tar --owner=root --group=root ${OFFLINE}/src/${GASNET}.tar.gz
gzip -9f ${OFFLINE}.tar
if ! gzip -t ${OFFLINE}.tar.gz; then
  echo 'ERROR: offline tarball failed "gzip -t"' >&2
  exit 1
fi
rm -R ${OFFLINE}

set +x

echo
echo "INPUT SUMMARY:"
echo "-------------"
echo "Repo:               $REPO ($REPOURL)"
echo "Branch:             $BRANCH"
echo "Release version:    ${RELEASE#upcxx-}"
echo "UPC++ commit hash:  ${UPCXX_HASH}"
echo "GASNet-EX describe: ${GEX_DESCRIBE}"
echo "GASNet-EX checksum: ${GEX_MD5SUM}"
echo
echo "OUTPUT SUMMARY:"
echo "--------------"
$MD5_CMD ${RELEASE_TGZ} ${OFFLINE}.tar.gz
