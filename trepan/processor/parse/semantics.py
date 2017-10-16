#  Copyright (c) 2017 by Rocky Bernstein
from __future__ import print_function

from trepan.processor.parse.parser import (
    parse_bp_location, parse_range
    )
from trepan.processor.parse.parser import LocationError as PLocationError
from trepan.processor.parse.scanner import ScannerError
from spark_parser import GenericASTTraversal # , DEFAULT_DEBUG as PARSER_DEFAULT_DEBUG

from collections import namedtuple
Location = namedtuple("Location", "path line_number method")
BPLocation = namedtuple("BPLocation", "location condition")
ListRange = namedtuple("ListRange", "first last")


class LocationError(Exception):
    def __init__(self, errmsg):
        self.errmsg = errmsg

    def __str__(self):
        return self.errmsg

class RangeError(Exception):
    def __init__(self, errmsg):
        self.errmsg = errmsg

    def __str__(self):
        return self.errmsg

class LocationGrok(GenericASTTraversal, object):

    def __init__(self, text):
        GenericASTTraversal.__init__(self, None)
        self.text = text
        self.result = None
        return

    def n_location(self, node):
        path, line_number, method = None, None, None
        if node[0] == 'FILENAME':
            path = node[0].value
            # If there is a line number, it is the last token of a location
            if len(node) > 1 and node[-1] == 'NUMBER':
                line_number = node[-1].value
        elif node[0] == 'FUNCNAME':
            method = node[0].value[:-2]
        elif node[0] == 'NUMBER':
            line_number = node[0].value
        else:
            assert True, "n_location: Something's is wrong; node[0] is %s" % node[0]
        self.result = Location(path, line_number, method)
        node.location = Location(path, line_number, method)
        self.prune()

    def n_NUMBER(self, node):
        self.result = Location(None, node.value, None)

    def n_FUNCNAME(self, node):
        self.result = Location(None, None, node.value[:-2])

    def n_location_if(self, node):
        location = None
        if node[0] == 'location':
            self.preorder(node[0])
            location = node[0].location

        if len(node) == 1:
            return
        if node[1] == 'IF':
            if_node = node[1]
        elif node[2] == 'IF':
            if_node = node[2]
        elif node[3] == 'IF':
            if_node = node[3]
        else:
            assert False, 'location_if: Something is wrong; cannot find "if"'

        condition = self.text[if_node.offset:]

        # Pick out condition from string and location inside "IF" token
        self.result = BPLocation(location, condition)
        self.prune()

    def n_range(self, range_node):
        # FIXME: start here
        l = len(range_node)
        if 1 <= l <= 2:
            # range ::= location
            # range ::= DIRECTION
            # range ::= FUNCNAME
            # range ::= NUMBER
            # range ::= OFFSET
            last_node = range_node[-1]
            if last_node == 'location':
                self.preorder(range_node[-1])
                self.result = ListRange(last_node.location, None)
            elif last_node == 'FUNCNAME':
                self.result = ListRange(Location(None, None, last_node.value[:-2]), None)
            elif last_node in ('NUMBER', 'OFFSET'):
                self.result = ListRange(Location(None, last_node.value, None), None)
            else:
                assert last_node == 'DIRECTION'
                self.result = ListRange(None, last_node.value)
                pass
            self.prune()
        elif l == 3:
            # range ::= COMMA opt_space location
            # range ::= location opt_space COMMA
            if range_node[0] == 'COMMA':
                assert range_node[-1] == 'location'
                self.preorder(range_node[-1])
                self.result = ListRange(None, self.result)
                self.prune()
            else:
                assert range_node[-1] == 'COMMA'
                assert range_node[0] == 'location'
                self.preorder(range_node[0])
                self.result = ListRange(range_node[0].location, None)
                self.prune()
                pass
        elif l == 5:
            # range ::= location opt_space COMMA opt_space NUMBER
            assert range_node[2] == 'COMMA'
            assert range_node[-1] in ('NUMBER', 'OFFSET')
            self.preorder(range_node[0])
            self.result = ListRange(range_node[0].location, range_node[-1].value)
            self.prune()
        else:
            raise RangeError("Something is wrong")
        return

    def default(self, node):
        if node not in frozenset(("""opt_space tokens token bp_start range_start
                                  IF FILENAME COLON COMMA SPACE DIRECTION""".split())):
            assert False, ("Something's wrong: you missed a rule for %s" % node.kind)

    def traverse(self, node, ):
        return self.preorder(node)


def build_bp_expr(string, show_tokens=False, show_ast=False, show_grammar=False):
    parser_debug = {'rules': False, 'transition': False,
                    'reduce': show_grammar,
                    'errorstack': None,
                    # 'context': True, 'dups': True
                        }
    parsed = parse_bp_location(string, show_tokens=show_tokens,
                               parser_debug=parser_debug)
    assert parsed == 'bp_start'
    if show_ast:
        print(parsed)
    walker = LocationGrok(string)
    walker.traverse(parsed)
    bp_expr = walker.result
    if isinstance(bp_expr, Location):
        bp_expr = BPLocation(bp_expr, None)
    location = bp_expr.location
    assert location.line_number is not None or location.method
    return bp_expr

def build_range(string, show_tokens=False, show_ast=False, show_grammar=False):
    parser_debug = {'rules': False, 'transition': False,
                    'reduce': show_grammar,
                    'errorstack': None,
                    'context': True, 'dups': True
                        }
    parsed = parse_range(string, show_tokens=show_tokens,
                               parser_debug=parser_debug)
    if show_ast:
        print(parsed)
    assert parsed == 'range_start'
    walker = LocationGrok(string)
    walker.traverse(parsed)
    list_range = walker.result
    return list_range

if __name__ == '__main__':
    # lines = """
    # /tmp/foo.py:12
    # /tmp/foo.py line 12
    # 12
    # ../foo.py:5
    # gcd()
    # foo.py line 5 if x > 1
    # """.splitlines()
    # for line in lines:
    #     if not line.strip():
    #         continue
    #     print("=" * 30)
    #     print(line)
    #     print("+" * 30)
    #     bp_expr = build_bp_expr(line)
    #     print(bp_expr)
    lines = """
    /tmp/foo.py:12 , 5
    -
    +
    ../foo.py:5
    ../foo.py:5 ,
    , 5
    6 , +2
    , /foo.py:5
    """.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        print("=" * 30)
        print(line)
        print("+" * 30)
        try:
            list_range = build_range(line)
        except ScannerError as e:
            print("Scanner error")
            print(e.text)
            print(e.text_cursor)
        except PLocationError as e:
            print("Parser error at or near")
            print(e.text)
            print(e.text_cursor)
        print(list_range)