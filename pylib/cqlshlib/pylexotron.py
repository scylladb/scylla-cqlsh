# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pylexotron uses Python's re.Scanner module as a simple regex-based tokenizer for BNF production rules"""

import re
import inspect
import sys
from typing import Union

from cqlshlib.saferscanner import SaferScanner


class LexingError(Exception):

    @classmethod
    def from_text(cls, rulestr, unmatched, msg='Lexing error'):
        bad_char = len(rulestr) - len(unmatched)
        linenum = rulestr[:bad_char].count('\n') + 1
        charnum = len(rulestr[:bad_char].rsplit('\n', 1)[-1]) + 1
        snippet_start = max(0, min(len(rulestr), bad_char - 10))
        snippet_end = max(0, min(len(rulestr), bad_char + 10))
        msg += " (Error at: '...%s...')" % (rulestr[snippet_start:snippet_end],)
        raise cls(linenum, charnum, msg)

    def __init__(self, linenum, charnum, msg='Lexing error'):
        self.linenum = linenum
        self.charnum = charnum
        self.msg = msg
        self.args = (linenum, charnum, msg)

    def __str__(self):
        return '%s at line %d, char %d' % (self.msg, self.linenum, self.charnum)


class Hint:

    def __init__(self, text):
        self.text = text

    def __hash__(self):
        return hash((id(self.__class__), self.text))

    def __eq__(self, other):
        return isinstance(other, self.__class__) and other.text == self.text

    def __repr__(self):
        return '%s(%r)' % (self.__class__, self.text)


def is_hint(obj):
    return isinstance(obj, Hint)


class ParseContext:
    """
    These are meant to be immutable, although it would be something of a
    pain to enforce that in python.
    """

    def __init__(self, ruleset, bindings, matched, remainder, productionname):
        self.ruleset = ruleset
        self.bindings = bindings
        self.matched = matched
        self.remainder = remainder
        self.productionname = productionname

    def get_production_by_name(self, name):
        return self.ruleset[name]

    def get_completer(self, symname):
        return self.ruleset[(self.productionname, symname)]

    def get_binding(self, name, default=None):
        return self.bindings.get(name, default)

    def with_binding(self, name, val):
        newbinds = self.bindings.copy()
        newbinds[name] = val
        return self.__class__(self.ruleset, newbinds, self.matched,
                              self.remainder, self.productionname)

    def with_match(self, num):
        return self.__class__(self.ruleset, self.bindings,
                              self.matched + self.remainder[:num],
                              self.remainder[num:], self.productionname)

    def with_production_named(self, newname):
        return self.__class__(self.ruleset, self.bindings, self.matched,
                              self.remainder, newname)

    def extract_orig(self, tokens=None):
        if tokens is None:
            tokens = self.matched
        if not tokens:
            return ''
        orig = self.bindings.get('*SRC*', None)
        if orig is None:
            # pretty much just guess
            return ' '.join([t[1] for t in tokens])
        # low end of span for first token, to high end of span for last token
        orig_text = orig[tokens[0][2][0]:tokens[-1][2][1]]
        return orig_text

    def __repr__(self):
        return '<%s matched=%r remainder=%r prodname=%r bindings=%r>' \
               % (self.__class__.__name__, self.matched, self.remainder, self.productionname, self.bindings)


class Matcher:

    def __init__(self, arg):
        self.arg = arg

    def match(self, ctxt, completions):
        raise NotImplementedError

    def match_with_results(self, ctxt, completions):
        matched_before = len(ctxt.matched)
        newctxts = self.match(ctxt, completions)
        return [(newctxt, newctxt.matched[matched_before:]) for newctxt in newctxts]

    @staticmethod
    def try_registered_completion(ctxt, symname, completions):
        debugging = ctxt.get_binding('*DEBUG*', False)
        if ctxt.remainder or completions is None:
            return False
        try:
            completer = ctxt.get_completer(symname)
        except KeyError:
            return False
        if debugging:
            print("Trying completer %r with %r" % (completer, ctxt))
        try:
            new_compls = completer(ctxt)
        except Exception:
            if debugging:
                import traceback
                traceback.print_exc()
            return False
        if debugging:
            print("got %r" % (new_compls,))
        completions.update(new_compls)
        return True

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.arg)


class Choice(Matcher):

    def match(self, ctxt, completions):
        foundctxts = []
        for each in self.arg:
            subctxts = each.match(ctxt, completions)
            foundctxts.extend(subctxts)
        return foundctxts


