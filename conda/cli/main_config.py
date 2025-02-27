# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function, unicode_literals

from collections.abc import Mapping, Sequence
import json
from logging import getLogger
import os
from os.path import isfile, join
import sys
from textwrap import wrap

try:
    from tlz.itertoolz import concat, groupby
except ImportError:
    from conda._vendor.toolz.itertoolz import concat, groupby

from .. import CondaError
from ..auxlib.entity import EntityEncoder
from ..base.constants import (ChannelPriority, DepsModifier, PathConflict, SafetyChecks,
                              UpdateModifier, SatSolverChoice, ExperimentalSolverChoice)
from ..base.context import context, sys_rc_path, user_rc_path
from ..common.compat import isiterable
from ..common.configuration import pretty_list, pretty_map
from ..common.io import timeout
from ..common.serialize import yaml, yaml_round_trip_dump, yaml_round_trip_load


def execute(args, parser):
    from ..exceptions import CouldntParseError
    try:
        execute_config(args, parser)
    except (CouldntParseError, NotImplementedError) as e:
        raise CondaError(e)


def format_dict(d):
    lines = []
    for k, v in d.items():
        if isinstance(v, Mapping):
            if v:
                lines.append("%s:" % k)
                lines.append(pretty_map(v))
            else:
                lines.append("%s: {}" % k)
        elif isiterable(v):
            if v:
                lines.append("%s:" % k)
                lines.append(pretty_list(v))
            else:
                lines.append("%s: []" % k)
        else:
            lines.append("%s: %s" % (k, v if v is not None else "None"))
    return lines


def parameter_description_builder(name):
    builder = []
    details = context.describe_parameter(name)
    aliases = details['aliases']
    string_delimiter = details.get('string_delimiter')
    element_types = details['element_types']
    default_value_str = json.dumps(details['default_value'], cls=EntityEncoder)

    if details['parameter_type'] == 'primitive':
        builder.append("%s (%s)" % (name, ', '.join(sorted(set(et for et in element_types)))))
    else:
        builder.append("%s (%s: %s)" % (name, details['parameter_type'],
                                        ', '.join(sorted(set(et for et in element_types)))))

    if aliases:
        builder.append("  aliases: %s" % ', '.join(aliases))
    if string_delimiter:
        builder.append("  env var string delimiter: '%s'" % string_delimiter)

    builder.extend('  ' + line for line in wrap(details['description'], 70))

    builder.append('')
    builder = ['# ' + line for line in builder]

    builder.extend(yaml_round_trip_dump({name: json.loads(default_value_str)}).strip().split('\n'))

    builder = ['# ' + line for line in builder]
    builder.append('')
    return builder


def describe_all_parameters():
    builder = []
    skip_categories = ('CLI-only', 'Hidden and Undocumented')
    for category, parameter_names in context.category_map.items():
        if category in skip_categories:
            continue
        builder.append('# ######################################################')
        builder.append('# ## {:^48} ##'.format(category))
        builder.append('# ######################################################')
        builder.append('')
        builder.extend(concat(parameter_description_builder(name)
                              for name in parameter_names))
        builder.append('')
    return '\n'.join(builder)


def print_config_item(key, value):
    stdout_write = getLogger("conda.stdout").info
    if isinstance(value, (dict,)):
        for k, v in value.items():
            print_config_item(key + "." + k, v)
    elif isinstance(value, (bool, int, str)):
        stdout_write(" ".join(("--set", key, str(value))))
    elif isinstance(value, (list, tuple)):
        # Note, since `conda config --add` prepends, print `--add` commands in
        # reverse order (using repr), so that entering them in this order will
        # recreate the same file.
        numitems = len(value)
        for q, item in enumerate(reversed(value)):
            if key == "channels" and q in (0, numitems-1):
                stdout_write(" ".join((
                    "--add", key, repr(item),
                    "  # lowest priority" if q == 0 else "  # highest priority"
                )))
            else:
                stdout_write(" ".join(("--add", key, repr(item))))


