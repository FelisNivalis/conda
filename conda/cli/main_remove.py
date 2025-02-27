# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
from os.path import isfile, join
import sys

from .common import check_non_admin, specs_from_args
from .install import handle_txn
from ..base.context import context
from ..core.envs_manager import unregister_env
from ..core.link import PrefixSetup, UnlinkLinkTransaction
from ..core.prefix_data import PrefixData
from ..core.solve import _get_solver_class
from ..exceptions import CondaEnvironmentError, CondaValueError, DirectoryNotACondaEnvironmentError
from ..gateways.disk.delete import rm_rf, path_is_clean
from ..models.match_spec import MatchSpec
from ..exceptions import PackagesNotFoundError

log = logging.getLogger(__name__)


def execute(args, parser):

    if not (args.all or args.package_names):
        raise CondaValueError('no package names supplied,\n'
                              '       try "conda remove -h" for more details')

    prefix = context.target_prefix
    check_non_admin()

    if args.all and prefix == context.default_prefix:
        msg = "cannot remove current environment. deactivate and run conda remove again"
        raise CondaEnvironmentError(msg)

    if args.all and path_is_clean(prefix):
        # full environment removal was requested, but environment doesn't exist anyway

        # .. but you know what? If you call `conda remove --all` you'd expect the dir
        # not to exist afterwards, would you not? If not (fine, I can see the argument
        # about deleting people's work in envs being a very bad thing indeed), but if
        # being careful is the goal it would still be nice if after `conda remove --all`
        # to be able to do `conda create` on the same environment name.
        #
        # try:
        #     rm_rf(prefix, clean_empty_parents=True)
        # except:
        #     log.warning("Failed rm_rf() of partially existent env {}".format(prefix))

        return 0

    if args.all:
        if prefix == context.root_prefix:
            raise CondaEnvironmentError('cannot remove root environment,\n'
                                        '       add -n NAME or -p PREFIX option')
        if not isfile(join(prefix, 'conda-meta', 'history')):
            raise DirectoryNotACondaEnvironmentError(prefix)
        print("\nRemove all packages in environment %s:\n" % prefix, file=sys.stderr)

        if 'package_names' in args:
            stp = PrefixSetup(
                target_prefix=prefix,
                unlink_precs=tuple(PrefixData(prefix).iter_records()),
                link_precs=(),
                remove_specs=(),
                update_specs=(),
                neutered_specs={},
            )
            txn = UnlinkLinkTransaction(stp)
            try:
                handle_txn(txn, prefix, args, False, True)
            except PackagesNotFoundError:
                print("No packages found in %s. Continuing environment removal" % prefix)
        if not context.dry_run:
            rm_rf(prefix, clean_empty_parents=True)
            unregister_env(prefix)

        return

    else:
        if args.features:
            specs = tuple(MatchSpec(track_features=f) for f in set(args.package_names))
        else:
            specs = specs_from_args(args.package_names)
        channel_urls = ()
        subdirs = ()
        solver = _get_solver_class()(prefix, channel_urls, subdirs, specs_to_remove=specs)
        txn = solver.solve_for_transaction()
        handle_txn(txn, prefix, args, False, True)

    # Keep this code for dev reference until private envs can be re-enabled in
    # Solver.solve_for_transaction

    # specs = None
    # if args.features:
    #     specs = [MatchSpec(track_features=f) for f in set(args.package_names)]
    #     actions = remove_actions(prefix, specs, index, pinned=not context.ignore_pinned)
    #     actions['ACTION'] = 'REMOVE_FEATURE'
    #     action_groups = (actions, index),
    # elif args.all:
    #     if prefix == context.root_prefix:
    #         raise CondaEnvironmentError('cannot remove root environment,\n'
    #                                     '       add -n NAME or -p PREFIX option')
    #     actions = defaultdict(list)
    #     actions[PREFIX] = prefix
    #     for dist in sorted(iter(index.keys())):
    #         add_unlink(actions, dist)
    #     actions['ACTION'] = 'REMOVE_ALL'
    #     action_groups = (actions, index),
    # elif prefix == context.root_prefix and not context.prefix_specified:
    #     from ..core.envs_manager import EnvsDirectory
    #     ed = EnvsDirectory(join(context.root_prefix, 'envs'))
    #     get_env = lambda s: ed.get_registered_preferred_env(MatchSpec(s).name)
    #     specs = specs_from_args(args.package_names)
    #     env_spec_map = groupby(get_env, specs)
    #     action_groups = []
    #     for env_name, spcs in env_spec_map.items():
    #         pfx = ed.to_prefix(env_name)
    #         r = get_resolve_object(index.copy(), pfx)
    #         specs_to_remove = tuple(MatchSpec(s) for s in spcs)
    #         prune = pfx != context.root_prefix
    #         dists_for_unlinking, dists_for_linking = solve_for_actions(
    #             pfx, r,
    #             specs_to_remove=specs_to_remove, prune=prune,
    #         )
    #         actions = get_blank_actions(pfx)
    #         actions['UNLINK'].extend(dists_for_unlinking)
    #         actions['LINK'].extend(dists_for_linking)
    #         actions['SPECS'].extend(str(s) for s in specs_to_remove)
    #         actions['ACTION'] = 'REMOVE'
    #         action_groups.append((actions, r.index))
    #     action_groups = tuple(action_groups)
    # else:
    #     specs = specs_from_args(args.package_names)
    #     if sys.prefix == abspath(prefix) and names_in_specs(ROOT_NO_RM, specs) and not args.force:  # NOQA
    #         raise CondaEnvironmentError('cannot remove %s from root environment' %
    #                                     ', '.join(ROOT_NO_RM))
    #     action_groups = (remove_actions(prefix, list(specs), index=index,
    #                                     force=args.force,
    #                                     pinned=not context.ignore_pinned,
    #                                     ), index),
    #
    #
    # delete_trash()
    # if any(nothing_to_do(x[0]) for x in action_groups):
    #     if args.all:
    #         print("\nRemove all packages in environment %s:\n" % prefix, file=sys.stderr)
    #         if not context.json:
    #             confirm_yn(args)
    #         rm_rf(prefix)
    #
    #         if context.json:
    #             stdout_json({
    #                 'success': True,
    #                 'actions': tuple(x[0] for x in action_groups)
    #             })
    #         return
    #
    #     pkg = str(args.package_names).replace("['", "")
    #     pkg = pkg.replace("']", "")
    #
    #     error_message = "No packages named '%s' found to remove from environment." % pkg
    #     raise PackageNotFoundError(error_message)
    # if not context.json:
    #     for actions, ndx in action_groups:
    #         print()
    #         print("Package plan for package removal in environment %s:" % actions["PREFIX"])
    #         display_actions(actions, ndx)
    # elif context.json and args.dry_run:
    #     stdout_json({
    #         'success': True,
    #         'dry_run': True,
    #         'actions': tuple(x[0] for x in action_groups),
    #     })
    #     return
    #
    # if not context.json:
    #     confirm_yn(args)
    #
    # for actions, ndx in action_groups:
    #     if context.json and not context.quiet:
    #         with json_progress_bars():
    #             execute_actions(actions, ndx, verbose=not context.quiet)
    #     else:
    #         execute_actions(actions, ndx, verbose=not context.quiet)
    #
    #     target_prefix = actions["PREFIX"]
    #     if is_private_env_path(target_prefix) and linked_data(target_prefix) == {}:
    #         rm_rf(target_prefix)
    #
    # if args.all:
    #     rm_rf(prefix)
    #
    # if context.json:
    #     stdout_json({
    #         'success': True,
    #         'actions': tuple(x[0] for x in action_groups),
    #     })
