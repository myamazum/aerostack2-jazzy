"""Service handler."""

# Copyright 2022 Universidad Politécnica de Madrid
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
#    * Neither the name of the the copyright holder nor the names of its
#      contributors may be used to endorse or promote products derived from
#      this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


__authors__ = 'Miguel Fernández Cortizas, Pedro Arias Pérez, David Pérez Saura, Rafael Pérez Seguí'
__copyright__ = 'Copyright (c) 2022 Universidad Politécnica de Madrid'
__license__ = 'BSD-3-Clause'

from time import monotonic, sleep
import typing

from rclpy.client import Client
from std_srvs.srv import SetBool

if typing.TYPE_CHECKING:
    from ..drone_interface_base import DroneInterfaceBase


class ServiceHandler:
    """Service handler class with bounded availability and response waits."""

    TIMEOUT = 3.0  # seconds
    POLL_PERIOD = 0.01  # seconds

    class ServiceNotAvailable(RuntimeError):
        """Service did not become available before the availability timeout."""

    class ServiceCallTimeout(TimeoutError):
        """Service request did not receive a response before the response timeout."""

    def __init__(self, service_client: Client, logger) -> None:
        self._service_client = service_client
        self._logger = logger

        if not service_client.wait_for_service(timeout_sec=self.TIMEOUT):
            message = f'{service_client.srv_name} not available after {self.TIMEOUT:.1f} s'
            logger.error(message)
            raise self.ServiceNotAvailable(message)

    @classmethod
    def _wait_for_future(cls, future, timeout_sec: float) -> bool:
        """Wait for a future without depending on a ROS-distribution-specific Client.call API."""
        deadline = monotonic() + timeout_sec
        while not future.done():
            remaining = deadline - monotonic()
            if remaining <= 0.0:
                return False
            sleep(min(cls.POLL_PERIOD, remaining))
        return True

    def __call__(self, request_msg):
        """Call the service and fail explicitly on availability or response timeout."""
        if not self._service_client.service_is_ready():
            if not self._service_client.wait_for_service(timeout_sec=self.TIMEOUT):
                message = (
                    f'{self._service_client.srv_name} not available after '
                    f'{self.TIMEOUT:.1f} s'
                )
                self._logger.error(message)
                raise self.ServiceNotAvailable(message)

        future = self._service_client.call_async(request_msg)
        if not self._wait_for_future(future, self.TIMEOUT):
            # remove_pending_request() exists in both Humble and Jazzy.  Explicitly
            # removing the request prevents a permanently pending client entry.
            self._service_client.remove_pending_request(future)
            future.cancel()
            message = (
                f'{self._service_client.srv_name} response timed out after '
                f'{self.TIMEOUT:.1f} s'
            )
            self._logger.error(message)
            raise self.ServiceCallTimeout(message)

        exception = future.exception()
        if exception is not None:
            raise exception
        return future.result()


class ServiceBoolHandler(ServiceHandler):
    """Service SetBool handler class."""

    TIMEOUT = 3.0  # seconds

    def __init__(self, drone: 'DroneInterfaceBase', service_name: str) -> None:
        self._logger = drone.get_logger()
        try:
            self._service_client = drone.create_client(
                SetBool, service_name)
        except Exception as ex:
            self._logger.error(f'Could not create client for {service_name}')
            raise ex

        return super().__init__(self._service_client, self._logger)

    def __call__(self, value: bool = True) -> bool:
        """Call the service."""
        request = SetBool.Request()
        request.data = value
        response = super().__call__(request)
        if not response.success:
            self._logger.error('Service returned failure')
        return response.success
