# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from argparse import RawDescriptionHelpFormatter
import os
import sys
import textwrap

from conda.base.context import context, determine_target_prefix
from conda.cli.conda_argparse import add_parser_json, add_parser_prefix, \
    add_parser_experimental_solver
from conda.core.prefix_data import PrefixData
from conda.exceptions import CondaEnvException, SpecNotFound
from conda.misc import touch_nonadmin
from conda.notices import notices

from .common import print_result, get_filename
from .. import specs as install_specs
from ..installers.base import InvalidInstaller, get_installer

description = """
Update the current environment based on environment file
"""

example = """
examples:
    conda env update
    conda env update -n=foo
    conda env update -f=/path/to/environment.yml
    conda env update --name=foo --file=environment.yml
    conda env update vader/deathstar
"""


def configure_parser(sub_parsers):
    p = sub_parsers.add_parser(
        'update',
        formatter_class=RawDescriptionHelpFormatter,
        description=description,
        help=description,
        epilog=example,
    )
    add_parser_prefix(p)
    p.add_argument(
        '-f', '--file',
        action='store',
        help='environment definition (default: environment.yml)',
        default='environment.yml',
    )
    p.add_argument(
        '--prune',
        action='store_true',
        default=False,
        help='remove installed packages not defined in environment.yml',
    )
    p.add_argument(
        'remote_definition',
        help='remote environment definition / IPython notebook',
        action='store',
        default=None,
        nargs='?'
    )
    add_parser_json(p)
    add_parser_experimental_solver(p)
    p.set_defaults(func='.main_update.execute')


@notices
def execute(args, parser):
    name = args.remote_definition or args.name

    try:
        spec = install_specs.detect(name=name, filename=get_filename(args.file),
                                    directory=os.getcwd())
        env = spec.environment
    except SpecNotFound:
        raise

    if not (args.name or args.prefix):
        if not env.name:
            # Note, this is a hack fofr get_prefix that assumes argparse results
            # TODO Refactor common.get_prefix
            name = os.environ.get('CONDA_DEFAULT_ENV', False)
            if not name:
                msg = "Unable to determine environment\n\n"
                msg += textwrap.dedent("""
                    Please re-run this command with one of the following options:

                    * Provide an environment name via --name or -n
                    * Re-run this command inside an activated conda environment.""").lstrip()
                # TODO Add json support
                raise CondaEnvException(msg)

        # Note: stubbing out the args object as all of the
        # conda.cli.common code thinks that name will always
        # be specified.
        args.name = env.name

    prefix = determine_target_prefix(context, args)
    # CAN'T Check with this function since it assumes we will create prefix.
    # cli_install.check_prefix(prefix, json=args.json)

    # TODO, add capability
    # common.ensure_override_channels_requires_channel(args)
    # channel_urls = args.channel or ()

    # create installers before running any of them
    # to avoid failure to import after the file being deleted
    # e.g. due to conda_env being upgraded or Python version switched.
    installers = {}

    for installer_type in env.dependencies:
        try:
            installers[installer_type] = get_installer(installer_type)
        except InvalidInstaller:
            sys.stderr.write(textwrap.dedent("""
                Unable to install package for {0}.

                Please double check and ensure you dependencies file has
                the correct spelling.  You might also try installing the
                conda-env-{0} package to see if provides the required
                installer.
                """).lstrip().format(installer_type)
            )
            return -1

    result = {"conda": None, "pip": None}
    for installer_type, specs in env.dependencies.items():
        installer = installers[installer_type]
        result[installer_type] = installer.install(prefix, specs, args, env)

    if env.variables:
        pd = PrefixData(prefix)
        pd.set_environment_env_vars(env.variables)

    touch_nonadmin(prefix)
    print_result(args, prefix, result)
