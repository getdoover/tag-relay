#!/bin/sh

# Build the Lambda deploy zip.
#
# Lambda runtime is pinned to arm64 via lambda_config.Architectures in
# doover_config.json — we only build aarch64 wheels. We still install for
# both Python 3.12 and 3.13, because native extensions carry their ABI in
# the filename (e.g. `cel.cpython-313-aarch64-linux-gnu.so`) and both
# files coexist; whichever Python Lambda picks will load the matching
# .so, guarding against a silent runtime-version surprise.

set -e

rm -rf packages_export packages_export_extra

uv export --frozen --no-dev --no-editable --quiet -o requirements.txt

install_for() {
    py="$1"
    target="$2"
    uv pip install \
        --no-deps \
        --no-installer-metadata \
        --no-compile-bytecode \
        --python-platform aarch64-manylinux2014 \
        --python "$py" \
        --quiet \
        --target "$target" \
        --refresh \
        -r requirements.txt
}

# Primary install: Python 3.13 — becomes the base layout.
install_for 3.13 packages_export

# Add the Python 3.12 native extensions alongside. Pure-Python files are
# identical across versions so we only need the .so files from the 3.12
# pass.
rm -rf packages_export_extra
install_for 3.12 packages_export_extra
find packages_export_extra -name "*.so" -print0 | while IFS= read -r -d '' src; do
    dest="packages_export/${src#packages_export_extra/}"
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
done
rm -rf packages_export_extra

rm -f package.zip
mkdir -p packages_export
cd packages_export
zip -rq ../package.zip .
cd ..

zip -rq package.zip src

echo "OK"
