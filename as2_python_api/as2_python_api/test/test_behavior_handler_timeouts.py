# SPDX-License-Identifier: BSD-3-Clause
"""Unit tests for BehaviorHandler communication-failure handling."""

import unittest
from unittest.mock import MagicMock, patch

from action_msgs.msg import GoalStatus
from as2_msgs.msg import BehaviorStatus

from as2_python_api.behavior_actions.behavior_handler import BehaviorHandler


class FakeFuture:
    """Small controllable future compatible with the subset used by BehaviorHandler."""

    def __init__(self, result=None, done=True):
        self._result = result
        self._done = done
        self._callbacks = []
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

    def add_done_callback(self, callback):
        self._callbacks.append(callback)
        if self._done:
            callback(self)

    def complete(self, result=None):
        self._result = result
        self._done = True
        for callback in list(self._callbacks):
            callback(self)


class FakeSendGoalService:
    class Request:
        def __init__(self):
            self.goal = None


class FakeGoalHandle:
    def __init__(self, accepted=True, result_future=None):
        self.accepted = accepted
        self.result_future = result_future or FakeFuture()
        self.cancel_future = FakeFuture(result=object())
        self.cancel_calls = 0
        self.result_calls = 0

    def get_result_async(self):
        self.result_calls += 1
        return self.result_future

    def cancel_goal_async(self):
        self.cancel_calls += 1
        return self.cancel_future


class FakeActionClient:
    def __init__(self):
        self.available = True
        self.send_goal_future = FakeFuture(result=FakeGoalHandle())
        self.destroy_called = False

    def wait_for_server(self, timeout_sec=None):
        del timeout_sec
        return self.available

    def send_goal_async(self, goal_msg, feedback_callback=None):
        del goal_msg, feedback_callback
        return self.send_goal_future

    def destroy(self):
        self.destroy_called = True


class TestBehaviorHandlerTimeouts(unittest.TestCase):
    def setUp(self):
        self.node = MagicMock()
        self.node.get_logger.return_value = MagicMock()

        self.pause_client = MagicMock()
        self.resume_client = MagicMock()
        self.stop_client = MagicMock()
        self.modify_client = MagicMock()
        self.clients = [
            self.pause_client,
            self.resume_client,
            self.stop_client,
            self.modify_client,
        ]
        for client in self.clients:
            client.wait_for_service.return_value = True
            client.service_is_ready.return_value = True

        self.node.create_client.side_effect = self.clients
        self.node.create_subscription.return_value = object()
        self.action_client = FakeActionClient()

        action_patch = patch(
            'as2_python_api.behavior_actions.behavior_handler.ActionClient',
            return_value=self.action_client,
        )
        sendgoal_patch = patch(
            'as2_python_api.behavior_actions.behavior_handler.get_sendgoal_action_msg',
            return_value=FakeSendGoalService,
        )
        self.addCleanup(action_patch.stop)
        self.addCleanup(sendgoal_patch.stop)
        action_patch.start()
        sendgoal_patch.start()

        self.handler = BehaviorHandler(self.node, object, 'TestBehavior')
        self.handler.GOAL_RESPONSE_TIMEOUT = 0.02
        self.handler.SERVICE_RESPONSE_TIMEOUT = 0.02
        self.handler.STATUS_LIVENESS_TIMEOUT = 0.03
        self.handler.RESULT_RESPONSE_TIMEOUT = 0.02
        self.handler.POLL_PERIOD = 0.001

    def test_goal_acknowledgement_timeout_is_bounded(self):
        pending = FakeFuture(done=False)
        self.action_client.send_goal_future = pending

        with self.assertRaises(BehaviorHandler.GoalResponseTimeout):
            self.handler.start(object(), wait_result=False)

    def test_late_accepted_goal_is_cancelled(self):
        pending = FakeFuture(done=False)
        self.action_client.send_goal_future = pending

        with self.assertRaises(BehaviorHandler.GoalResponseTimeout):
            self.handler.start(object(), wait_result=False)

        late_goal = FakeGoalHandle(accepted=True)
        pending.complete(late_goal)
        self.assertEqual(late_goal.cancel_calls, 1)
        self.assertEqual(late_goal.result_calls, 1)

    def test_behavior_status_loss_breaks_result_wait(self):
        result_future = FakeFuture(done=False)
        goal_handle = FakeGoalHandle(result_future=result_future)
        self.action_client.send_goal_future = FakeFuture(result=goal_handle)

        with self.assertRaises(BehaviorHandler.BehaviorCommunicationLost):
            self.handler.start(object(), wait_result=True)

        self.assertTrue(result_future.cancel_called)

    def test_idle_without_action_result_times_out(self):
        result_future = FakeFuture(done=False)
        goal_handle = FakeGoalHandle(result_future=result_future)
        self.action_client.send_goal_future = FakeFuture(result=goal_handle)
        self.handler.STATUS_LIVENESS_TIMEOUT = 1.0

        self.assertTrue(self.handler.start(object(), wait_result=False))
        status = MagicMock()
        status.status = BehaviorStatus.IDLE
        self.handler._BehaviorHandler__status_callback(status)

        with self.assertRaises(BehaviorHandler.ResultResponseTimeout):
            self.handler.wait_to_result()

        self.assertTrue(result_future.cancel_called)

    def test_modify_service_response_timeout_is_bounded(self):
        pending = FakeFuture(done=False)
        self.modify_client.call_async.return_value = pending

        with self.assertRaises(BehaviorHandler.ServiceResponseTimeout):
            self.handler.modify(object())

        self.modify_client.remove_pending_request.assert_called_once_with(pending)
        self.assertTrue(pending.cancel_called)

    def test_successful_result_is_unchanged(self):
        result = MagicMock()
        result.status = GoalStatus.STATUS_SUCCEEDED
        result.result = object()
        goal_handle = FakeGoalHandle(result_future=FakeFuture(result=result))
        self.action_client.send_goal_future = FakeFuture(result=goal_handle)

        self.assertTrue(self.handler.start(object(), wait_result=True))

    def test_destroy_releases_all_behavior_clients(self):
        self.handler.destroy()

        destroyed = [call.args[0] for call in self.node.destroy_client.call_args_list]
        self.assertCountEqual(destroyed, self.clients)
        self.assertTrue(self.action_client.destroy_called)


if __name__ == '__main__':
    unittest.main()
