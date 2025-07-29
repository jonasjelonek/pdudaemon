#!/usr/bin/python3

#  Copyright 2013 Linaro Limited
#  Author Matt Hart <matthew.hart@linaro.org>
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

import asyncio
from enum import Enum
import logging
import time
import traceback
import pexpect
import concurrent.futures
from pdudaemon.drivers.driver import PDUDriver, PDUDriverException
import pdudaemon.drivers.strategies

assert pdudaemon.drivers.strategies, "Subclasses are iterated to find all drivers"

class PDURunnerJobType(int, Enum):
    GetState = 1
    SetState = 2
    PerformAction = 3
    GetMetrics = 4

class PDURunnerJob:
    def __init__(self, type: PDURunnerJobType, pdu: str, port: int, data: dict = {}):
        self.type = type
        self.pdu = pdu
        self.port = port
        self.data = data

class PDURunnerErrorKind(int, Enum):
    NotSupported = 1
    Timeout = 2
    UnknownError = 3

class PDURunnerResult:
    def __init__(self, ok: bool, data: dict | None, error: PDURunnerErrorKind | None, error_msg: str | None):
        self.ok = ok
        self.data = data
        self.error = error
        self.error_msg = error_msg

class PDURunner:
    def __init__(self, config, pdu_name, retries):
        self.config = config
        self.pdu_name = pdu_name # type: str
        self.retries = retries # type: int
        self.logger = logging.getLogger("pdud.pdu.%s" % pdu_name)
        self.driver = self.get_driver(pdu_name)
        # use single-worker ThreadPoolExecutor to serialize execution
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=pdu_name)

    async def shutdown(self):
        self.executor.shutdown(wait=True, cancel_futures=True)

    def get_driver(self, pdu_name) -> PDUDriver:
        drivername = self.config['driver']
        driver = PDUDriver.select(drivername)(pdu_name, self.config)
        return driver

    def _map_job_to_driver(self, job: PDURunnerJob) -> PDURunnerResult:
        match job.type:
            case PDURunnerJobType.GetState:
                res = self.driver.port_get(job.port)
                return PDURunnerResult(True, { "state": "on" if res else "off" }, None, None)
            case PDURunnerJobType.SetState:
                if not job.data["state"] or job.data["state"] not in [ "on", "off" ]:
                    raise ValueError("Invalid state")

                self.driver.port_set(job.port, job.data["state"] == "on")
                return PDURunnerResult(True, None, None, None)
            case PDURunnerJobType.PerformAction:
                if not job.data["action"]:
                    raise ValueError("Missing action")

                self.driver.port_action(job.port, job.data["action"])
                return PDURunnerResult(True, None, None, None)
            case PDURunnerJobType.GetMetrics:
                metrics = self.driver.port_get_metrics(job.port)
                return PDURunnerResult(True, metrics, None, None)

    def do_job(self, job: PDURunnerJob) -> PDURunnerResult:
        self.logger.info("Processing job for PDU %s: (%s port %s)", self.pdu_name, job.type, job.port)
        retries = self.retries
        while retries > 0:
            try:
                return self._map_job_to_driver(job)
            except NotImplementedError as e:
                return PDURunnerResult(False, None, PDURunnerErrorKind.NotSupported, str(e))
            except (OSError, pexpect.exceptions.EOF, Exception):  # pylint: disable=broad-except
                self.logger.warning(traceback.format_exc())
                self.logger.warning("Failed to execute job: {} {} (attempts left {})".format(job.port, job.type, retries - 1))
                if self.driver:
                    self.driver._bombout()  # pylint: disable=W0212,E1101
                time.sleep(5)
                retries -= 1
                continue

        return PDURunnerResult(False, None, PDURunnerErrorKind.Timeout, None)

    async def do_job_async(self, job) -> PDURunnerResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.do_job, job)
