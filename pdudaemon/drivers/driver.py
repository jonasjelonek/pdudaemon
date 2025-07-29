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

import logging
import os
log = logging.getLogger("pdud.drivers")


def get_named_entry_point(group, name):
    import importlib.metadata
    eps = [
        ep for ep in importlib.metadata.entry_points().select(group=group)
        if ep.name == name
    ]
    if len(eps) > 1:
        raise Exception('Multiple entry points for {} under {}'.format(group, name))
    if len(eps) == 0:
        return None
    return eps[0]

class PDUDriver(object):
    connection = None

    def __init__(self):
        super(PDUDriver, self).__init__()

    @classmethod
    def select(cls, drivername):
        ep = get_named_entry_point('pdudaemon.driver', drivername)
        if ep:
            # Not clear why a driver would reject the driver
            # it is registered for but check anyway:
            c = ep.load()
            if not c.accepts(drivername):
                raise Exception('pdudaemon.driver entry_point {} did not accept configuration'.format(c))
            return c
        candidates = cls.__subclasses__()  # pylint: disable=no-member
        for subc in cls.__subclasses__():  # pylint: disable=no-member
            candidates = candidates + (subc.__subclasses__())
            for subsubc in subc.__subclasses__():
                candidates = candidates + (subsubc.__subclasses__())
        willing = [c for c in candidates if c.accepts(drivername)]
        if len(willing) == 0:
            log.error("No driver accepted the configuration '%s'", drivername)
            os._exit(1)
        log.debug("%s accepted the request", willing[0])
        return willing[0]

    def port_get(self, port_number: int) -> bool:
        raise NotImplementedError("Driver does not support port_get")

    def port_set(self, port_number: int, state: bool):
        raise NotImplementedError("Driver does not support port_set")

    def port_action(self, port_number: int, action: str):
        raise NotImplementedError("Driver does not support port_action")

    def port_get_metrics(self, port_number: int) -> dict:
        raise NotImplementedError("Driver does not support port_get_metrics")

    def _bombout(self):
        pass

    def _cleanup(self):
        pass


class PDUDriverException(Exception):
    pass

class UnknownCommandException(PDUDriverException):
    pass

class FailedRequestException(PDUDriverException):
    pass
