# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import

import tempfile
from os.path import basename

from conda._vendor.boltons.setutils import IndexedSet
from conda.base.constants import UpdateModifier
from conda.base.context import context
from conda.common.constants import NULL
from conda.core.solve import _get_solver_class
from conda.exceptions import UnsatisfiableError
from conda.models.channel import Channel, prioritize_channels

from ..env import Environment

def _solve(prefix, specs, args, env, *_, **kwargs):
    # TODO: support all various ways this happens
    # Including 'nodefaults' in the channels list disables the defaults
    channel_urls = [chan for chan in env.channels if chan != 'nodefaults']

    if 'nodefaults' not in env.channels:
        channel_urls.extend(context.channels)
    _channel_priority_map = prioritize_channels(channel_urls)

    channels = IndexedSet(Channel(url) for url in _channel_priority_map)
    subdirs = IndexedSet(basename(url) for url in _channel_priority_map)

    solver = _get_solver_class()(prefix, channels, subdirs, specs_to_add=specs)
    return solver


def dry_run(specs, args, env, *_, **kwargs):
    solver = _solve(tempfile.mkdtemp(), specs, args, env, *_, **kwargs)
    pkgs = solver.solve_final_state()
    solved_env = Environment(
        name=env.name,
        dependencies=[str(p) for p in pkgs],
        channels=env.channels
    )
    return solved_env


def install(prefix, specs, args, env, *_, **kwargs):
    solver = _solve(prefix, specs, args, env, *_, **kwargs)

    try:
        unlink_link_transaction = solver.solve_for_transaction(
            prune=getattr(args, 'prune', False), update_modifier=UpdateModifier.FREEZE_INSTALLED)
    except (UnsatisfiableError, SystemExit):
        unlink_link_transaction = solver.solve_for_transaction(
            prune=getattr(args, 'prune', False), update_modifier=NULL)

    if unlink_link_transaction.nothing_to_do:
        return None
    unlink_link_transaction.download_and_extract()
    unlink_link_transaction.execute()
    return unlink_link_transaction._make_legacy_action_groups()[0]
