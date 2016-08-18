#!/usr/bin/env python3
#
# Copyright (c) 2016 Roberto Riggio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""A proof-of-concept python app leveraging the EmPOWER rest interface."""

import sys
import getpass
import base64
import json
import threading

from uuid import UUID
from xmlrpc.server import SimpleXMLRPCServer
from http.client import HTTPConnection
from argparse import ArgumentParser

BT_L20 = 0
BT_HT20 = 1
BT_HT40 = 2

L20 = 'L20'
HT20 = 'HT20'
HT40 = 'HT40'

BANDS = {BT_L20: L20,
         BT_HT20: HT20,
         BT_HT40: HT40}

REVERSE_BANDS = {L20: BT_L20,
                 HT20: BT_HT20,
                 HT40: BT_HT40}

DEFAULT_PERIOD = 5000


def get_connection(args):
    """ Fetch url from option parser. """

    if args.transport == "http":
        connection = HTTPConnection(args.host, args.port)
    else:
        raise ValueError("transport not supported: %s" % args.transport)

    if args.no_passwd:
        return (connection, {})

    if args.passwdfile is None:
        passwd = getpass.getpass("Password: ")
    else:
        passwd = open(args.passwdfile, "r").read().strip()

    auth_str = "%s:%s" % (args.user, passwd)
    auth = base64.b64encode(auth_str.encode('utf-8'))
    headers = {'Authorization': 'Basic %s' % auth.decode('utf-8'),
               'Content-type': 'application/json'}

    return (connection, headers)


class SimpleApp(SimpleXMLRPCServer):
    """Demo XML-RPC App."""

    def __init__(self, connection, headers, tenant_id):

        SimpleXMLRPCServer.__init__(self, ("localhost", 8000))

        self.tenant_id = tenant_id
        self.every = DEFAULT_PERIOD

        self.connection = connection
        self.headers = headers
        self.xmlrpc_url = "http://127.0.0.1:8000/RPC2"
        self.worker = None

        # register callback
        self.wtp_up(callback=self.wtp_up_callback)

    def run(self):
        """Start hello messages."""

        self.loop()

        threading.Timer(self.every / 1000, self.run).start()

    def loop(self):
        """Periodic task."""

        wtps = self.wtps()

        for wtp in wtps:
            for entry in wtp['supports']:
                block = {}
                block['hwaddr'] = entry['hwaddr']
                block['channel'] = entry['channel']
                block['band'] = REVERSE_BANDS[entry['band']]
                block['wtp'] = entry['addr']
                self.summary(block=block, callback=self.summary_callback)

    def summary_callback(self, tmp):

        print("ciao")
        print(tmp)

    def summary(self, block, callback):
        """Summary primitive."""

        url = '/api/v1/tenants/%s/summary' % self.tenant_id
        data = {"version": "1.0",
                "block": block,
                "callback": (self.xmlrpc_url, callback.__name__)}

        response, _ = self.execute(('POST', url), data)

        if response[0] != 201:
            print("%s %s" % response)

        self.register_function(callback)

    def _dispatch(self, method, params):
        try:
            func = getattr(self, method)
        except AttributeError:
            raise Exception('method "%s" is not supported' % method)
        else:
            new_args = []
            for arg in params:
                new_args.append(json.loads(arg))
            func(*new_args)

    def execute(self, cmd, data=None):
        """ Run command. """

        self.connection.request(cmd[0], cmd[1], headers=self.headers,
                                body=json.dumps(data))

        response = self.connection.getresponse()
        resp = response.read().decode('utf-8')

        if resp:
            return (response.code, response.reason), json.loads(resp)

        return (response.code, response.reason), None

    def wtps(self):
        """List wtps primitive."""

        url = '/api/v1/tenants/%s/wtps' % self.tenant_id
        response, data = self.execute(('GET', url))

        if response[0] != 200:
            print("%s %s" % response)

        return data

    def wtp_up(self, callback):
        """WTP Up primitive."""

        url = '/api/v1/tenants/%s/wtpup' % self.tenant_id
        data = {"version": "1.0",
                "callback": (self.xmlrpc_url, callback.__name__)}

        response, _ = self.execute(('POST', url), data)

        if response[0] != 201:
            print("%s %s" % response)

        self.register_function(callback)

    def wtp_up_callback(self, wtp):
        """Called when a WTP is coming online."""

        print("Tenant %s, WTP %s is up" % (self.tenant_id, wtp['addr']))


def main():
    """ Parse argument list and execute command. """

    usage = "%s [options]" % sys.argv[0]

    parser = ArgumentParser(usage=usage)

    parser.add_argument("-r", "--host", dest="host", default="127.0.0.1",
                        help="REST server address; default='127.0.0.1'")
    parser.add_argument("-p", "--port", dest="port", default="8888",
                        help="REST server port; default=8888")
    parser.add_argument("-u", "--user", dest="user", default="root",
                        help="EmPOWER admin user; default='root'")
    parser.add_argument("-n", "--no-passwd", action="store_true",
                        dest="no_passwd", default=False,
                        help="Run without password; default false")
    parser.add_argument("-f", "--passwd-file", dest="passwdfile",
                        default=None, help="Password file; default=none")
    parser.add_argument("-t", "--transport", dest="transport", default="http",
                        help="Specify the transport; default='http'")
    parser.add_argument("-w", "--tenant_id", dest="tenant_id", default=None,
                        help="Tenant id'")

    (args, _) = parser.parse_known_args(sys.argv[1:])

    tenant_id = UUID(args.tenant_id)

    if not tenant_id:
        raise ValueError("You must specify a valid tenant_id")

    connection, headers = get_connection(args)

    simple_app = SimpleApp(connection, headers, args.tenant_id)
    simple_app.run()

    # Start xml-rpc server
    simple_app.serve_forever()


if __name__ == '__main__':
    main()
