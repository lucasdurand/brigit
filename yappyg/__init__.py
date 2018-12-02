# -*- coding: utf-8 -*-
# Copyright (C) 2018 by Lucas Durand, Kozea

import logging
from logging import getLogger
import os, sys
from datetime import datetime
import pexpect
import getpass
from io import StringIO 
import warnings

handler = None
try:
    from log_colorizer import make_colored_stream_handler
    handler = make_colored_stream_handler()
except ImportError:
    handler = logging.StreamHandler()


class NullHandler(logging.Handler):
    """Handler that do nothing"""
    def emit(self, record):
        """Do nothing"""


class GitException(Exception):
    """Exception raised when something went wrong for git"""

    def __init__(self, message):
        super(GitException, self).__init__(message)


class RawGit(object):
    """Git command wrapper"""

    def __init__(self, git_path, encoding="utf-8", timeout=30):
        """Init a Git wrapper with an instance"""
        self.path = git_path
        self.encoding = encoding
        self.timeout = timeout 

    def __call__(self, command, *args, **kwargs):
        """Run a command with args as arguments."""
        named = ' '.join(f"--{key}=\"{value}\"" if len(key) > 1 else f"-{key} {value}"
                      for key, value in kwargs.items())
        full_command = f'git {command} {" ".join(args)} {named}'
        self.process = pexpect.spawn(full_command, encoding=self.encoding, cwd=self.path, logfile=sys.stdout, timeout=self.timeout)
        expectations = ['Username*','Password*',pexpect.EOF,pexpect.TIMEOUT]
        stage = self.process.expect(expectations)
        while stage < 2:
            # Stop logging in here! ----------#
            logfile, self.process.logfile = self.process.logfile, None
            if stage == 0:
                # Get Username
                self.process.sendline(input())
            elif stage == 1:
                # Get Password
                self.process.sendline(getpass.getpass())
            # Restore logging
            self.process.logfile = logfile
            # --------------------------------#
            stage = self.process.expect(expectations)
        if stage == 3:
            self.process.stderr.write(f'Time out!\nIf this is a long-running process, increase the timeout with self.timeout=X\nOr are we waiting on a prompt we are not expecting: ${expectations}')
        retcode = self.process.exitstatus
        if retcode:
            warnings.warn(
                "%s has returned %d:\n %s" % (
                    full_command, retcode, self.process.before.strip('\n').split('\n')[-1]))
        return



    def __getattr__(self, name):
        """Any method not implemented will be executed as is."""
        return lambda *args, **kwargs: self(name, *args, **kwargs)


class Git(RawGit):
    """Utility class overloading most used functions"""

    def __init__(self, git_path, remote=None, quiet=True, bare=False):
        """Init the repo or clone the remote if remote is not None."""
        if "~" in git_path:
            git_path = os.path.expanduser(git_path)

        super(Git, self).__init__(git_path)

        dirpath = os.path.dirname(self.path)
        basename = os.path.basename(self.path)
        self.logger = getLogger("brigit")
        if not quiet:
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.addHandler(NullHandler())

        if not os.path.exists(self.path):
            # Non existing repository
            if remote:
                if not os.path.exists(dirpath):
                    os.makedirs(dirpath)
                self.path = dirpath
                # The '--recursive' option will clone all submodules, if any
                self.clone(remote, basename, '--recursive')
                self.path = git_path
            else:
                os.makedirs(self.path)
                if bare:
                    self.init('--bare')
                else:
                    self.init()
        self.remote_path = remote

    def pretty_log(self, *args, **kwargs):
        """Return the log as a list of dict"""
        kwargs["pretty"] = "format:%H;;%an;;%ae;;%at;;%s"
        for line in self.log(*args, **kwargs).split("\n"):
            fields = line.split(";;")
            yield {
                'hash': fields[0],
                'author': {
                    'name': fields[1],
                    'email': fields[2]},
                'datetime': datetime.fromtimestamp(float(fields[3])),
                'message': fields[4]
            }