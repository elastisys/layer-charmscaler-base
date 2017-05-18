#!/usr/bin/make

charm_dir := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

all: lint unit_test

clean:
	rm -rf $(charm_dir).tox
	rm -rf $(charm_dir).cache
	rm -rf $(charm_dir).unit-state.db
	rm -rf $(charm_dir)*/__pycache__

lint:
	tox -c $(charm_dir)tox.ini -e lint

unit_test:
ifdef VERBOSE
	tox -c $(charm_dir)tox.ini -- -v -s
else
	tox -c $(charm_dir)tox.ini
endif