class OneOrNone(Matcher):

    def match(self, ctxt, completions):
        return [ctxt] + list(self.arg.match(ctxt, completions))


class Repeat(Matcher):

    def match(self, ctxt, completions):
        found = [ctxt]
        ctxts = [ctxt]
        while True:
            new_ctxts = []
            for each in ctxts:
                new_ctxts.extend(self.arg.match(each, completions))
            if not new_ctxts:
                return found
            found.extend(new_ctxts)
            ctxts = new_ctxts


class RuleReference(Matcher):

    def match(self, ctxt, completions):
        prevname = ctxt.productionname
        try:
            rule = ctxt.get_production_by_name(self.arg)
        except KeyError:
            raise ValueError("Can't look up production rule named %r" % (self.arg,))
        output = rule.match(ctxt.with_production_named(self.arg), completions)
        return [c.with_production_named(prevname) for c in output]


class RuleSeries(Matcher):

    def match(self, ctxt, completions):
        ctxts = [ctxt]
        for patpiece in self.arg:
            new_ctxts = []
            for each in ctxts:
                new_ctxts.extend(patpiece.match(each, completions))
            if not new_ctxts:
                return ()
            ctxts = new_ctxts
        return ctxts


class NamedSymbol(Matcher):

    def __init__(self, name, arg):
        Matcher.__init__(self, arg)
        self.name = name

    def match(self, ctxt, completions):
        pass_in_compls = completions
        if self.try_registered_completion(ctxt, self.name, completions):
            # don't collect other completions under this; use a dummy
            pass_in_compls = set()
        results = self.arg.match_with_results(ctxt, pass_in_compls)
        return [c.with_binding(self.name, ctxt.extract_orig(matchtoks))
                for (c, matchtoks) in results]

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__, self.name, self.arg)


class NamedCollector(NamedSymbol):

    def match(self, ctxt, completions):
        pass_in_compls = completions
        if self.try_registered_completion(ctxt, self.name, completions):
            # don't collect other completions under this; use a dummy
            pass_in_compls = set()
        output = []
        for ctxt, matchtoks in self.arg.match_with_results(ctxt, pass_in_compls):
            oldval = ctxt.get_binding(self.name, ())
            output.append(ctxt.with_binding(self.name, oldval + (ctxt.extract_orig(matchtoks),)))
        return output


class TerminalMatcher(Matcher):

    def match(self, ctxt, completions):
        raise NotImplementedError

    def pattern(self):
        raise NotImplementedError


class RegexRule(TerminalMatcher):

    def __init__(self, pat):
        TerminalMatcher.__init__(self, pat)
        self.regex = pat
        self.re = re.compile(pat + '$', re.IGNORECASE | re.DOTALL)

    def match(self, ctxt, completions):
        if ctxt.remainder:
            if self.re.match(ctxt.remainder[0][1]):
                return [ctxt.with_match(1)]
        elif completions is not None:
            completions.add(Hint('<%s>' % ctxt.productionname))
        return []

    def pattern(self):
        return self.regex


class TextMatch(TerminalMatcher):
    alpha_re = re.compile(r'[a-zA-Z]')

    def __init__(self, text):
        try:
            TerminalMatcher.__init__(self, eval(text))
        except SyntaxError:
            print("bad syntax %r" % (text,))

    def match(self, ctxt, completions):
        if ctxt.remainder:
            if self.arg.lower() == ctxt.remainder[0][1].lower():
                return [ctxt.with_match(1)]
        elif completions is not None:
            completions.add(self.arg)
        return []

    def pattern(self):
        # can't use (?i) here- Scanner component regex flags won't be applied
        def ignorecaseify(matchobj):
            val = matchobj.group(0)
            return '[%s%s]' % (val.upper(), val.lower())

        return self.alpha_re.sub(ignorecaseify, re.escape(self.arg))


class CaseMatch(TextMatch):

    def match(self, ctxt, completions):
        if ctxt.remainder:
            if self.arg == ctxt.remainder[0][1]:
                return [ctxt.with_match(1)]
        elif completions is not None:
            completions.add(self.arg)
        return []

    def pattern(self):
        return re.escape(self.arg)


class WordMatch(TextMatch):

    def pattern(self):
        return r'\b' + TextMatch.pattern(self) + r'\b'


