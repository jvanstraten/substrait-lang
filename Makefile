
#ANTLR_JAR   = "/usr/share/java/antlr-complete.jar"
ANTLR_JAR   = $(shell pwd)/antlr.jar
JAVA_PREFIX = "$(shell pwd)/java_parser:$(ANTLR_JAR):$(CLASSPATH)"
JAVA        = CLASSPATH=$(JAVA_PREFIX) java
JAVAC       = CLASSPATH=$(JAVA_PREFIX) javac
ANTLR       = $(JAVA) -jar $(ANTLR_JAR)
GRUN        = $(JAVA) org.antlr.v4.gui.TestRig

GRAMMAR     = Substrait

.PHONY: all
all: parser/$(GRAMMAR)Parser.py test

$(ANTLR_JAR):
	curl https://www.antlr.org/download/antlr-4.9.3-complete.jar -o $(ANTLR_JAR)

parser/$(GRAMMAR)Parser.py: $(GRAMMAR).g4 $(ANTLR_JAR)
	$(ANTLR) -o parser -Dlanguage=Python3 $<
	touch parser/__init__.py

java_parser/$(GRAMMAR)Parser.class: $(GRAMMAR).g4 $(ANTLR_JAR)
	$(ANTLR) -o java_parser $<
	cd java_parser && $(JAVAC) *.java

test.sub: disas.py
	python3 $< > test.sub

.PHONY: test
test: java_parser/$(GRAMMAR)Parser.class test.sub
	$(GRUN) Substrait substrait test.sub -gui

.PHONY: clean
clean:
	rm -rf parser java_parser
	rm test.sub
	-rm $(ANTLR_JAR)

