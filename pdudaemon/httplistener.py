#!/usr/bin/python3

#  Copyright 2018 Matt Hart <matt@mattface.org>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

import logging

from aiohttp import web
from pdudaemon.pdurunner import PDURunner, PDURunnerErrorKind, PDURunnerJob, PDURunnerJobType, PDURunnerResult

logger = logging.getLogger('pdud.http')


class HTTPListener:

    def __init__(self, config, daemon):
        self.config = config
        self.daemon = daemon
        self.settings = config["daemon"]

        self.app = web.Application()
        self.app.add_routes([
            web.get('/pdu/{pdu}/port/{port}', self.handle_port_get),
            web.put('/pdu/{pdu}/port/{port}', self.handle_port_put),
            web.post('/pdu/{pdu}/port/{port}/actions/{action}', self.handle_port_post_action),
            web.get('/pdu/{pdu}/port/{port}/metrics', self.handle_port_get_metrics),
        ])
        self.apprunner = None

    async def start(self):
        logger.info("Starting the HTTP server")
        self.apprunner = web.AppRunner(self.app)
        await self.apprunner.setup()
        listen_host = self.settings["hostname"]
        listen_port = self.settings.get("port", 16421)
        site = web.TCPSite(self.apprunner, host=listen_host, port=listen_port)
        await site.start()
        logger.info("Listening on %s:%s", listen_host, listen_port)

    async def shutdown(self):
        if self.apprunner:
            await self.apprunner.cleanup()
        self.apprunner = None

    async def handle_port_get(self, request: web.Request):
        logger.info("Handling HTTP GET request from %s: %s", request.remote, request.path_qs)
        pdu = request.match_info.get('pdu')
        port = request.match_info.get('port')

        if pdu is None or port is None:
            return web.Response(status=400, text="Missing required parameters\n")

        job = PDURunnerJob(PDURunnerJobType.GetState, pdu, int(port))
        runner = self.daemon.runners[pdu]
        res = await runner.do_job_async(job)
        if res is not None:
            return web.json_response(res.data, status=200)
        else:
            return web.Response(status=500, text="Invalid request\n")

    async def handle_port_put(self, request: web.Request):
        logger.info("Handling HTTP PUT request from %s: %s", request.remote, request.path_qs)
        pdu = request.match_info.get('pdu')
        port = request.match_info.get('port')
        data = await request.json()

        if pdu is None or port is None or data is None:
            return web.Response(status=400, text="Missing required parameters\n")

        job = PDURunnerJob(PDURunnerJobType.SetState, pdu, int(port), data)
        runner = self.daemon.runners[pdu]
        res = await runner.do_job_async(job)
        if res:
            return web.Response(status=200, text="OK - accepted request\n")
        else:
            return web.Response(status=500, text="Invalid request\n")

    async def handle_port_post_action(self, request: web.Request):
        logger.info("Handling HTTP POST request from %s: %s", request.remote, request.path_qs)
        pdu = request.match_info.get('pdu')
        port = request.match_info.get('port')
        action = request.match_info.get('action')
        data = await request.json()

        if pdu is None or port is None or data is None:
            return web.Response(status=400, text="Missing required parameters\n")

        job = PDURunnerJob(PDURunnerJobType.PerformAction, pdu, int(port), { "action": action } | data)
        runner = self.daemon.runners[pdu] # type: PDURunner
        res = await runner.do_job_async(job) # type: PDURunnerResult
        if res.ok:
            return web.Response(status=200, text="OK - accepted request\n")
        else:
            match res.error:
                case PDURunnerErrorKind.NotSupported:
                    return web.Response(status=400, text="Action not supported\n")
            return web.Response(status=500, text="Invalid request\n")

    async def handle_port_get_metrics(self, request: web.Request):
        logger.info("Handling HTTP GET request from %s: %s", request.remote, request.path_qs)
        pdu = request.match_info.get('pdu')
        port = request.match_info.get('port')

        if pdu is None or port is None:
            return web.Response(status=400, text="Missing required parameters\n")

        job = PDURunnerJob(PDURunnerJobType.GetMetrics, pdu, int(port))
        runner = self.daemon.runners[pdu]
        res = await runner.do_job_async(job)
        if res is not None:
            return web.json_response(res.data, status=200)
        else:
            return web.Response(status=500, text="Invalid request\n")
