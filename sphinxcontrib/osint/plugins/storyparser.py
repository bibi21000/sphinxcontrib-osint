# -*- encoding: utf-8 -*-
"""
The story parser
------------------


"""
__author__ = 'bibi21000 aka Sébastien GALLET'
__email__ = 'bibi21000@gmail.com'

import textparser
from textparser import Sequence
from textparser import ZeroOrMore
from textparser import choice
from textparser import Token

class Parser(textparser.Parser):

    def token_specs(self):
        return [
            ('EXTSRC',              r':osint:extsrc:`[^`]+`'),
            ('EXTURL',              r':osint:exturl:`[^`]+`'),
            ('LINK',                r'`[^`]+`_'),
            ('MENTION',             r'@[^\s]+'),
            ('TAG',                 r'#[^\s]+'),
            ('WORD',                r'[^\s]+'),
        ]

    def grammar(self):
        return Sequence(ZeroOrMore(choice('EXTSRC', 'EXTURL', 'LINK', 'MENTION', 'TAG', 'WORD')))

class StoryParser():
    parser = Parser

    def parse(self, lines):
        tree = []
        for line in lines:
            tree += self.parser().parse(line, token_tree=True)
        ret = []
        for t in tree:
            line = []
            if t == []:
                line.append(Token('TEXT', '', 0))
            else:
                ttext = []
                for tt in t:
                    if tt.kind == 'WORD':
                        ttext.append(tt)
                    else:
                        if ttext != []:
                            line.append(Token('TEXT', ' '.join([token.value for token in ttext]), ttext[0].offset))
                            ttext = []
                        if tt.kind == 'EXTSRC':
                            line.append(Token(tt.kind, tt.value.replace(':osint:extsrc:', '').replace('`', ''), tt.offset))
                        elif tt.kind == 'EXTURL':
                            line.append(Token(tt.kind, tt.value.replace(':osint:exturl:', '').replace('`', ''), tt.offset))
                        elif tt.kind == 'LINK':
                            line.append(Token(tt.kind, tt.value.replace('`_', '').replace('`', ''), tt.offset))
                        elif tt.kind == 'MENTION':
                            line.append(Token(tt.kind, tt.value.replace('@', ''), tt.offset))
                        elif tt.kind == 'TAG':
                            line.append(Token(tt.kind, tt.value.replace('#', ''), tt.offset))
                        else:
                            line.append(tt)
                if ttext != []:
                    line.append(Token('TEXT', ' '.join([token.value for token in ttext]), ttext[0].offset))
            ret.append(line)
        return ret

