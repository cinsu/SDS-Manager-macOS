# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 J. Lynch. See LICENSE.
"""Sorting in Keys & Tags (v0.1.13): numbers as numbers, items without a number last either way."""
import unittest


class Header:
    def __init__(self, order):
        self.order = order

    def sortIndicatorOrder(self):
        return self.order


class Tree:
    def __init__(self, column, order):
        self.column, self._header = column, Header(order)

    def sortColumn(self):
        return self.column

    def header(self):
        return self._header


class Node:
    def __init__(self, tree, keys, text=''):
        self.tree, self.keys, self._text = tree, keys, text

    def treeWidget(self):
        return self.tree

    def data(self, column, _role):
        return self.keys.get(column)

    def text(self, _column):
        return self._text


class SortTests(unittest.TestCase):
    def test_sorting(self):
        import qt_stub
        with qt_stub.installed(forget=('keys_window',)):
            import keys_window as w
            items = [{'id': 0, 'name': 'Bravo', 'key': 10, 'tag': None, 'detail': ''},
                     {'id': 1, 'name': 'alpha', 'key': 2, 'tag': 5, 'detail': ''},
                     {'id': 2, 'name': 'Charlie', 'key': None, 'tag': 1, 'detail': ''}]

            def order(column, descending=False):
                tree = Tree(column, w.Qt.SortOrder.DescendingOrder if descending else w.Qt.SortOrder.AscendingOrder)
                nodes = [Node(tree, {c: w.sort_key(c, i, True) for c in range(6)}, i['name']) for i in items]
                for n, i in zip(nodes, items):
                    n.name = i['name']
                import functools
                ranked = sorted(nodes, key=functools.cmp_to_key(
                    lambda a, b: -1 if w.SortItem.__lt__(a, b) else (1 if w.SortItem.__lt__(b, a) else 0)))
                return [n.name for n in (reversed(ranked) if descending else ranked)]

            self.assertEqual(order(w.KEY), ['alpha', 'Bravo', 'Charlie'])          # 2 before 10; none last
            self.assertEqual(order(w.KEY, True), ['Bravo', 'alpha', 'Charlie'])    # none still last
            self.assertEqual(order(w.TAG), ['Charlie', 'alpha', 'Bravo'])
            self.assertEqual(order(w.NAME), ['alpha', 'Bravo', 'Charlie'])          # not case-sensitive
            self.assertEqual(order(w.ORDER), ['Bravo', 'alpha', 'Charlie'])         # back to scanner order
            self.assertEqual([label for label, _c, _o in w.SORTS][0], 'Scanner order')


if __name__ == '__main__':
    unittest.main()
