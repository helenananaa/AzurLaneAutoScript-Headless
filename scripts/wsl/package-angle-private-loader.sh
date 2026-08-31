#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <AngleLibraries.apk> <x64|arm64> <ANGLE source root>" >&2
  exit 2
fi

apk="$1"
target_cpu="$2"
angle_dir="$3"
case "$target_cpu" in
  x64) abi="x86_64" ;;
  arm64) abi="arm64-v8a" ;;
  *) echo "unsupported ANGLE target CPU: $target_cpu" >&2; exit 2 ;;
esac

for command in unzip zip zipinfo perl; do
  command -v "$command" >/dev/null || {
    echo "required command is unavailable: $command" >&2
    exit 1
  }
done

mapfile -t signer_candidates < <(
  find "$angle_dir/third_party/android_sdk" -type f -path '*/build-tools/*/apksigner' -print |
    sort -V
)
[[ ${#signer_candidates[@]} -gt 0 ]] || {
  echo "ANGLE Android SDK apksigner is unavailable" >&2
  exit 1
}
apksigner="${signer_candidates[-1]}"
zipalign="$(dirname "$apksigner")/zipalign"
keystore="$angle_dir/build/android/chromium-debug.keystore"
[[ -x "$zipalign" && -f "$keystore" ]] || {
  echo "ANGLE zipalign or Chromium debug keystore is unavailable" >&2
  exit 1
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/tree"
unzip -q "$apk" -d "$work/tree"
libdir="$work/tree/lib/$abi"

egl="$libdir/libEGL_angle.so"
gles1="$libdir/libGLESv1_CM_angle.so"
gles2="$libdir/libGLESv2_angle.so"
private_egl="$libdir/libEGL_alasx.so"
private_gles1="$libdir/libGLESv1_CM_alasx.so"
private_gles2="$libdir/libGLESv2_alasx.so"
rules="$work/tree/assets/a4a_rules.json"
for library in "$egl" "$gles1" "$gles2"; do
  [[ -f "$library" ]] || { echo "missing ANGLE APK library: $library" >&2; exit 1; }
done
[[ -f "$rules" ]] || { echo "missing ANGLE APK rules asset: $rules" >&2; exit 1; }

# autoninja may leave an unchanged, already packaged APK in place.  Verify and
# preserve it instead of trying to rewrite the private SONAMEs a second time.
if [[ -f "$private_egl" && -f "$private_gles1" && -f "$private_gles2" ]] &&
   LC_ALL=C grep -aqF 'libEGL_angle.so' "$egl" &&
   ! LC_ALL=C grep -aqF 'libEGL_alasx.so' "$egl" &&
   LC_ALL=C grep -aqF 'libGLESv1_CM_angle.so' "$gles1" &&
   ! LC_ALL=C grep -aqF 'libGLESv1_CM_alasx.so' "$gles1" &&
   LC_ALL=C grep -aqF 'libGLESv2_angle.so' "$gles2" &&
   ! LC_ALL=C grep -aqF 'libGLESv2_alasx.so' "$gles2" &&
   LC_ALL=C grep -aqF 'libEGL_alasx.so' "$private_egl" &&
   LC_ALL=C grep -aqF 'libGLESv2_alasx' "$private_egl" &&
   ! LC_ALL=C grep -aqF 'libGLESv2_angle' "$private_egl" &&
   LC_ALL=C grep -aqF 'libGLESv1_CM_alasx.so' "$private_gles1" &&
   LC_ALL=C grep -aqF 'libGLESv2_alasx.so' "$private_gles2" &&
   zipinfo -v "$apk" assets/a4a_rules.json |
     grep -Fq 'compression method:                             none (stored)'; then
  "$apksigner" verify "$apk"
  exit 0
fi

rm -rf "$work/tree/META-INF"

# An interrupted or older packager may have rewritten the upstream aliases in
# place before copying them. Normalize those aliases first so a private request
# cannot reuse a handle carrying the wrong filename or dependency identity.
# Every replacement is deliberately equal length.
LC_ALL=C perl -pi -e 's/libEGL_alasx\.so/libEGL_angle.so/g' "$egl"
LC_ALL=C perl -pi -e 's/libGLESv1_CM_alasx\.so/libGLESv1_CM_angle.so/g' "$gles1"
LC_ALL=C perl -pi -e 's/libGLESv2_alasx\.so/libGLESv2_angle.so/g' \
  "$gles1" "$gles2"

[[ $(LC_ALL=C grep -aoF 'libEGL_angle.so' "$egl" | wc -l) -eq 1 ]]
[[ $(LC_ALL=C grep -aoF 'libGLESv2_angle' "$egl" | wc -l) -eq 1 ]]
[[ $(LC_ALL=C grep -aoF 'libGLESv1_CM_angle.so' "$gles1" | wc -l) -eq 1 ]]
[[ $(LC_ALL=C grep -aoF 'libGLESv2_angle.so' "$gles1" | wc -l) -eq 1 ]]
[[ $(LC_ALL=C grep -aoF 'libGLESv2_angle.so' "$gles2" | wc -l) -eq 1 ]]

# Keep the upstream files and SONAMEs intact for older Android releases.  Only
# the copies requested by the Android 14 image patch receive private SONAMEs
# and dependencies, so the linker cannot satisfy a private request with an
# already-loaded upstream alias.  All replacements are deliberately equal
# length.
cp "$egl" "$private_egl"
cp "$gles1" "$private_gles1"
cp "$gles2" "$private_gles2"
LC_ALL=C perl -pi -e 's/libEGL_angle\.so/libEGL_alasx.so/g' "$private_egl"
# libEGL constructs the GLES implementation name from the stem without the
# .so suffix.  Rewriting only SONAME/DT_NEEDED strings leaves it opening the
# upstream GLES library and creates two ANGLE instances with separate TLS.
LC_ALL=C perl -pi -e 's/libGLESv2_angle/libGLESv2_alasx/g' "$private_egl"
LC_ALL=C perl -pi -e 's/libGLESv1_CM_angle\.so/libGLESv1_CM_alasx.so/g' "$private_gles1"
LC_ALL=C perl -pi -e 's/libGLESv2_angle\.so/libGLESv2_alasx.so/g' \
  "$private_gles1" "$private_gles2"

! LC_ALL=C grep -aqF 'libEGL_alasx.so' "$egl"
! LC_ALL=C grep -aqF 'libGLESv1_CM_alasx.so' "$gles1"
! LC_ALL=C grep -aqF 'libGLESv2_alasx.so' "$gles2"
! LC_ALL=C grep -aqF 'libGLESv2_angle' "$private_egl"

source_date_epoch="${SOURCE_DATE_EPOCH:-1731467710}"
find "$work/tree" -exec touch -h -d "@$source_date_epoch" {} +
(
  cd "$work/tree"
  # AngleLibraries.apk may declare extractNativeLibs=false.  In that mode
  # PackageManager must mmap every native library directly from the APK and
  # rejects compressed .so entries before installation.  Store all ABIs'
  # native libraries and page-align them; compress only the non-native files.
  # GraphicsEnvironment opens a4a_rules.json through an AssetFileDescriptor,
  # which Android cannot provide for a compressed ZIP entry.  Keep that asset
  # stored for the same direct-access reason as extractNativeLibs=false .so files.
  zip -X -q -r "$work/unsigned.apk" . \
    -x 'lib/*/*.so' 'assets/a4a_rules.json'
  zip -X -q -0 "$work/unsigned.apk" lib/*/*.so assets/a4a_rules.json
)
"$zipalign" -P 16 -f 4 "$work/unsigned.apk" "$work/aligned.apk"
"$apksigner" sign \
  --ks "$keystore" \
  --ks-key-alias chromiumdebugkey \
  --ks-pass pass:chromium \
  --key-pass pass:chromium \
  --out "$work/signed.apk" \
  "$work/aligned.apk"
"$apksigner" verify "$work/signed.apk"
mv "$work/signed.apk" "$apk"
