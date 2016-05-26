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

from xmlrpc.server import SimpleXMLRPCServer
from http.client import HTTPConnection
from argparse import ArgumentParser


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

        self.connection = connection
        self.headers = headers
        self.xmlrpc_url = "http://127.0.0.1:8000/RPC2"
        self.tenant_id = tenant_id

        # register callback
        self.wtp_up(callback=self.wtp_up_callback)

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

    def __synch_callback(self, url):
        """Synchonized callback defined on the control with the local ones."""

        cmd = ('GET', url)
        response, body = self.execute(cmd)

        if response[0] != 200:
            print("%s %s" % response)
            sys.exit()

        for entry in body:
            if 'callback' in entry:
                callback = entry['callback'][1]
                if hasattr(globals(), callback):
                    func = getattr(globals(), callback)
                    self.register_function(func)

    def execute(self, cmd, data=None):
        """ Run command. """

        self.connection.request(cmd[0], cmd[1], headers=self.headers,
                                body=json.dumps(data))

        response = self.connection.getresponse()
        resp = response.readall().decode('utf-8')

        if resp:
            return (response.code, response.reason), json.loads(resp)

        return (response.code, response.reason), None

    def wtp_up(self, callback):
        """WTP Up primitive."""

        url = '/api/v1/tenants/%s/wtpup' % self.tenant_id

        self.__synch_callback(url)

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

    parser.add_argument("-a", "--hostname", dest="host", default="127.0.0.1",
                        help="EmPOWER REST address; default='127.0.0.1'")

    parser.add_argument("-p", "--port", dest="port", default="8888",
                        help="EmPOWER REST port; default=8888")

    parser.add_argument("-u", "--user", dest="user", default="root",
                        help="EmPOWER admin user; default='root'")

    parser.add_argument("-n", "--no-passwd", action="store_true",
                        dest="no_passwd", default=False,
                        help="Run without password; default false")

    parser.add_argument("-f", "--passwd-file", dest="passwdfile",
                        default=None, help="Password file; default=none")

    parser.add_argument("-i", "--tenant-id", dest="tenant_id",
                        default=None, help="Tenant id; default=none")

    parser.add_argument("-t", "--transport", dest="transport", default="http",
                        help="Specify the transport; default='http'")

    (args, _) = parser.parse_known_args(sys.argv[1:])

    if not args.tenant_id:
        raise ValueError("You must specify a valid tenant_id")

    connection, headers = get_connection(args)

    simple_app = SimpleApp(connection, headers, args.tenant_id)

    # Start xml-rpc server
    simple_app.serve_forever()


if __name__ == '__main__':
    main()
