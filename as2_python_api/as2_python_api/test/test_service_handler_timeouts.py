# SPDX-License-Identifier: BSD-3-Clause
"""Unit tests for bounded service waits in ServiceHandler."""

import unittest
from unittest.mock import MagicMock

from as2_python_api.service_clients.service_handler import ServiceHandler


class FakeFuture:
    """Minimal future used to test timeout behavior without a ROS executor."""

    def __init__(self, result=None, done=True):
        self._result = result
        self._done = done
        self.cancel_called = False

    def done(self):
        return self._done

    def exception(self):
        return None

    def result(self):
        return self._result

    def cancel(self):
        self.cancel_called = True
        self._done = True
        return True


class TestServiceHandlerTimeouts(unittest.TestCase):
    """ServiceHandler must never silently continue after endpoint/response timeout."""

    def setUp(self):
        self.client = MagicMock()
        self.client.srv_name = '/drone0/platform/arm'
        self.client.wait_for_service.return_value = True
        self.client.service_is_ready.return_value = True
        self.logger = MagicMock()

    def test_constructor_raises_when_service_is_unavailable(self):
        self.client.wait_for_service.return_value = False

        with self.assertRaises(ServiceHandler.ServiceNotAvailable):
            ServiceHandler(self.client, self.logger)

    def test_async_response_is_returned(self):
        response = object()
        self.client.call_async.return_value = FakeFuture(result=response)
        handler = ServiceHandler(self.client, self.logger)

        self.assertIs(handler(object()), response)
        self.client.call_async.assert_called_once()

    def test_pending_request_is_removed_on_response_timeout(self):
        future = FakeFuture(done=False)
        self.client.call_async.return_value = future
        handler = ServiceHandler(self.client, self.logger)
        handler.TIMEOUT = 0.01
        handler.POLL_PERIOD = 0.001

        with self.assertRaises(ServiceHandler.ServiceCallTimeout):
            handler(object())

        self.client.remove_pending_request.assert_called_once_with(future)
        self.assertTrue(future.cancel_called)

    def test_call_rechecks_service_availability(self):
        handler = ServiceHandler(self.client, self.logger)
        self.client.service_is_ready.return_value = False
        self.client.wait_for_service.return_value = False
        handler.TIMEOUT = 0.01

        with self.assertRaises(ServiceHandler.ServiceNotAvailable):
            handler(object())


if __name__ == '__main__':
    unittest.main()