class CaseWordMatch(CaseMatch):

    def pattern(self):
        return r'\b' + CaseMatch.pattern(self) + r'\b'


class TerminalTypeMatcher(Matcher):

    def __init__(self, tokentype, submatcher):
        Matcher.__init__(self, tokentype)
        self.tokentype = tokentype
        self.submatcher = submatcher

    def match(self, ctxt, completions):
        if ctxt.remainder:
            if ctxt.remainder[0][0] == self.tokentype:
                return [ctxt.with_match(1)]
        elif completions is not None:
            self.submatcher.match(ctxt, completions)
        return []

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__, self.tokentype, self.submatcher)


class ParsingRuleSet:
    """Define the BNF tokenization rules for cql3handling.syntax_rules. Backus-Naur Form consists of
       - Production rules in the form: Left-Hand-Side ::= Right-Hand-Side.  The LHS is a non-terminal.
       - Productions or non-terminal symbols
       - Terminal symbols.  Every terminal is a single token.
    """

    RuleSpecScanner = SaferScanner([
        (r'::=', lambda s, t: t),                   # BNF rule definition
        (r'\[[a-z0-9_]+\]=', lambda s, t: ('named_collector', t[1:-2])),
        (r'[a-z0-9_]+=', lambda s, t: ('named_symbol', t[:-1])),
        (r'/(\[\^?.[^]]*\]|[^/]|\\.)*/', lambda s, t: ('regex', t[1:-1].replace(r'\/', '/'))),
        (r'"([^"]|\\.)*"', lambda s, t: ('string_literal', t)),
        (r'<[^>]*>', lambda s, t: ('reference', t[1:-1])),
        (r'\bJUNK\b', lambda s, t: ('junk', t)),
        (r'[@()|?*;]', lambda s, t: t),
        (r'\s+', None),                             # whitespace
        (r'#[^\n]*', None),
    ], re.IGNORECASE | re.DOTALL | re.UNICODE)

    def __init__(self):
        self.ruleset = {}
        self.scanner = None
        self.terminals = []

    @classmethod
    def from_rule_defs(cls, rule_defs):
        prs = cls()
        prs.ruleset, prs.terminals = cls.parse_rules(rule_defs)
        return prs

    @classmethod
    def parse_rules(cls, rulestr):
        tokens, unmatched = cls.RuleSpecScanner.scan(rulestr)
        if unmatched:
            raise LexingError.from_text(rulestr, unmatched, msg="Syntax rules are unparsable")
        rules = {}
        terminals = []
        tokeniter = iter(tokens)
        for t in tokeniter:
            if isinstance(t, tuple) and t[0] in ('reference', 'junk'):
                assign = next(tokeniter)
                if assign != '::=':
                    raise ValueError('Unexpected token %r; expected "::="' % (assign,))
                name = t[1]
                production = cls.read_rule_tokens_until(';', tokeniter)
                if isinstance(production, TerminalMatcher):
                    terminals.append((name, production))
                    production = TerminalTypeMatcher(name, production)
                rules[name] = production
            else:
                raise ValueError('Unexpected token %r; expected name' % (t,))
        return rules, terminals

    @staticmethod
    def mkrule(pieces):
        if isinstance(pieces, (tuple, list)):
            if len(pieces) == 1:
                return pieces[0]
            return RuleSeries(pieces)
        return pieces

    @classmethod
    def read_rule_tokens_until(cls, endtoks: Union[str, int], tokeniter):
        if isinstance(endtoks, str):
            endtoks = (endtoks,)
        counttarget = None
        if isinstance(endtoks, int):
            counttarget = endtoks
            endtoks = ()
        countsofar = 0
        myrules = []
        mybranches = [myrules]
        for t in tokeniter:
            countsofar += 1
            if t in endtoks:
                if len(mybranches) == 1:
                    return cls.mkrule(mybranches[0])
                return Choice(list(map(cls.mkrule, mybranches)))
            if isinstance(t, tuple):
                if t[0] == 'reference':
                    t = RuleReference(t[1])
                elif t[0] == 'string_literal':
                    if t[1][1].isalnum() or t[1][1] == '_':
                        t = WordMatch(t[1])
                    else:
                        t = TextMatch(t[1])
                elif t[0] == 'regex':
                    t = RegexRule(t[1])
                elif t[0] == 'named_collector':
                    t = NamedCollector(t[1], cls.read_rule_tokens_until(1, tokeniter))
                elif t[0] == 'named_symbol':
                    t = NamedSymbol(t[1], cls.read_rule_tokens_until(1, tokeniter))
            elif t == '(':
                t = cls.read_rule_tokens_until(')', tokeniter)
            elif t == '?':
                t = OneOrNone(myrules.pop(-1))
            elif t == '*':
                t = Repeat(myrules.pop(-1))
            elif t == '@':
                val = next(tokeniter)
                if not isinstance(val, tuple) or val[0] != 'string_literal':
                    raise ValueError("Unexpected token %r following '@'" % (val,))
                t = CaseMatch(val[1])
            elif t == '|':
                myrules = []
                mybranches.append(myrules)
                continue
            else:
                raise ValueError('Unparseable rule token %r after %r' % (t, myrules[-1]))
            myrules.append(t)
            if countsofar == counttarget:
                if len(mybranches) == 1:
                    return cls.mkrule(mybranches[0])
                return Choice(list(map(cls.mkrule, mybranches)))
        raise ValueError('Unexpected end of rule tokens')

    def append_rules(self, rulestr):
        rules, terminals = self.parse_rules(rulestr)
        self.ruleset.update(rules)
        self.terminals.extend(terminals)
        if terminals:
            self.scanner = None  # recreate it if/when necessary

    def register_completer(self, func, rulename, symname):
        self.ruleset[(rulename, symname)] = func

    def make_lexer(self):
        def make_handler(name):
            if name == 'JUNK':
                return None
            return lambda s, t: (name, t, s.match.span())

        regexes = [(p.pattern(), make_handler(name)) for (name, p) in self.terminals]
        return SaferScanner(regexes, re.IGNORECASE | re.DOTALL | re.UNICODE).scan

    def lex(self, text):
        if self.scanner is None:
            self.scanner = self.make_lexer()
        tokens, unmatched = self.scanner(text)
        if unmatched:
            raise LexingError.from_text(text, unmatched, 'text could not be lexed')
        return tokens

    def parse(self, startsymbol, tokens, init_bindings=None):
        if init_bindings is None:
            init_bindings = {}
        ctxt = ParseContext(self.ruleset, init_bindings, (), tuple(tokens), startsymbol)
        pattern = self.ruleset[startsymbol]
        return pattern.match(ctxt, None)

    def whole_match(self, startsymbol, tokens, srcstr=None):
        bindings = {}
        if srcstr is not None:
            bindings['*SRC*'] = srcstr
        for val in self.parse(startsymbol, tokens, init_bindings=bindings):
            if not val.remainder:
                return val

    def lex_and_parse(self, text, startsymbol='Start'):
        return self.parse(startsymbol, self.lex(text), init_bindings={'*SRC*': text})

    def lex_and_whole_match(self, text, startsymbol='Start'):
        tokens = self.lex(text)
        return self.whole_match(startsymbol, tokens, srcstr=text)

    def complete(self, startsymbol, tokens, init_bindings=None):
        if init_bindings is None:
            init_bindings = {}
        ctxt = ParseContext(self.ruleset, init_bindings, (), tuple(tokens), startsymbol)
        pattern = self.ruleset[startsymbol]
        if init_bindings.get('*DEBUG*', False):
            completions = Debugotron(stream=sys.stderr)
        else:
            completions = set()
        pattern.match(ctxt, completions)
        return completions


class Debugotron(set):
    depth = 10

    def __init__(self, initializer=(), stream=sys.stdout):
        set.__init__(self, initializer)
        self.stream = stream

    def add(self, item):
        self._note_addition(item)
        set.add(self, item)

    def _note_addition(self, item):
        self.stream.write("\nitem %r added by:\n" % (item,))
        frame = inspect.currentframe().f_back.f_back
        for i in range(self.depth):
            name = frame.f_code.co_name
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno
            if 'self' in frame.f_locals:
                clsobj = frame.f_locals['self']
                line = '%s.%s() (%s:%d)' % (clsobj, name, filename, lineno)
            else:
                line = '%s (%s:%d)' % (name, filename, lineno)
            self.stream.write('  - %s\n' % (line,))
            if i == 0 and 'ctxt' in frame.f_locals:
                self.stream.write('    - %s\n' % (frame.f_locals['ctxt'],))
            frame = frame.f_back

    def update(self, items):
        if items:
            self._note_addition(items)
        set.update(self, items)
