#!/usr/bin/env bash
# Offline-reference tools, user prefix only. No app dependency or redistribution.
# Debian 12 x86_64 prototype; other platforms need separate qualification.
set -euo pipefail
OPT=${SOLVER_OPT:-$HOME/.local/opt/solver-prototypes}
. /etc/os-release
[[ ${VERSION_CODENAME:-} == bookworm && $(uname -m) == x86_64 ]] || {
  echo 'This prototype installer requires Debian 12 x86_64.' >&2; exit 1;
}
for tool in apt-get dpkg-deb dpkg curl tar sha256sum cmake cc c++; do
  command -v "$tool" >/dev/null || { echo "Required host tool not found: $tool" >&2; exit 1; }
done
mkdir -p "$OPT" "$OPT/deps" "$OPT/root" "$OPT/apt"/{state,lists/partial,cache/archives/partial}

archive() {
  local name=$1 url=$2 sha=$3
  if ! echo "$sha  $OPT/$name" | sha256sum -c --status; then
    curl -fsSL --retry 3 --max-time 600 "$url" -o "$OPT/$name"
  fi
  echo "$sha  $OPT/$name" | sha256sum -c
  tar xzf "$OPT/$name" -C "$OPT"
}
archive getdp-3.5.0-Linux64c.tgz https://getdp.info/bin/Linux/getdp-3.5.0-Linux64c.tgz d3c28fa18f20d6147b4c7367d4dd802e9f7ddb58c608688bbb71919dbca8041d
archive gmsh-4.13.1-Linux64.tgz https://gmsh.info/bin/Linux/gmsh-4.13.1-Linux64.tgz 6c9f030d20388392968e40d15f6ebb5e1d46f29c92b7afb14cee728d30e8a08f
archive elmerfem-release-26.2.tar.gz https://github.com/ElmerCSC/elmerfem/releases/download/release-26.2/elmerfem-release-26.2.tar.gz 7addfb102d735929a40929be08be0c16703d734498d33bc70c96e7d526fe249c

cat > "$OPT/apt/apt.conf" <<EOF
Dir::State "$OPT/apt/state";
Dir::State::Lists "$OPT/apt/lists";
Dir::State::status "/var/lib/dpkg/status";
Dir::Cache "$OPT/apt/cache";
APT::Sandbox::User "$(id -un)";
Debug::NoLocking "true";
EOF
export APT_CONFIG="$OPT/apt/apt.conf"
apt-get update
(
  cd "$OPT/deps"
  # Runtime and compiler packages are unpacked, not installed into the system.
  requested=(gfortran gfortran-12 libgfortran5 libgfortran-12-dev
    libblas3 libblas-dev liblapack3 liblapack-dev libglu1-mesa)
  # apt-get download alone does not fetch dependencies. Include missing host
  # dependencies while still fetching requested files into the private prefix.
  simulation=$(apt-get -s install --no-install-recommends "${requested[@]}")
  mapfile -t packages < <({ printf '%s\n' "${requested[@]}";
    awk '/^Inst/ {print $2}' <<< "$simulation"; } | sort -u)
  apt-get download "${packages[@]}"
  sha256sum ./*.deb > sha256.txt
  for deb in ./*.deb; do
    dpkg-deb -f "$deb" Package Version Architecture
    dpkg -x "$deb" "$OPT/root"
  done > packages.txt
)

export LD_LIBRARY_PATH="$OPT/root/usr/lib/x86_64-linux-gnu:$OPT/root/usr/lib/x86_64-linux-gnu/blas:$OPT/root/usr/lib/x86_64-linux-gnu/lapack${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cmake -S "$OPT/elmerfem-release-26.2" -B "$OPT/elmer-build" \
  -DCMAKE_INSTALL_PREFIX="$OPT/elmer-install" \
  -DCMAKE_Fortran_COMPILER="$OPT/root/usr/bin/gfortran" \
  -DCMAKE_Fortran_FLAGS="-B$OPT/root/usr/lib/gcc/x86_64-linux-gnu/12 -B/usr/lib/gcc/x86_64-linux-gnu/12 -L$OPT/root/usr/lib/gcc/x86_64-linux-gnu/12 -L$OPT/root/usr/lib/x86_64-linux-gnu" \
  -DBLAS_LIBRARIES="$OPT/root/usr/lib/x86_64-linux-gnu/blas/libblas.so.3" \
  -DLAPACK_LIBRARIES="$OPT/root/usr/lib/x86_64-linux-gnu/lapack/liblapack.so.3" \
  '-DINCLUDE_ELMER_MODULES=MagnetoDynamics;MagnetoDynamics2D;ResultOutputSolve;SaveData;StatMagSolve;StatCurrentSolve' \
  -DWITH_MPI=OFF -DWITH_ELMERGUI=OFF -DWITH_ElmerIce=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$OPT/elmer-build" -j "${SOLVER_BUILD_JOBS:-2}"
cmake --install "$OPT/elmer-build"

cat > "$OPT/env.sh" <<EOF
export SOLVER_OPT="$OPT"
export PATH="$OPT/elmer-install/bin:$OPT/gmsh-4.13.1-Linux64/bin:$OPT/getdp-3.5.0-Linux64/bin:\$PATH"
export LD_LIBRARY_PATH="$LD_LIBRARY_PATH"
EOF
echo "Reference tools built. Source $OPT/env.sh before running checks."
echo 'Not bundled with pcbmotorgen. Review GPL/LGPL and dependency licenses before any distribution.'
