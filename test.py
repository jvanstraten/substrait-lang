import sys
from antlr4 import *
from parser.SubstraitParser import SubstraitParser
from parser.SubstraitLexer import SubstraitLexer
from parser.SubstraitListener import SubstraitListener

input = FileStream(sys.argv[1])
lexer = SubstraitLexer(input)
stream = CommonTokenStream(lexer)
parser = SubstraitParser(stream)
tree = parser.substrait()
listener = SubstraitListener()
walker = ParseTreeWalker()
walker.walk(listener, tree)

#print(tree)
