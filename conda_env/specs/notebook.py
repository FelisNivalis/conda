# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
try:
    import nbformat
except ImportError:
    nbformat = None
from ..env import Environment
from .binstar import BinstarSpec


class NotebookSpec(object):
    msg = None

    def __init__(self, name=None, **kwargs):
        self.name = name
        self.nb = {}

    def can_handle(self):
        result = self._can_handle()
        if result:
            print("WARNING: Notebook environments are deprecated and scheduled to be "
                  "removed in conda 4.5. See conda issue #5843 at "
                  "https://github.com/conda/conda/pull/5843 for more information.")
        return result

    def _can_handle(self):
        try:
            self.nb = nbformat.reader.reads(open(self.name).read())
            return 'environment' in self.nb['metadata']
        except AttributeError:
            self.msg = "Please install nbformat:\n\tconda install nbformat"
        except IOError:
            self.msg = "{} does not exist or can't be accessed".format(self.name)
        except (nbformat.reader.NotJSONError, KeyError):
            self.msg = "{} does not looks like a notebook file".format(self.name)
        except Exception:
            return False
        return False

    @property
    def environment(self):
        if 'remote' in self.nb['metadata']['environment']:
            spec = BinstarSpec('darth/deathstar')
            return spec.environment
        else:
            return Environment(**self.nb['metadata']['environment'])
