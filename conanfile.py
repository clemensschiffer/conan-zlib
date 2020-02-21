#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import stat
from conans import ConanFile, tools, CMake, AutoToolsBuildEnvironment
from conans.errors import ConanException


class ZlibConan(ConanFile):
    name = "zlib"
    version = "1.2.11"
    url = "http://github.com/conan-community/conan-zlib"
    homepage = "https://zlib.net"
    author = "Conan Community"
    license = "Zlib"
    description = ("A Massively Spiffy Yet Delicately Unobtrusive Compression Library "
                   "(Also Free, Not to Mention Unencumbered by Patents)")
    settings = "os", "arch", "compiler", "build_type"
    options = {"shared": [True, False], "fPIC": [True, False], "minizip": [True, False]}
    default_options = {'shared': False, 'fPIC': True, 'minizip': False}
    topics = ("conan", "zlib", "compression", "zip")
    exports = ["LICENSE"]
    exports_sources = ["CMakeLists.txt", "CMakeLists_minizip.txt", "minizip.patch"]
    generators = "cmake"
    _source_subfolder = "source_subfolder"
    _source_subfolder = "test_package"

    @property
    def _is_msvc(self):
        return self.settings.compiler == "Visual Studio"

    @property
    def _is_clangcl(self):
        return self.settings.compiler == "clang" and self.settings.os == "Windows"

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    def source(self):
        sha256 = "c3e5e9fdd5004dcb542feda5ee4f0ff0744628baf8ed2dd5d66f8ca1197cb1a1"
        try:
            tools.get("{}/{}-{}.tar.gz".format(self.homepage, self.name, self.version),
                      sha256=sha256)
        except ConanException:
            mirror = "https://downloads.sourceforge.net/project/libpng/zlib/{version}/zlib-{version}.tar.gz"
            tools.get(mirror.format(version=self.version), sha256=sha256)
        os.rename("{}-{}".format(self.name, self.version), self._source_subfolder)
        if not tools.os_info.is_windows:
            configure_file = os.path.join(self._source_subfolder, "configure")
            st = os.stat(configure_file)
            os.chmod(configure_file, st.st_mode | stat.S_IEXEC)
        tools.patch(patch_file="minizip.patch", base_path=self._source_subfolder)

    def build(self):
        self._build_zlib()
        if self.options.minizip:
            self._build_minizip()

    @property
    def _use_autotools(self):
        return self.settings.os == "Linux" or tools.is_apple_os(self.settings.os)

    def _build_zlib_autotools(self):
        env_build = AutoToolsBuildEnvironment(self)

        # configure passes CFLAGS to linker, should be LDFLAGS
        tools.replace_in_file("../configure", "$LDSHARED $SFLAGS", "$LDSHARED $LDFLAGS")
        # same thing in Makefile.in, when building tests/example executables
        tools.replace_in_file("../Makefile.in", "$(CC) $(CFLAGS) -o", "$(CC) $(LDFLAGS) -o")

        # we need to build only libraries without test example and minigzip
        if self.options.shared:
            make_target = "libz.%s.dylib" % self.version if tools.is_apple_os(self.settings.os) else "libz.so.%s" % self.version
        else:
            make_target = "libz.a"
        env_build.configure("../", build=False, host=False, target=False)
        env_build.make(target=make_target)

    def _build_zlib_cmake(self):
        cmake = CMake(self)
        cmake.configure(build_dir=".")
        # we need to build only libraries without test example/example64 and minigzip/minigzip64
        make_target = "zlib" if self.options.shared else "zlibstatic"
        cmake.build(build_dir=".", target=make_target)

    def _build_zlib(self):
        with tools.chdir(self._source_subfolder):
            # https://github.com/madler/zlib/issues/268
            tools.replace_in_file('gzguts.h',
                                  '#if defined(_WIN32) || defined(__CYGWIN__)',
                                  '#if defined(_WIN32) || defined(__MINGW32__)')
            if self.settings.os == "iOS":
                tools.replace_in_file("gzguts.h", '#ifdef _LARGEFILE64_SOURCE', '#include <unistd.h>\n\n#ifdef _LARGEFILE64_SOURCE')
            for filename in ['zconf.h', 'zconf.h.cmakein', 'zconf.h.in']:
                tools.replace_in_file(filename,
                                      '#ifdef HAVE_UNISTD_H    /* may be set to #if 1 by ./configure */',
                                      '#if defined(HAVE_UNISTD_H) && (1-HAVE_UNISTD_H-1 != 0)')
                tools.replace_in_file(filename,
                                      '#ifdef HAVE_STDARG_H    /* may be set to #if 1 by ./configure */',
                                      '#if defined(HAVE_STDARG_H) && (1-HAVE_STDARG_H-1 != 0)')
            tools.mkdir("_build")
            with tools.chdir("_build"):
                if self._use_autotools:
                    self._build_zlib_autotools()
                else:
                    self._build_zlib_cmake()

    def _build_minizip(self):
        minizip_dir = os.path.join(self._source_subfolder, 'contrib', 'minizip')
        os.rename("CMakeLists_minizip.txt", os.path.join(minizip_dir, 'CMakeLists.txt'))
        with tools.chdir(minizip_dir):
            cmake = CMake(self)
            cmake.configure(source_folder=minizip_dir)
            cmake.build()
            cmake.install()

    def _rename_libraries(self):
        if self.settings.os == "Windows":
            lib_path = os.path.join(self.package_folder, "lib")
            suffix = "d" if self.settings.build_type == "Debug" else ""

            if self.options.shared:
                if self._is_clangcl or self._is_msvc:
                    current_lib = os.path.join(lib_path, "zlib%s.lib" % suffix)
                    os.rename(current_lib, os.path.join(lib_path, "zlib.lib"))
            else:
                if self._is_clangcl or self._is_msvc:
                    current_lib = os.path.join(lib_path, "zlibstatic%s.lib" % suffix)
                    os.rename(current_lib, os.path.join(lib_path, "zlib.lib"))
                elif self.settings.compiler == "gcc":
                    current_lib = os.path.join(lib_path, "libzlibstatic.a")
                    os.rename(current_lib, os.path.join(lib_path, "libzlib.a"))

    def _delete_crypt_header(self):
        """
        Delete the crypt.h which is causing trouble for linking.
        The crypt.h defines only static methods which are to be included
        in zip.c/unzip.c so it will work just fine by  including zip.h/unzip.h
        and linking against libminizip
        cf: https://bugzilla.redhat.com/show_bug.cgi?id=1424609
        """
        crypt_path = os.path.join(self.package_folder, "include", "crypt.h")
        if os.path.exists(crypt_path):
            self.output.warn("Removing crypt.h at path: "
                             "{}".format(crypt_path))
            os.remove(crypt_path)
        else:
            self.output.warn("Didn't find crypt.h at path: "
                             "{}".format(crypt_path))

    def package(self):
        # Extract the License/s from the header to a file
        with tools.chdir(os.path.join(self.source_folder, self._source_subfolder)):
            tmp = tools.load("zlib.h")
            license_contents = tmp[2:tmp.find("*/", 1)]
            tools.save("LICENSE", license_contents)

        # Copy the license files
        self.copy("LICENSE", src=self._source_subfolder, dst="licenses")

        # Copy pc file
        self.copy("*.pc", dst="", keep_path=False)  # for compatibility only!
        self.copy("*.pc", dst=os.path.join("lib", "pkgconfig"), keep_path=False)

        # Copy headers
        for header in ["*zlib.h", "*zconf.h"]:
            self.copy(pattern=header, dst="include", src=self._source_subfolder, keep_path=False)
            self.copy(pattern=header, dst="include", src="_build", keep_path=False)

        # Copying static and dynamic libs
        build_dir = os.path.join(self._source_subfolder, "_build")
        if self.options.shared:
            self.copy(pattern="*.dylib*", dst="lib", src=build_dir, keep_path=False, symlinks=True)
            self.copy(pattern="*.so*", dst="lib", src=build_dir, keep_path=False, symlinks=True)
            self.copy(pattern="*.dll", dst="bin", src=build_dir, keep_path=False)
            self.copy(pattern="*.dll.a", dst="lib", src=build_dir, keep_path=False)
        else:
            self.copy(pattern="*.a", dst="lib", src=build_dir, keep_path=False)
        self.copy(pattern="*.lib", dst="lib", src=build_dir, keep_path=False)

        self._rename_libraries()
        self._delete_crypt_header()

    def package_info(self):
        if self.options.minizip:
            self.cpp_info.libs.append('minizip')
            if self.options.shared:
                self.cpp_info.defines.append('MINIZIP_DLL')
        self.cpp_info.libs.append('zlib' if self.settings.os == "Windows" else "z")
