# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""A stand-in for PyQt6 so GUI *logic* can be exercised in an environment without Qt.

It proves that the code runs (no misspelt names, wrong arguments, or broken control flow) against widgets that
accept anything.  It cannot show how anything looks or behaves on screen; that is tested by hand.
"""
import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock

PREFIX = 'PyQt6'


class _Meta(type):
    """Class-level lookups (QApplication.instance, QMessageBox.StandardButton.Yes, ...) give mocks."""

    def __getattr__(cls, name):
        if name.startswith('__') or name.startswith('_mock') or name.startswith('assert'):
            raise AttributeError(name)
        value = MagicMock(name=cls.__name__ + '.' + name)
        setattr(cls, name, value)
        return value


class StubWidget(MagicMock, metaclass=_Meta):
    """Instances accept any call; the class can also be used as a base class."""

    def __init__(self, *args, **kwargs):
        super().__init__()


class StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name[:1].islower() and name != 'pyqtSignal':
            raise AttributeError(name)
        value = MagicMock(name=name) if name in ('Qt', 'pyqtSignal', 'QT_VERSION_STR', 'PYQT_VERSION_STR') \
            else type(name, (StubWidget,), {})
        setattr(self, name, value)
        return value


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path, target=None):
        if fullname == PREFIX or fullname.startswith(PREFIX + '.'):
            return importlib.machinery.ModuleSpec(fullname, self, is_package=(fullname == PREFIX))

    def create_module(self, spec):
        module = StubModule(spec.name)
        if spec.name == PREFIX:
            module.__path__ = []
        return module

    def exec_module(self, module):
        pass


class installed:
    """Context manager: PyQt6 imports resolve to stubs; everything imported meanwhile is forgotten on exit."""

    def __init__(self, forget=()):
        self.forget = tuple(forget)

    def __enter__(self):
        self._saved = {k: v for k, v in sys.modules.items() if k == PREFIX or k.startswith(PREFIX + '.')}
        for key in self._saved:
            del sys.modules[key]
        self._finder = _Finder()
        sys.meta_path.insert(0, self._finder)
        return self

    def __exit__(self, *exc):
        sys.meta_path.remove(self._finder)
        for key in [k for k in sys.modules if k == PREFIX or k.startswith(PREFIX + '.')]:
            del sys.modules[key]
        for key in self.forget:
            sys.modules.pop(key, None)
        sys.modules.update(self._saved)
