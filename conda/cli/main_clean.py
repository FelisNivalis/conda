# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function, unicode_literals

from logging import getLogger
from os import lstat, walk
from os.path import isdir, join
from typing import Any, Dict, Iterable, List, Tuple
import sys

from ..base.constants import CONDA_PACKAGE_EXTENSIONS, CONDA_TEMP_EXTENSIONS, CONDA_LOGS_DIR
from ..base.context import context

log = getLogger(__name__)
_EXTS = (*CONDA_PACKAGE_EXTENSIONS, *(f"{e}.part" for e in CONDA_PACKAGE_EXTENSIONS))


def _get_size(*parts: str, warnings: List[Tuple[str, Exception]]) -> int:
    path = join(*parts)
    try:
        stat = lstat(path)
    except OSError as e:
        if warnings is None:
            raise
        warnings.append((path, e))

    # TODO: This doesn't handle packages that have hard links to files within
    # themselves, like bin/python3.3 and bin/python3.3m in the Python package
    if stat.st_nlink > 1:
        raise NotImplementedError

    return stat.st_size


def _get_pkgs_dirs(pkg_sizes: Dict[str, Dict[str, int]]) -> Dict[str, Tuple[str]]:
    return {pkgs_dir: tuple(pkgs) for pkgs_dir, pkgs in pkg_sizes.items()}


def _get_total_size(pkg_sizes: Dict[str, Dict[str, int]]) -> int:
    return sum(sum(pkgs.values()) for pkgs in pkg_sizes.values())


def _rm_rf(*parts: str, verbose: bool, verbosity: bool) -> None:
    from ..gateways.disk.delete import rm_rf

    path = join(*parts)
    try:
        if rm_rf(path):
            if verbose and verbosity:
                print(f"Removed {path}")
        elif verbose:
            print(f"WARNING: cannot remove, file permissions: {path}")
    except (IOError, OSError) as e:
        if verbose:
            print(f"WARNING: cannot remove, file permissions: {path}\n{e!r}")
        else:
            log.info("%r", e)

def find_tarballs() -> Dict[str, Any]:
    warnings: List[Tuple[str, Exception]] = []
    pkg_sizes: Dict[str, Dict[str, int]] = {}
    for pkgs_dir in find_pkgs_dirs():
        # tarballs are files in pkgs_dir
        _, _, tars = next(walk(pkgs_dir))
        for tar in tars:
            # tarballs also end in .tar.bz2, .conda, .tar.bz2.part, or .conda.part
            if not tar.endswith(_EXTS):
                continue

            # get size
            try:
                size = _get_size(pkgs_dir, tar, warnings=warnings)
            except NotImplementedError:
                pass
            else:
                pkg_sizes.setdefault(pkgs_dir, {})[tar] = size

    return {
        "warnings": warnings,
        "pkg_sizes": pkg_sizes,
        "pkgs_dirs": _get_pkgs_dirs(pkg_sizes),
        "total_size": _get_total_size(pkg_sizes),
    }


def find_pkgs() -> Dict[str, Any]:
    warnings: List[Tuple[str, Exception]] = []
    pkg_sizes: Dict[str, Dict[str, int]] = {}
    for pkgs_dir in find_pkgs_dirs():
        # pkgs are directories in pkgs_dir
        _, pkgs, _ = next(walk(pkgs_dir))
        for pkg in pkgs:
            # pkgs also have an info directory
            if not isdir(join(pkgs_dir, pkg, "info")):
                continue

            # get size
            try:
                size = sum(
                    _get_size(root, file, warnings=warnings)
                    for root, _, files in walk(join(pkgs_dir, pkg))
                    for file in files
                )
            except NotImplementedError:
                pass
            else:
                pkg_sizes.setdefault(pkgs_dir, {})[pkg] = size

    return {
        "warnings": warnings,
        "pkg_sizes": pkg_sizes,
        "pkgs_dirs": _get_pkgs_dirs(pkg_sizes),
        "total_size": _get_total_size(pkg_sizes),
    }


