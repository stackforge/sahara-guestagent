# Copyright (c) 2014 Mirantis Inc.
# Copyright (c) 2013 Eric Larson
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

import eventlet
eventlet.monkey_patch()

import contextlib
import os
import pickle
import requests
import subprocess
import sys
import tempfile

from oslo.config import cfg
from oslo import messaging

from savanna import exceptions as ex
from savanna import guestagent
from savanna.guestagent.openstack.common import log


agent_ops = [
    cfg.StrOpt('server_id',
               help='Server ID the agent should use as its identifier.')
]

CONF = cfg.CONF
CONF.register_opts(agent_ops)


LOG = log.getLogger(__name__)


# TODO(dmitryme): once requests in requirements are >= 2.1,
# replace that self-made serialization with pickling. Specifically,
# we wait for the following commit:
# https://github.com/kennethreitz/requests/commit/512beb8

# Below is the list of fields from the commit with some fields
# defencively removed from serialization:
#  * elapsed - absent in requests 1.1
#  * request - creates circular reference; does not work for json encoding
#  * history - removed just in case; seems like we don't need it anyway
_resp_attrs = [
    '_content',
    'status_code',
    'headers',
    'url',
    # 'history',
    'encoding',
    'reason',
    'cookies',
    # 'elapsed',
    # 'request',
]


# TODO(dmitryme): serialize everything, not just HTTP negotiation
# we can read/write binary data, execute_command can return binary data, etc.
def _serialize_http_response(f):
    def handle(*args, **kwargs):
        # TODO(dmitryme): find a way to avoid dummy exception wrapping
        try:
            resp = f(*args, **kwargs)
        except Exception as e:
            raise RuntimeError(type(e).__name__ + ': ' + str(e))

        if not resp._content_consumed:
            resp.content

        dct = dict(
            (attr, getattr(resp, attr, None))
            for attr in _resp_attrs
        )

        # We pickle returned data because of the following:
        #  * oslo.messaging AMQP driver sends messages json-encoded
        #  * json encoding by default expects all input strings to be utf-8
        #  * we can have non-utf8 symbols in HTTP response
        # Pickle protocol 0 reliably produces ascii strings
        return pickle.dumps(dct, protocol=0)

    return handle


class AgentEndpoint(object):
    def execute_command(self, ctx, cmd, run_as_root, get_stderr,
                        raise_when_error):
        return self._execute_command(cmd, run_as_root, get_stderr,
                                     raise_when_error)

    def _execute_command(self, cmd, run_as_root=False, get_stderr=False,
                         raise_when_error=True):

        if run_as_root:
            cmd = 'sudo bash -c "%s"' % cmd

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             shell=True, executable='/bin/bash')

        stdout, stderr = p.communicate()
        ret_code = p.returncode

        if ret_code and raise_when_error:
            raise ex.RemoteCommandException(cmd=cmd, ret_code=ret_code,
                                            stdout=stdout, stderr=stderr)

        if get_stderr:
            return ret_code, stdout, stderr
        else:
            return ret_code, stdout

    @contextlib.contextmanager
    def _safely_unlink(self, filename):
        yield

        try:
            os.unlink(filename)
        except OSError:
            # if file does not exist, we don't care
            pass

    def write_files_to(self, ctxt, files, run_as_root):
        for filename, data in files.iteritems():
            if run_as_root:
                fd, tmp_name = tempfile.mkstemp()

                with self._safely_unlink(tmp_name):
                    with os.fdopen(fd, 'w') as fl:
                        fl.write(data)
                    self._execute_command('cp %s %s' % (tmp_name, filename),
                                          run_as_root=True)

            else:
                with open(filename, 'w') as fl:
                    fl.write(data)

    def read_file_from(self, ctxt, remote_file, run_as_root):
        if run_as_root:
            fd, tmp_name = tempfile.mkstemp()

            with self._safely_unlink(tmp_name):
                os.close(fd)
                self._execute_command('cp %s %s' % (remote_file, tmp_name),
                                      run_as_root=True)
                with open(tmp_name) as fl:
                    return fl.read()

        else:
            with open(remote_file) as fl:
                return fl.read()

    @_serialize_http_response
    def request(self, ctxt, http_method, url, kwargs):
        if ('auth' in kwargs and isinstance(kwargs['auth'], list) and
                len(kwargs['auth']) == 2):
            # messaging converts tuple to list, reverting it back
            kwargs['auth'] = tuple(kwargs['auth'])

        return requests.request(http_method, url, **kwargs)


def main():
    CONF(sys.argv[1:], project='savanna-guestagent',
         version=guestagent.__version__)

    log.setup('guestagent')

    transport = messaging.get_transport(cfg.CONF)

    LOG.info('Listening as server_id "%s" on topic "savanna-topic"' %
             CONF.server_id)

    target = messaging.Target(topic='savanna-topic', version='1.0',
                              server=CONF.server_id)
    server = messaging.get_rpc_server(transport, target,
                                      endpoints=[AgentEndpoint()],
                                      executor='eventlet')

    server.start()
    server.wait()
