# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


class SavannaException(Exception):
    """Base Exception for the project

    To correctly use this class, inherit from it and define
    a 'message' and 'code' properties.
    """
    message = "An unknown exception occurred"
    code = "UNKNOWN_EXCEPTION"

    def __str__(self):
        return self.message

    def __init__(self):
        super(SavannaException, self).__init__(
            '%s: %s' % (self.code, self.message))


class RemoteError(Exception):
    """A base class for all the remote exceptions.

    There are two types of the remote exceptions:
     * Wrapping exceptions. These should be constructed with the
       orignal exception passed as 'exc' parameter.
     * Other exceptions. These should be constructed with the
       error message passed as 'msg' parameter.
    """

    def __init__(self, exc=None, msg=''):
        if exc:
            exc_type = type(exc)
            msg = '%s.%s: %s' % (exc_type.__module__,
                                 exc_type.__name__, str(exc))

        msg = msg.decode('ascii', 'ignore')

        super(RemoteError, self).__init__(msg)


class RemoteCommandError(RemoteError):
    message = "Error during command execution: \"%s\""

    def __init__(self, cmd, ret_code=None, stdout=None,
                 stderr=None):

        stdout = stdout.decode('ascii', 'ignore')
        stderr = stderr.decode('ascii', 'ignore')

        self.cmd = cmd
        self.ret_code = ret_code
        self.stdout = stdout
        self.stderr = stderr

        self.message = self.message % cmd

        if ret_code:
            self.message += '\nReturn code: ' + str(ret_code)

        if stderr:
            self.message += '\nSTDERR:\n' + stderr

        if stdout:
            self.message += '\nSTDOUT:\n' + stdout

        super(RemoteCommandError, self).__init__(msg=self.message)


class RemoteConnectionError(RemoteError):
    """Signals that the requested connection failed on the remote side."""
