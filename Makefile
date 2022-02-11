
#ANTLR_JAR   = "/usr/share/java/antlr-complete.jar"
ANTLR_JAR   = $(shell pwd)/antlr.jar
JAVA_PREFIX = "$(shell pwd)/java_parser:$(ANTLR_JAR):$(CLASSPATH)"
JAVA        = CLASSPATH=$(JAVA_PREFIX) java
JAVAC       = CLASSPATH=$(JAVA_PREFIX) javac
ANTLR       = $(JAVA) -jar $(ANTLR_JAR)
GRUN        = $(JAVA) org.antlr.v4.gui.TestRig

GRAMMAR     = Substrait

.PHONY: all
all: disas_test as_test

$(ANTLR_JAR):
	curl https://www.antlr.org/download/antlr-4.9.3-complete.jar -o $(ANTLR_JAR)

parser/$(GRAMMAR)Parser.py: $(GRAMMAR).g4 $(ANTLR_JAR)
	$(ANTLR) -o parser -Dlanguage=Python3 $<
	touch parser/__init__.py

java_parser/$(GRAMMAR)Parser.class: $(GRAMMAR).g4 $(ANTLR_JAR)
	$(ANTLR) -o java_parser $<
	cd java_parser && $(JAVAC) *.java

disas_test.sub: disas.py tpc1.json
	python3 $^ $@

.PHONY: disas_test
disas_test: java_parser/$(GRAMMAR)Parser.class disas_test.sub
	$(GRUN) Substrait substrait disas_test.sub -gui

.PHONY: as_test
as_test: disas_test.sub parser/$(GRAMMAR)Parser.py
	python3 as.py $^

.PHONY: clean
clean:
	rm -rf parser java_parser
	rm disas_test.sub
	-rm $(ANTLR_JAR)

