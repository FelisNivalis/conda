# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function, unicode_literals

from logging import getLogger

from .enums import LeasedPathType
from ..auxlib.entity import Entity, EnumField, StringField

log = getLogger(__name__)


class LeasedPathEntry(Entity):
    """
        _path: short path for the leased path, using forward slashes
        target_path: the full path to the executable in the private env
        target_prefix: the full path to the private environment
        leased_path: the full path for the lease in the root prefix
        package_name: the package holding the lease
        leased_path_type: application_entry_point

    """

    _path = StringField()
    target_path = StringField()
    target_prefix = StringField()
    leased_path = StringField()
    package_name = StringField()
    leased_path_type = EnumField(LeasedPathType)
