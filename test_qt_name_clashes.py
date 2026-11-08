# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Windows must not accidentally reuse the names of Qt's own methods.

v0.0.9a's firmware window defined done(result, error). QDialog.reject() (the Close button and the
window's ×) calls done(), so the window could never close. The Qt stub used by the other tests can't
see this, so this test reads the source: in every class based on a Qt window class, a method or a
self.<attribute> may not use one of these names unless it's listed as an intended override.
"""
import ast
import unittest
from pathlib import Path

QT_BASES = {'QDialog', 'QWidget', 'QMainWindow', 'QMessageBox', 'QDockWidget', 'QFrame', 'QGroupBox'}
QT_NAMES = {
    'done', 'accept', 'reject', 'exec', 'open', 'result', 'setResult', 'window', 'parent', 'parentWidget',
    'show', 'hide', 'close', 'update', 'repaint', 'layout', 'size', 'width', 'height', 'move', 'resize',
    'pos', 'rect', 'geometry', 'font', 'palette', 'style', 'children', 'event', 'isVisible', 'setVisible',
    'windowTitle', 'setWindowTitle', 'focusWidget', 'actions', 'title', 'menuBar', 'statusBar',
    'setLayout', 'deleteLater', 'objectName', 'setParent', 'raise_', 'activateWindow', 'adjustSize',
    'sizeHint', 'minimumSize', 'maximumSize', 'setEnabled', 'isEnabled', 'setFocus', 'clear', 'text',
}
# Overrides that are meant (same signature as Qt's): {(class, name)}
INTENDED = {('ExportPreviewBusyDialog', 'reject'),   # keeps Escape from hiding progress mid-task
            ('UpdateDialog', 'reject')}              # never closes while apt-get is installing


def clashes(path):
    found = []
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id if isinstance(b, ast.Name) else getattr(b, 'attr', '') for b in node.bases}
        if not bases & QT_BASES:
            continue
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in QT_NAMES:
                if (node.name, item.name) not in INTENDED:
                    found.append(f'{path.name}: {node.name}.{item.name}() hides Qt\'s {item.name}()')
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Store)
                    and isinstance(sub.value, ast.Name) and sub.value.id == 'self' and sub.attr in QT_NAMES
                    and (node.name, sub.attr) not in INTENDED):
                found.append(f'{path.name}: {node.name} assigns self.{sub.attr}, hiding Qt\'s {sub.attr}()')
    return found


class QtNameClashTests(unittest.TestCase):
    def test_no_window_class_hides_a_qt_method(self):
        here = Path(__file__).parent
        problems = []
        for path in sorted(here.glob('*.py')):
            if path.name.startswith('test_') or path.name == 'qt_stub.py':
                continue
            problems += clashes(path)
        self.assertEqual(problems, [], '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