def execute_config(args, parser):
    stdout_write = getLogger("conda.stdout").info
    stderr_write = getLogger("conda.stderr").info
    json_warnings = []
    json_get = {}

    if args.show_sources:
        if context.json:
            stdout_write(json.dumps(
                context.collect_all(), sort_keys=True, indent=2, separators=(',', ': '),
                cls=EntityEncoder
            ))
        else:
            lines = []
            for source, reprs in context.collect_all().items():
                lines.append("==> %s <==" % source)
                lines.extend(format_dict(reprs))
                lines.append('')
            stdout_write('\n'.join(lines))
        return

    if args.show is not None:
        if args.show:
            paramater_names = args.show
            all_names = context.list_parameters()
            not_params = set(paramater_names) - set(all_names)
            if not_params:
                from ..exceptions import ArgumentError
                from ..common.io import dashlist
                raise ArgumentError("Invalid configuration parameters: %s" % dashlist(not_params))
        else:
            paramater_names = context.list_parameters()

        d = {key: getattr(context, key) for key in paramater_names}
        if context.json:
            stdout_write(json.dumps(
                d, sort_keys=True, indent=2, separators=(',', ': '), cls=EntityEncoder
            ))
        else:
            # Add in custom formatting
            if 'custom_channels' in d:
                d['custom_channels'] = {
                    channel.name: "%s://%s" % (channel.scheme, channel.location)
                    for channel in d['custom_channels'].values()
                }
            if 'custom_multichannels' in d:
                from ..common.io import dashlist
                d['custom_multichannels'] = {
                    multichannel_name: dashlist(channels, indent=4)
                    for multichannel_name, channels in d['custom_multichannels'].items()
                }

            stdout_write('\n'.join(format_dict(d)))
        context.validate_configuration()
        return

    if args.describe is not None:
        if args.describe:
            paramater_names = args.describe
            all_names = context.list_parameters()
            not_params = set(paramater_names) - set(all_names)
            if not_params:
                from ..exceptions import ArgumentError
                from ..common.io import dashlist
                raise ArgumentError("Invalid configuration parameters: %s" % dashlist(not_params))
            if context.json:
                stdout_write(json.dumps(
                    [context.describe_parameter(name) for name in paramater_names],
                    sort_keys=True, indent=2, separators=(',', ': '), cls=EntityEncoder
                ))
            else:
                builder = []
                builder.extend(concat(parameter_description_builder(name)
                                      for name in paramater_names))
                stdout_write('\n'.join(builder))
        else:
            if context.json:
                skip_categories = ('CLI-only', 'Hidden and Undocumented')
                paramater_names = sorted(concat(
                    parameter_names for category, parameter_names in context.category_map.items()
                    if category not in skip_categories
                ))
                stdout_write(json.dumps(
                    [context.describe_parameter(name) for name in paramater_names],
                    sort_keys=True, indent=2, separators=(',', ': '), cls=EntityEncoder
                ))
            else:
                stdout_write(describe_all_parameters())
        return

    if args.validate:
        context.validate_all()
        return

    if args.system:
        rc_path = sys_rc_path
    elif args.env:
        if 'CONDA_PREFIX' in os.environ:
            rc_path = join(os.environ['CONDA_PREFIX'], '.condarc')
        else:
            rc_path = user_rc_path
    elif args.file:
        rc_path = args.file
    else:
        rc_path = user_rc_path

    if args.write_default:
        if isfile(rc_path):
            with open(rc_path) as fh:
                data = fh.read().strip()
            if data:
                raise CondaError("The file '%s' "
                                 "already contains configuration information.\n"
                                 "Remove the file to proceed.\n"
                                 "Use `conda config --describe` to display default configuration."
                                 % rc_path)

        with open(rc_path, 'w') as fh:
            fh.write(describe_all_parameters())
        return

    # read existing condarc
    if os.path.exists(rc_path):
        with open(rc_path, 'r') as fh:
            # round trip load required because... we need to round trip
            rc_config = yaml_round_trip_load(fh) or {}
    elif os.path.exists(sys_rc_path):
        # In case the considered rc file doesn't exist, fall back to the system rc
        with open(sys_rc_path, 'r') as fh:
            rc_config = yaml_round_trip_load(fh) or {}
    else:
        rc_config = {}

    grouped_paramaters = groupby(lambda p: context.describe_parameter(p)['parameter_type'],
                                 context.list_parameters())
    primitive_parameters = grouped_paramaters['primitive']
    sequence_parameters = grouped_paramaters['sequence']
    map_parameters = grouped_paramaters['map']
    all_parameters = primitive_parameters + sequence_parameters + map_parameters

    # Get
    if args.get is not None:
        context.validate_all()
        if args.get == []:
            args.get = sorted(rc_config.keys())

        value_not_found = object()
        for key in args.get:
            key_parts = key.split(".")

            if key_parts[0] not in all_parameters:
                message = "unknown key %s" % key_parts[0]
                if not context.json:
                    stderr_write(message)
                else:
                    json_warnings.append(message)
                continue

            remaining_rc_config = rc_config
            for k in key_parts:
                if k in remaining_rc_config:
                    remaining_rc_config = remaining_rc_config[k]
                else:
                    remaining_rc_config = value_not_found
                    break

            if remaining_rc_config is value_not_found:
                pass
            elif context.json:
                json_get[key] = remaining_rc_config
            else:
                print_config_item(key, remaining_rc_config)

    if args.stdin:
        content = timeout(5, sys.stdin.read)
        if not content:
            return
        try:
            # round trip load required because... we need to round trip
            parsed = yaml_round_trip_load(content)
            rc_config.update(parsed)
        except Exception:  # pragma: no cover
            from ..exceptions import ParseError
            raise ParseError("invalid yaml content:\n%s" % content)

    # prepend, append, add
    for arg, prepend in zip((args.prepend, args.append), (True, False)):
        for key, item in arg:
            key, subkey = key.split('.', 1) if '.' in key else (key, None)
            if key == 'channels' and key not in rc_config:
                rc_config[key] = ['defaults']
            if key in sequence_parameters:
                arglist = rc_config.setdefault(key, [])
            elif key in map_parameters:
                arglist = rc_config.setdefault(key, {}).setdefault(subkey, [])
            else:
                from ..exceptions import CondaValueError
                raise CondaValueError("Key '%s' is not a known sequence parameter." % key)
            if not (isinstance(arglist, Sequence) and not
                    isinstance(arglist, str)):
                from ..exceptions import CouldntParseError
                bad = rc_config[key].__class__.__name__
                raise CouldntParseError("key %r should be a list, not %s." % (key, bad))
            if item in arglist:
                message_key = key + "." + subkey if subkey is not None else key
                # Right now, all list keys should not contain duplicates
                message = "Warning: '%s' already in '%s' list, moving to the %s" % (
                    item, message_key, "top" if prepend else "bottom")
                if subkey is None:
                    arglist = rc_config[key] = [p for p in arglist if p != item]
                else:
                    arglist = rc_config[key][subkey] = [p for p in arglist if p != item]
                if not context.json:
                    stderr_write(message)
                else:
                    json_warnings.append(message)
            arglist.insert(0 if prepend else len(arglist), item)

    # Set
    for key, item in args.set:
        key, subkey = key.split('.', 1) if '.' in key else (key, None)
        if key in primitive_parameters:
            value = context.typify_parameter(key, item, "--set parameter")
            rc_config[key] = value
        elif key in map_parameters:
            argmap = rc_config.setdefault(key, {})
            argmap[subkey] = item
        else:
            from ..exceptions import CondaValueError
            raise CondaValueError("Key '%s' is not a known primitive parameter." % key)

    # Remove
    for key, item in args.remove:
        key, subkey = key.split('.', 1) if '.' in key else (key, None)
        if key not in rc_config:
            if key != 'channels':
                from ..exceptions import CondaKeyError
                raise CondaKeyError(key, "key %r is not in the config file" % key)
            rc_config[key] = ['defaults']
        if item not in rc_config[key]:
            from ..exceptions import CondaKeyError
            raise CondaKeyError(key, "%r is not in the %r key of the config file" %
                                (item, key))
        rc_config[key] = [i for i in rc_config[key] if i != item]

    # Remove Key
    for key, in args.remove_key:
        key, subkey = key.split('.', 1) if '.' in key else (key, None)
        if key not in rc_config:
            from ..exceptions import CondaKeyError
            raise CondaKeyError(key, "key %r is not in the config file" %
                                key)
        del rc_config[key]

    # config.rc_keys
    if not args.get:

        # Add representers for enums.
        # Because a representer cannot be added for the base Enum class (it must be added for
        # each specific Enum subclass - and because of import rules), I don't know of a better
        # location to do this.
        def enum_representer(dumper, data):
            return dumper.represent_str(str(data))

        yaml.representer.RoundTripRepresenter.add_representer(SafetyChecks, enum_representer)
        yaml.representer.RoundTripRepresenter.add_representer(PathConflict, enum_representer)
        yaml.representer.RoundTripRepresenter.add_representer(DepsModifier, enum_representer)
        yaml.representer.RoundTripRepresenter.add_representer(UpdateModifier, enum_representer)
        yaml.representer.RoundTripRepresenter.add_representer(ChannelPriority, enum_representer)
        yaml.representer.RoundTripRepresenter.add_representer(SatSolverChoice, enum_representer)
        yaml.representer.RoundTripRepresenter.add_representer(
            ExperimentalSolverChoice, enum_representer
        )

        try:
            with open(rc_path, 'w') as rc:
                rc.write(yaml_round_trip_dump(rc_config))
        except (IOError, OSError) as e:
            raise CondaError('Cannot write to condarc file at %s\n'
                             'Caused by %r' % (rc_path, e))

    if context.json:
        from .common import stdout_json_success
        stdout_json_success(
            rc_path=rc_path,
            warnings=json_warnings,
            get=json_get
        )
    return
