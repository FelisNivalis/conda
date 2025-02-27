# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import OrderedDict
from functools import lru_cache
from genericpath import exists
from logging import getLogger
from os import scandir
import sys


log = getLogger(__name__)


@lru_cache(maxsize=None)
def linux_get_libc_version():
    """
    If on linux, returns (libc_family, version), otherwise (None, None).
    """

    if not sys.platform.startswith('linux'):
        return None, None

    from os import confstr, confstr_names, readlink

    # Python 2.7 does not have either of these keys in confstr_names, so provide
    # hard-coded defaults and assert if the key is in confstr_names but differs.
    # These are defined by POSIX anyway so should never change.
    confstr_names_fallback = OrderedDict([('CS_GNU_LIBC_VERSION', 2),
                                          ('CS_GNU_LIBPTHREAD_VERSION', 3)])

    val = None
    for k, v in confstr_names_fallback.items():
        assert k not in confstr_names or confstr_names[k] == v, (
            "confstr_names_fallback for %s is %s yet in confstr_names it is %s"
            "" % (k, confstr_names_fallback[k], confstr_names[k])
        )
        try:
            val = str(confstr(v))
        except Exception:  # pragma: no cover
            pass
        else:
            if val:
                break

    if not val:  # pragma: no cover
        # Weird, play it safe and assume glibc 2.5
        family, version = 'glibc', '2.5'
        log.warning("Failed to detect libc family and version, assuming %s/%s", family, version)
        return family, version
    family, version = val.split(' ')

    # NPTL is just the name of the threading library, even though the
    # version refers to that of uClibc. readlink() can help to try to
    # figure out a better name instead.
    if family == 'NPTL':  # pragma: no cover
        for clib in (entry.path for entry in scandir("/lib") if entry.name[:7] == "libc.so"):
            clib = readlink(clib)
            if exists(clib):
                if clib.startswith('libuClibc'):
                    if version.startswith('0.'):
                        family = 'uClibc'
                    else:
                        family = 'uClibc-ng'
                    return family, version
        # This could be some other C library; it is unlikely though.
        family = 'uClibc'
        log.warning("Failed to detect non-glibc family, assuming %s (%s)", family, version)
        return family, version
    return family, version