def rm_pkgs(
    pkgs_dirs: Dict[str, Tuple[str]],
    warnings: List[Tuple[str, Exception]],
    total_size: int,
    pkg_sizes: Dict[str, Dict[str, int]],
    *,
    verbose: bool,
    verbosity: bool,
    dry_run: bool,
    name: str,
) -> None:
    from .common import confirm_yn
    from ..utils import human_bytes

    if verbose and warnings:
        for fn, exception in warnings:
            print(exception)

    if not any(pkgs for pkgs in pkg_sizes.values()):
        if verbose:
            print(f"There are no unused {name} to remove.")
        return

    if verbose:
        if verbosity:
            print(f"Will remove the following {name}:")
            for pkgs_dir, pkgs in pkg_sizes.items():
                print(f"  {pkgs_dir}")
                print(f"  {'-' * len(pkgs_dir)}")
                for pkg, size in pkgs.items():
                    print(f"  - {pkg:<40} {human_bytes(size):>10}")
                print()
            print("-" * 17)
            print(f"Total: {human_bytes(total_size):>10}")
            print()
        else:
            count = sum(len(pkgs) for pkgs in pkg_sizes.values())
            print(f"Will remove {count} ({human_bytes(total_size)}) {name}.")

    if dry_run:
        return
    if not context.json or not context.always_yes:
        confirm_yn()

    for pkgs_dir, pkgs in pkg_sizes.items():
        for pkg in pkgs:
            _rm_rf(pkgs_dir, pkg, verbose=verbose, verbosity=verbosity)


def find_index_cache() -> List[str]:
    files = []
    for pkgs_dir in find_pkgs_dirs():
        # caches are directories in pkgs_dir
        path = join(pkgs_dir, "cache")
        if isdir(path):
            files.append(path)
    return files


def find_pkgs_dirs() -> List[str]:
    from ..core.package_cache_data import PackageCacheData

    return [pc.pkgs_dir for pc in PackageCacheData.writable_caches() if isdir(pc.pkgs_dir)]


def find_tempfiles(paths: Iterable[str]) -> List[str]:
    tempfiles = []
    for path in sorted(set(paths or [sys.prefix])):
        # tempfiles are files in path
        for root, _, files in walk(path):
            for file in files:
                # tempfiles also end in .c~ or .trash
                if not file.endswith(CONDA_TEMP_EXTENSIONS):
                    continue

                tempfiles.append(join(root, file))

    return tempfiles


def find_logfiles() -> List[str]:
    files = []
    for pkgs_dir in find_pkgs_dirs():
        # .logs are directories in pkgs_dir
        path = join(pkgs_dir, CONDA_LOGS_DIR)
        if not isdir(path):
            continue

        # logfiles are files in .logs
        _, _, logs = next(walk(path), [None, None, []])
        files.extend([join(path, log) for log in logs])

    return files


def rm_items(
    items: List[str],
    *,
    verbose: bool,
    verbosity: bool,
    dry_run: bool,
    name: str,
) -> None:
    from .common import confirm_yn

    if not items:
        if verbose:
            print(f"There are no {name} to remove.")
        return

    if verbose:
        if verbosity:
            print(f"Will remove the following {name}:")
            for item in items:
                print(f"  - {item}")
            print()
        else:
            print(f"Will remove {len(items)} {name}.")

    if dry_run:
        return
    if not context.json or not context.always_yes:
        confirm_yn()

    for item in items:
        _rm_rf(item, verbose=verbose, verbosity=verbosity)


def _execute(args, parser):
    json_result = {"success": True}
    kwargs = {
        "verbose": not (context.json or context.quiet),
        "verbosity": args.verbosity,
        "dry_run": args.dry_run,
    }

    if args.force_pkgs_dirs:
        json_result["pkgs_dirs"] = pkgs_dirs = find_pkgs_dirs()
        rm_items(pkgs_dirs, **kwargs, name="package cache(s)")

        # we return here because all other clean operations target individual parts of
        # package caches
        return json_result

    if not (
        args.all
        or args.tarballs
        or args.index_cache
        or args.packages
        or args.tempfiles
        or args.logfiles
    ):
        from ..exceptions import ArgumentError

        raise ArgumentError("At least one removal target must be given. See 'conda clean --help'.")

    if args.tarballs or args.all:
        json_result["tarballs"] = tars = find_tarballs()
        rm_pkgs(**tars, **kwargs, name="tarball(s)")

    if args.index_cache or args.all:
        cache = find_index_cache()
        json_result["index_cache"] = {"files": cache}
        rm_items(cache, **kwargs, name="index cache(s)")

    if args.packages or args.all:
        json_result["packages"] = pkgs = find_pkgs()
        rm_pkgs(**pkgs, **kwargs, name="package(s)")

    if args.tempfiles or args.all:
        json_result["tempfiles"] = tmps = find_tempfiles(args.tempfiles)
        rm_items(tmps, **kwargs, name="tempfile(s)")

    if args.logfiles or args.all:
        json_result["logfiles"] = logs = find_logfiles()
        rm_items(logs, **kwargs, name="logfile(s)")

    return json_result


def execute(args, parser):
    from .common import stdout_json
    json_result = _execute(args, parser)
    if context.json:
        stdout_json(json_result)
    if args.dry_run:
        from ..exceptions import DryRunExit

        raise DryRunExit
