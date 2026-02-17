#!/bin/bash
set -x
set -e

TARGET_DIR=${1:-target}

TAG_NAME=${TAG_NAME:-$(git -c "core.abbrev=8" show -s "--format=%cd-%h" "--date=format:%Y%m%d-%H%M%S")}

HERE=$(pwd)

if test -z "${SUDO+x}" && hash sudo 2>/dev/null; then
  SUDO="sudo"
fi

if test -e /etc/os-release; then
  . /etc/os-release
fi


case $OSTYPE in
  darwin*)
    # CX Terminal: Updated branding from WezTerm
    APP_NAME="CX Terminal"
    APP_BUNDLE="CX Terminal.app"
    zipdir=CXTerminal-macos-$TAG_NAME
    dmgname=CXTerminal-macos-$TAG_NAME.dmg
    if [[ "$BUILD_REASON" == "Schedule" ]] ; then
      zipname=CXTerminal-macos-nightly.zip
      dmgname=CXTerminal-macos-nightly.dmg
    else
      zipname=$zipdir.zip
    fi
    rm -rf "$zipdir" "$zipname" "$dmgname"
    mkdir "$zipdir"

    # Copy the app template
    cp -r "assets/macos/CX Terminal.app" "$zipdir/$APP_BUNDLE"

    # Omit MetalANGLE for now; it's a bit laggy compared to CGL,
    # and on M1/Big Sur, CGL is implemented in terms of Metal anyway
    rm -f "$zipdir/$APP_BUNDLE"/*.dylib 2>/dev/null || true
    mkdir -p "$zipdir/$APP_BUNDLE/Contents/MacOS"
    mkdir -p "$zipdir/$APP_BUNDLE/Contents/Resources"
    cp -r assets/shell-integration/* "$zipdir/$APP_BUNDLE/Contents/Resources"
    cp -r assets/shell-completion "$zipdir/$APP_BUNDLE/Contents/Resources"
    tic -xe cx-terminal -o "$zipdir/$APP_BUNDLE/Contents/Resources/terminfo" termwiz/data/cx-terminal.terminfo

    # CX Terminal: Updated binary names
    # Map: old name -> new name (for copying into bundle)
    declare -A BIN_MAP=(
      ["cx-terminal"]="cx-terminal"
      ["cx-mux-server"]="cx-mux-server"
      ["cx-terminal-gui"]="cx-terminal-gui"
      ["strip-ansi-escapes"]="strip-ansi-escapes"
    )

    for bin in "${!BIN_MAP[@]}" ; do
      target_name="${BIN_MAP[$bin]}"
      # If the user ran a simple `cargo build --release`, then we want to allow
      # a single-arch package to be built
      if [[ -f $TARGET_DIR/release/$bin ]] ; then
        cp $TARGET_DIR/release/$bin "$zipdir/$APP_BUNDLE/Contents/MacOS/$target_name"
      else
        # The CI runs `cargo build --target XXX --release` which means that
        # the binaries will be deployed in `$TARGET_DIR/XXX/release` instead of
        # the plain path above.
        # In that situation, we have two architectures to assemble into a
        # Universal ("fat") binary, so we use the `lipo` tool for that.
        lipo $TARGET_DIR/*/release/$bin -output "$zipdir/$APP_BUNDLE/Contents/MacOS/$target_name" -create
      fi
    done

    set +x
    if [ -n "$MACOS_TEAM_ID" ] ; then
      MACOS_PW=$(echo $MACOS_CERT_PW | base64 --decode)
      echo "pw sha"
      echo $MACOS_PW | shasum

      # Remove pesky additional quotes from default-keychain output
      def_keychain=$(eval echo $(security default-keychain -d user))
      echo "Default keychain is $def_keychain"
      echo "Speculative delete of build.keychain"
      security delete-keychain build.keychain || true
      echo "Create build.keychain"
      security create-keychain -p "$MACOS_PW" build.keychain
      echo "Make build.keychain the default"
      security default-keychain -d user -s build.keychain
      echo "Unlock build.keychain"
      security unlock-keychain -p "$MACOS_PW" build.keychain
      echo "Import .p12 data"
      echo $MACOS_CERT | base64 --decode > /tmp/certificate.p12
      echo "decoded sha"
      shasum /tmp/certificate.p12
      security import /tmp/certificate.p12 -k build.keychain -P "$MACOS_PW" -T /usr/bin/codesign
      rm /tmp/certificate.p12
      echo "Grant apple tools access to build.keychain"
      security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$MACOS_PW" build.keychain
      echo "Codesign"
      /usr/bin/codesign --keychain build.keychain --force --options runtime \
        --entitlements ci/macos-entitlement.plist --deep --sign "$MACOS_TEAM_ID" "$zipdir/$APP_BUNDLE/"
      echo "Restore default keychain"
      security default-keychain -d user -s $def_keychain
      echo "Remove build.keychain"
      security delete-keychain build.keychain || true
    fi

    set -x

    # Create ZIP archive
    zip -r "$zipname" "$zipdir"

    # CX Terminal: Create DMG installer
    echo "Creating DMG installer..."
    DMG_TEMP="dmg_temp"
    rm -rf "$DMG_TEMP"
    mkdir -p "$DMG_TEMP"
    cp -r "$zipdir/$APP_BUNDLE" "$DMG_TEMP/"
    ln -s /Applications "$DMG_TEMP/Applications"

    # Create DMG with hdiutil
    hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_TEMP" -ov -format UDZO "$dmgname"
    rm -rf "$DMG_TEMP"

    set +x

    if [ -n "$MACOS_TEAM_ID" ] ; then
      echo "Notarize ZIP"
      xcrun notarytool submit "$zipname" --wait --team-id "$MACOS_TEAM_ID" --apple-id "$MACOS_APPLEID" --password "$MACOS_APP_PW"

      echo "Notarize DMG"
      xcrun notarytool submit "$dmgname" --wait --team-id "$MACOS_TEAM_ID" --apple-id "$MACOS_APPLEID" --password "$MACOS_APP_PW"

      echo "Staple notarization ticket to DMG"
      xcrun stapler staple "$dmgname"
    fi
    set -x

    SHA256=$(shasum -a 256 $zipname | cut -d' ' -f1)
    sed -e "s/@TAG@/$TAG_NAME/g" -e "s/@SHA256@/$SHA256/g" < ci/cx-terminal-homebrew-macos.rb.template > cx-terminal.rb

    ;;
  msys)
    zipdir=WezTerm-windows-$TAG_NAME
    if [[ "$BUILD_REASON" == "Schedule" ]] ; then
      zipname=WezTerm-windows-nightly.zip
      instname=WezTerm-nightly-setup
    else
      zipname=$zipdir.zip
      instname=WezTerm-${TAG_NAME}-setup
    fi
    rm -rf $zipdir $zipname
    mkdir $zipdir
    cp $TARGET_DIR/release/cx-terminal.exe \
      $TARGET_DIR/release/cx-mux-server.exe \
      $TARGET_DIR/release/cx-terminal-gui.exe \
      $TARGET_DIR/release/strip-ansi-escapes.exe \
      $TARGET_DIR/release/cx-terminal.pdb \
      assets/windows/conhost/conpty.dll \
      assets/windows/conhost/OpenConsole.exe \
      assets/windows/angle/libEGL.dll \
      assets/windows/angle/libGLESv2.dll \
      $zipdir
    mkdir $zipdir/mesa
    cp $TARGET_DIR/release/mesa/opengl32.dll \
        $zipdir/mesa
    7z a -tzip $zipname $zipdir
    iscc.exe -DMyAppVersion=${TAG_NAME#nightly} -F${instname} ci/windows-installer.iss
    ;;
  linux-gnu|linux)
    distro=$(lsb_release -is 2>/dev/null || sh -c "source /etc/os-release && echo \$NAME")
    distver=$(lsb_release -rs 2>/dev/null || sh -c "source /etc/os-release && echo \$VERSION_ID")
    case "$distro" in
      *Fedora*|*CentOS*|*SUSE*)
        WEZTERM_RPM_VERSION=$(echo ${TAG_NAME#nightly-} | tr - _)
        distroid=$(sh -c "source /etc/os-release && echo \$ID" | tr - _)
        distver=$(sh -c "source /etc/os-release && echo \$VERSION_ID" | tr - _)

        SPEC_RELEASE="1.${distroid}${distver}"
        if test -n "${COPR_SRPM}" ; then
          SPEC_RELEASE=0
        fi

        # Set up variables for spec generation
        if test -n "${COPR_SRPM}" ; then
          TAR_NAME=$(git -c "core.abbrev=8" show -s "--format=%cd_%h" "--date=format:%Y%m%d_%H%M%S")
          HERE="."
          BUILD_SECTION=$(cat <<'BUILDEOFEOF'
%prep
%autosetup
%build

echo Here I am

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source ~/.cargo/env

cargo build --release \
      -p cx-terminal-gui -p cx-terminal -p cx-mux-server \
      -p strip-ansi-escapes
BUILDEOFEOF
)
          BUILD_REQUIRES=$(cat <<BREQEOF
BuildRequires: gcc, gcc-c++, make, curl, fontconfig-devel, openssl-devel, libxcb-devel, libxkbcommon-devel, libxkbcommon-x11-devel, wayland-devel, xcb-util-devel, xcb-util-keysyms-devel, xcb-util-image-devel, xcb-util-wm-devel, git
%if 0%{?suse_version}
BuildRequires: Mesa-libEGL-devel
%else
BuildRequires: mesa-libEGL-devel
%endif
%if 0%{?fedora} >= 41
BuildRequires: openssl-devel-engine
%endif
Source0: cx-terminal-${TAR_NAME}.tar.gz
BREQEOF
)
        else
          HERE="${HERE}"
          BUILD_SECTION=$(cat <<'BUILDEOFEOF'
%build
echo build
BUILDEOFEOF
)
          BUILD_REQUIRES=""
        fi

        # Generate single spec with subpackages
        cat > cx-terminal.spec <<EOF
Name: cx-terminal
Version: ${WEZTERM_RPM_VERSION}
Release: ${SPEC_RELEASE}
Packager: Wez Furlong <wez@wezfurlong.org>
License: MIT
URL: https://cxlinux.ai/
Summary: Wez's Terminal Emulator.
${BUILD_REQUIRES}
Requires: cx-terminal-common, cx-terminal-gui, cx-mux-server

%global debug_package %{nil}

%description
CX Terminal is a terminal emulator with support for modern features
such as fonts with ligatures, hyperlinks, tabs and multiple
windows.

# Subpackage: cx-terminal-common
%package -n cx-terminal-common
Summary: Wez's Terminal Emulator - Common CLI components
Requires: openssl
%description -n cx-terminal-common
cx-terminal-common provides the base CLI launcher and utilities shared by
all CX Terminal components.

# Subpackage: cx-terminal-gui
%package -n cx-terminal-gui
Summary: Wez's Terminal Emulator - GUI and multiplexer
Requires: cx-terminal-common
%if 0%{?suse_version}
Requires: dbus-1, fontconfig, libxcb1, libxkbcommon0, libxkbcommon-x11-0, libwayland-client0, libwayland-egl1, libwayland-cursor0, Mesa-libEGL1, libxcb-keysyms1, libxcb-ewmh2, libxcb-icccm4
%else
Requires: dbus, fontconfig, libxcb, libxkbcommon, libxkbcommon-x11, libwayland-client, libwayland-egl, libwayland-cursor, mesa-libEGL, xcb-util-keysyms, xcb-util-wm
%endif
%description -n cx-terminal-gui
cx-terminal-gui is a GPU-accelerated cross-platform terminal emulator with
support for modern features such as fonts with ligatures, hyperlinks,
tabs and multiple windows.

# Subpackage: cx-mux-server
%package -n cx-mux-server
Summary: Wez's Terminal Emulator - Multiplexer server (headless)
Requires: openssl
%description -n cx-mux-server
cx-mux-server is a headless terminal multiplexer that can be used
as a session manager for terminal sessions, without requiring X11,
Wayland, or other GUI libraries.

${BUILD_SECTION}

%install
set -x
cd ${HERE}
mkdir -p %{buildroot}/usr/bin %{buildroot}/etc/profile.d %{buildroot}/usr/share/icons/hicolor/128x128/apps %{buildroot}/usr/share/applications %{buildroot}/usr/share/metainfo %{buildroot}/usr/share/nautilus-python/extensions
install -Dm755 assets/open-cx-terminal-here -t %{buildroot}/usr/bin
install -Dsm755 $TARGET_DIR/release/cx-terminal -t %{buildroot}/usr/bin
install -Dsm755 $TARGET_DIR/release/cx-terminal-gui -t %{buildroot}/usr/bin
install -Dsm755 $TARGET_DIR/release/cx-mux-server -t %{buildroot}/usr/bin
install -Dsm755 $TARGET_DIR/release/strip-ansi-escapes -t %{buildroot}/usr/bin
install -Dm644 assets/shell-integration/* -t %{buildroot}/etc/profile.d
install -Dm644 assets/shell-completion/zsh %{buildroot}/usr/share/zsh/site-functions/_cx-terminal
install -Dm644 assets/shell-completion/bash %{buildroot}/etc/bash_completion.d/cx-terminal
install -Dm644 assets/icon/terminal.png %{buildroot}/usr/share/icons/hicolor/128x128/apps/org.cxlinux.cx-terminal.png
install -Dm644 assets/cx-terminal.desktop %{buildroot}/usr/share/applications/org.wezfurlong.cx-terminal.desktop
install -Dm644 assets/cx-terminal.appdata.xml %{buildroot}/usr/share/metainfo/org.wezfurlong.cx-terminal.appdata.xml
install -Dm644 assets/cx-terminal-nautilus.py %{buildroot}/usr/share/nautilus-python/extensions/cx-terminal-nautilus.py

%files
# Main package (metapackage) has no files

%files -n cx-terminal-common
/usr/bin/cx-terminal
/usr/bin/strip-ansi-escapes
/usr/share/zsh/site-functions/_cx-terminal
/etc/bash_completion.d/cx-terminal
/etc/profile.d/*

%files -n cx-terminal-gui
/usr/bin/open-cx-terminal-here
/usr/bin/cx-terminal-gui
/usr/share/icons/hicolor/128x128/apps/org.cxlinux.cx-terminal.png
/usr/share/applications/org.wezfurlong.cx-terminal.desktop
/usr/share/metainfo/org.wezfurlong.cx-terminal.appdata.xml
/usr/share/nautilus-python/extensions/cx-terminal-nautilus.py*

%files -n cx-mux-server
/usr/bin/cx-mux-server

%changelog
* Mon Oct 2 2023 Wez Furlong
- See git for full changelog
EOF

        if test -n "${COPR_SRPM}" ; then
          /usr/bin/rpmbuild -bs --rmspec cx-terminal.spec --verbose
          mv $(rpm --eval '%{_srcrpmdir}')/cx-terminal-${TAR_NAME}*.src.rpm "${COPR_SRPM}"/
        else
          /usr/bin/rpmbuild -bb --rmspec cx-terminal.spec --verbose
        fi

        ;;
      Ubuntu*|Debian*|Pop)
        rm -rf pkg
        mkdir -p pkg/debian/usr/bin pkg/debian/DEBIAN pkg/debian/usr/share/{applications,cx-terminal}

        if [[ "$BUILD_REASON" == "Schedule" ]] ; then
          pkgname=cx-terminal-nightly
          conflicts=cx-terminal
        else
          pkgname=cx-terminal
          conflicts=cx-terminal-nightly
        fi

        cat > pkg/debian/control <<EOF
Package: $pkgname
Version: ${TAG_NAME#nightly-}
Conflicts: $conflicts
Architecture: $(dpkg-architecture -q DEB_BUILD_ARCH_CPU)
Maintainer: Wez Furlong <wez@wezfurlong.org>
Section: utils
Priority: optional
Homepage: https://cxlinux.ai/
Description: Wez's Terminal Emulator.
 CX Terminal is a terminal emulator with support for modern features
 such as fonts with ligatures, hyperlinks, tabs and multiple
 windows.
Provides: x-terminal-emulator
Source: https://cxlinux.ai/
EOF

        cat > pkg/debian/postinst <<EOF
#!/bin/sh
set -e
if [ "\$1" = "configure" ] ; then
        update-alternatives --install /usr/bin/x-terminal-emulator x-terminal-emulator /usr/bin/open-cx-terminal-here 20
fi
EOF

        cat > pkg/debian/prerm <<EOF
#!/bin/sh
set -e
if [ "\$1" = "remove" ]; then
	update-alternatives --remove x-terminal-emulator /usr/bin/open-cx-terminal-here
fi
EOF

        install -Dsm755 -t pkg/debian/usr/bin $TARGET_DIR/release/cx-mux-server
        install -Dsm755 -t pkg/debian/usr/bin $TARGET_DIR/release/cx-terminal-gui
        install -Dsm755 -t pkg/debian/usr/bin $TARGET_DIR/release/cx-terminal
        install -Dm755 -t pkg/debian/usr/bin assets/open-cx-terminal-here
        install -Dsm755 -t pkg/debian/usr/bin $TARGET_DIR/release/strip-ansi-escapes

        deps=$(cd pkg && dpkg-shlibdeps -O -e debian/usr/bin/*)
        mv pkg/debian/postinst pkg/debian/DEBIAN/postinst
        chmod 0755 pkg/debian/DEBIAN/postinst
        mv pkg/debian/prerm pkg/debian/DEBIAN/prerm
        chmod 0755 pkg/debian/DEBIAN/prerm
        mv pkg/debian/control pkg/debian/DEBIAN/control
        sed -i '/^Source:/d' pkg/debian/DEBIAN/control  # The `Source:` field needs to be valid in a binary package
        echo $deps | sed -e 's/shlibs:Depends=/Depends: /' >> pkg/debian/DEBIAN/control
        cat pkg/debian/DEBIAN/control

        install -Dm644 assets/icon/terminal.png pkg/debian/usr/share/icons/hicolor/128x128/apps/org.cxlinux.cx-terminal.png
        install -Dm644 assets/cx-terminal.desktop pkg/debian/usr/share/applications/org.wezfurlong.cx-terminal.desktop
        install -Dm644 assets/cx-terminal.appdata.xml pkg/debian/usr/share/metainfo/org.wezfurlong.cx-terminal.appdata.xml
        install -Dm644 assets/cx-terminal-nautilus.py pkg/debian/usr/share/nautilus-python/extensions/cx-terminal-nautilus.py
        install -Dm644 assets/shell-completion/bash pkg/debian/usr/share/bash-completion/completions/cx-terminal
        install -Dm644 assets/shell-completion/zsh pkg/debian/usr/share/zsh/functions/Completion/Unix/_cx-terminal
        install -Dm644 assets/shell-integration/* -t pkg/debian/etc/profile.d

        if [[ "$BUILD_REASON" == "Schedule" ]] ; then
          debname=cx-terminal-nightly.$distro$distver
        else
          debname=cx-terminal-$TAG_NAME.$distro$distver
        fi
        arch=$(dpkg-architecture -q DEB_BUILD_ARCH_CPU)
        case $arch in
          amd64)
            ;;
          *)
            debname="${debname}.${arch}"
            ;;
        esac

        fakeroot dpkg-deb --build pkg/debian $debname.deb

        if [[ "$BUILD_REASON" != '' ]] ; then
          $SUDO apt-get install ./$debname.deb
        fi

        mv pkg/debian pkg/cx-terminal
        tar cJf $debname.tar.xz -C pkg cx-terminal
        rm -rf pkg
      ;;
    esac
    ;;
  linux-musl)
    case $ID in
      alpine)
        export SUDO=''
        abuild-keygen -a -n -b 8192
        pkgver="${TAG_NAME#nightly-}"
        cat > APKBUILD <<EOF
# Maintainer: Wez Furlong <wez@wezfurlong.org>
pkgname=cx-terminal
pkgver=$(echo "$pkgver" | cut -d'-' -f1-2 | tr - .)
_pkgver=$pkgver
pkgrel=0
pkgdesc="A GPU-accelerated cross-platform terminal emulator and multiplexer written in Rust"
license="MIT"
arch="all"
options="!check"
url="https://cxlinux.ai/"
makedepends="cmd:tic"
source="
  $TARGET_DIR/release/cx-terminal
  $TARGET_DIR/release/cx-terminal-gui
  $TARGET_DIR/release/cx-mux-server
  assets/open-cx-terminal-here
  assets/cx-terminal.desktop
  assets/cx-terminal.appdata.xml
  assets/icon/terminal.png
  assets/icon/cx-terminal-icon.svg
  termwiz/data/cx-terminal.terminfo
"
builddir="\$srcdir"

build() {
  tic -x -o "\$builddir"/cx-terminal.terminfo "\$srcdir"/cx-terminal.terminfo
}

package() {
  install -Dm755 -t "\$pkgdir"/usr/bin "\$srcdir"/open-cx-terminal-here
  install -Dm755 -t "\$pkgdir"/usr/bin "\$srcdir"/cx-terminal
  install -Dm755 -t "\$pkgdir"/usr/bin "\$srcdir"/cx-terminal-gui
  install -Dm755 -t "\$pkgdir"/usr/bin "\$srcdir"/cx-mux-server

  install -Dm644 -t "\$pkgdir"/usr/share/applications "\$srcdir"/cx-terminal.desktop
  install -Dm644 -t "\$pkgdir"/usr/share/metainfo "\$srcdir"/cx-terminal.appdata.xml
  install -Dm644 "\$srcdir"/terminal.png "\$pkgdir"/usr/share/pixmaps/cx-terminal.png
  install -Dm644 "\$srcdir"/cx-terminal-icon.svg "\$pkgdir"/usr/share/pixmaps/cx-terminal.svg
  install -Dm644 "\$srcdir"/terminal.png "\$pkgdir"/usr/share/icons/hicolor/128x128/apps/cx-terminal.png
  install -Dm644 "\$srcdir"/cx-terminal-icon.svg "\$pkgdir"/usr/share/icons/hicolor/scalable/apps/cx-terminal.svg
  install -Dm644 "\$builddir"/cx-terminal.terminfo "\$pkgdir"/usr/share/terminfo/c/cx-terminal
}
EOF
        abuild -F checksum
        abuild -Fr
      ;;
    esac
    ;;
  *)
    ;;
esac
