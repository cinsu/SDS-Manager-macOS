# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Static regression for the Qt/Wayland preview lifecycle; GUI must be tested on Kubuntu."""
import ast
import unittest
from pathlib import Path

class PreviewQtLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parent / 'database_favorites_manager.py').read_text()
        tree = ast.parse(cls.source)
        window = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ManagerWindow')
        cls.methods = {node.name: ast.get_source_segment(cls.source, node) for node in window.body if isinstance(node, ast.FunctionDef)}

    def test_visible_nonmodal_progress_window(self):
        self.assertIn('class ExportPreviewBusyDialog(QDialog):', self.source)
        dialog_class = self.source.split('class ExportPreviewBusyDialog(QDialog):', 1)[1].split('class ScannerImportWorker', 1)[0]
        self.assertIn('Qt.WindowModality.NonModal', dialog_class)
        self.assertIn('progress.setRange(0, 0)', dialog_class)
        self.assertIn('self._ticker.start(1000)', dialog_class)
        self.assertIn('self.hide()', dialog_class)
        self.assertIn('self.deleteLater()', dialog_class)
        self.assertNotIn('self.exec()', dialog_class)
        preview = self.methods['preview_scanner_export']
        self.assertIn('ExportPreviewBusyDialog(self, export_flow=export_flow)', preview)
        self.assertIn('self._export_preview_busy_dialog.show()', preview)

    def test_busy_window_removed_after_worker_joins(self):
        cleanup = self.methods['_export_preview_cleanup']
        self.assertLess(cleanup.index('thread.wait(2000)'), cleanup.index('busy.finish()'))
        self.assertLess(cleanup.index('busy.finish()'), cleanup.index('QTimer.singleShot(300,'))

    def test_no_modal_progress_dialog(self):
        body = self.methods['preview_scanner_export']
        self.assertNotIn('QProgressDialog(', body)
        self.assertIn('statusBar().showMessage(', body)
        self.assertIn('self._export_preview_worker.finished.connect(self._export_preview_worker.deleteLater)', body)
        self.assertIn('self._export_preview_thread.finished.connect(self._export_preview_cleanup)', body)

    def test_wait_for_thread_before_report(self):
        body = self.methods['_export_preview_cleanup']
        self.assertIn('thread.wait(2000)', body)
        self.assertIn('thread.deleteLater()', body)
        self.assertIn('QTimer.singleShot(300,', body)
        self.assertLess(body.index('thread.wait(2000)'), body.index('thread.deleteLater()'))

    def test_report_is_nonmodal(self):
        body = self.methods['_export_preview_show_result']
        self.assertIn('Qt.WindowModality.NonModal', body)
        self.assertIn('dialog.show()', body)
        self.assertNotIn('dialog.exec()', body.replace('dialog.exec() while', ''))

if __name__ == '__main__': unittest.main()
