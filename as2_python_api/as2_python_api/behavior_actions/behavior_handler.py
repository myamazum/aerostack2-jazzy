"""Behavior handler. Abstract class to handle behaviors."""

# Copyright 2025 Universidad Politécnica de Madrid
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

__authors__ = (
    'Miguel Fernández Cortizas, Pedro Arias Pérez, David Pérez Saura, Rafael Pérez Seguí,'
    ' Guillermo GP-Lenza'
)
__copyright__ = 'Copyright (c) 2022 Universidad Politécnica de Madrid'
__license__ = 'BSD-3-Clause'

import abc
from time import monotonic, sleep

from action_msgs.msg import GoalStatus
from as2_msgs.msg import BehaviorStatus
from as2_python_api.tools.utils import get_sendgoal_action_msg
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_srvs.srv import Trigger


class BehaviorHandler(abc.ABC):
    """Behavior handler with bounded protocol waits and server-liveness monitoring."""

    TIMEOUT = 1.0  # endpoint availability timeout, seconds
    GOAL_RESPONSE_TIMEOUT = 3.0  # send-goal acknowledgement timeout, seconds
    SERVICE_RESPONSE_TIMEOUT = 3.0  # pause/resume/stop/modify response timeout, seconds
    STATUS_LIVENESS_TIMEOUT = 3.0  # maximum time without status or feedback, seconds
    RESULT_RESPONSE_TIMEOUT = 3.0  # result grace period after behavior becomes IDLE, seconds
    POLL_PERIOD = 0.05  # future/liveness polling period, seconds

    class BehaviorNotAvailable(Exception):
        """Behavior not available exception."""

    class GoalRejected(Exception):
        """Goal rejected exception."""

    class GoalResponseTimeout(TimeoutError):
        """Action server did not acknowledge the goal in time."""

    class ServiceResponseTimeout(TimeoutError):
        """Behavior control service did not respond in time."""

    class BehaviorCommunicationLost(TimeoutError):
        """Behavior server stopped publishing status/feedback while a goal was active."""

    class ResultResponseTimeout(TimeoutError):
        """Behavior became idle but the action result did not arrive in time."""

    class ResultUnknown(Exception):
        """Result unknown exception."""

    def __init__(self, node: 'Node', action_msg, behavior_name) -> None:
        self._node = node
        self.__behavior_name = behavior_name
        self.__status = BehaviorStatus.IDLE
        self.__feedback = None
        self.__result = None
        self.__goal_handle = None
        self.__last_server_activity = monotonic()

        self.__action_client = ActionClient(node, action_msg, behavior_name)

        self.__pause_client = self._node.create_client(Trigger, behavior_name + '/_behavior/pause')
        self.__resume_client = self._node.create_client(
            Trigger, behavior_name + '/_behavior/resume'
        )
        self.__stop_client = self._node.create_client(Trigger, behavior_name + '/_behavior/stop')

        self.__send_goal_msg_t = get_sendgoal_action_msg(action_msg)
        self.__modify_client = self._node.create_client(
            self.__send_goal_msg_t, behavior_name + '/_behavior/modify'
        )

        self.__status_sub = self._node.create_subscription(
            BehaviorStatus,
            behavior_name + '/_behavior/behavior_status',
            self.__status_callback,
            QoSProfile(depth=1),
        )

        # Keep the existing construction-time check, but every operation also
        # re-checks its endpoint because connectivity may change afterwards.
        if (
            not self.__action_client.wait_for_server(timeout_sec=self.TIMEOUT)
            or not self.__pause_client.wait_for_service(timeout_sec=self.TIMEOUT)
            or not self.__resume_client.wait_for_service(timeout_sec=self.TIMEOUT)
            or not self.__stop_client.wait_for_service(timeout_sec=self.TIMEOUT)
            or not self.__modify_client.wait_for_service(timeout_sec=self.TIMEOUT)
        ):
            raise self.BehaviorNotAvailable(f'{behavior_name} Not Available')

    def destroy(self) -> None:
        """Clean exit."""
        self._node.destroy_subscription(self.__status_sub)
        self._node.destroy_client(self.__resume_client)
        self._node.destroy_client(self.__pause_client)
        self._node.destroy_client(self.__stop_client)
        self._node.destroy_client(self.__modify_client)
        self.__action_client.destroy()

    @property
    def status(self) -> int:
        """
        Behavior internal status.

        :return: IDLE, PAUSED, RUNNING
        :rtype: int
        """
        return self.__status

    @property
    def feedback(self):
        """
        Behavior feedback.

        :return: rclpy.Feedback
        """
        return self.__feedback

    @property
    def result_status(self):
        """
        Behavior result status.

        :raises self.ResultUnknown: on result not ready
        :return: rclpy.GoalStatus
        """
        if self.__result is None:
            raise self.ResultUnknown('Result not received yet')
        return self.__result.status

    @property
    def result(self):
        """
        Behavior result.

        :raises self.ResultUnknown: on result not ready
        :return: rclpy.Result
        """
        if self.result_status not in [GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_CANCELED]:
            raise self.ResultUnknown('Result not received yet')
        return self.__result.result

    def is_running(self) -> bool:
        """
        Check if behavior is running.

        :return: running or not
        """
        return self.__status == BehaviorStatus.RUNNING

    @classmethod
    def __wait_for_future(cls, future, timeout_sec: float) -> bool:
        deadline = monotonic() + timeout_sec
        while not future.done():
            remaining = deadline - monotonic()
            if remaining <= 0.0:
                return False
            sleep(min(cls.POLL_PERIOD, remaining))
        return True

    @staticmethod
    def __discard_service_future(client, future) -> None:
        client.remove_pending_request(future)
        future.cancel()

    def __ensure_action_available(self) -> None:
        if not self.__action_client.wait_for_server(timeout_sec=self.TIMEOUT):
            raise self.BehaviorNotAvailable(
                f'{self.__behavior_name} action server not available'
            )

    def __call_service(self, client, request, operation: str):
        if not client.wait_for_service(timeout_sec=self.TIMEOUT):
            raise self.BehaviorNotAvailable(
                f'{self.__behavior_name} {operation} service not available'
            )

        future = client.call_async(request)
        if not self.__wait_for_future(future, self.SERVICE_RESPONSE_TIMEOUT):
            self.__discard_service_future(client, future)
            raise self.ServiceResponseTimeout(
                f'{self.__behavior_name} {operation} response timed out after '
                f'{self.SERVICE_RESPONSE_TIMEOUT:.1f} s'
            )

        exception = future.exception()
        if exception is not None:
            raise exception
        return future.result()

    def start(self, goal_msg, wait_result: bool = True) -> bool:
        """
        Start behavior.

        :param goal_msg: behavior goal
        :type goal_msg: Goal
        :param wait_result: wait to behavior end, defaults to True
        :type wait_result: bool, optional
        :raises self.BehaviorNotAvailable: when the action server is unavailable
        :raises self.GoalResponseTimeout: when goal acknowledgement times out
        :raises self.GoalRejected: on goal rejection
        :return: succeeded or not
        :rtype: bool
        """
        self.__ensure_action_available()

        send_goal_future = self.__action_client.send_goal_async(
            goal_msg, feedback_callback=self.__feedback_callback
        )

        if not self.__wait_for_future(send_goal_future, self.GOAL_RESPONSE_TIMEOUT):
            # The goal request may have reached the server although its response was
            # lost or delayed.  Do not cancel the local Future: keeping it alive lets
            # us cancel a goal that is accepted after this method has already failed.
            send_goal_future.add_done_callback(self.__cancel_late_goal)
            raise self.GoalResponseTimeout(
                f'{self.__behavior_name} goal response timed out after '
                f'{self.GOAL_RESPONSE_TIMEOUT:.1f} s; goal state is being reconciled'
            )

        exception = send_goal_future.exception()
        if exception is not None:
            raise exception

        self.__goal_handle = send_goal_future.result()
        if self.__goal_handle is None or not self.__goal_handle.accepted:
            raise self.GoalRejected('Goal Rejected')

        self.__status = BehaviorStatus.RUNNING
        self.__last_server_activity = monotonic()

        if wait_result:
            return self.wait_to_result()

        return True

    def modify(self, goal_msg) -> bool:
        """
        Modify current behavior.

        :param goal_msg: behavior goal
        :type goal_msg: Goal
        """
        goal_req = self.__send_goal_msg_t.Request()
        goal_req.goal = goal_msg
        response = self.__call_service(self.__modify_client, goal_req, 'modify')
        return response.accepted

    def pause(self) -> bool:
        """
        Pause current behavior.

        :return: pause succeed or not
        :rtype: bool
        """
        if self.status != BehaviorStatus.RUNNING:
            return True
        response = self.__call_service(self.__pause_client, Trigger.Request(), 'pause')
        if response.success:
            self.__status = BehaviorStatus.PAUSED
        return response.success

    def resume(self, wait_result: bool = True) -> bool:
        """
        Continue with current behavior.

        :param wait_result: wait to behavior end, defaults to True
        :type wait_result: bool, optional
        :return: resume succeed or not
        :rtype: bool
        """
        if self.status != BehaviorStatus.PAUSED:
            return True
        response = self.__call_service(self.__resume_client, Trigger.Request(), 'resume')
        if response.success:
            self.__status = BehaviorStatus.RUNNING
            self.__last_server_activity = monotonic()
        if wait_result and response.success:
            return self.wait_to_result()
        return response.success

    def stop(self) -> bool:
        """
        Stop current behavior.

        :return: stop succeed or not
        :rtype: bool
        """
        if self.status == BehaviorStatus.IDLE:
            return True
        response = self.__call_service(self.__stop_client, Trigger.Request(), 'stop')
        if response.success:
            self.__status = BehaviorStatus.IDLE
        return response.success

    def wait_to_result(self) -> bool:
        """
        Wait for the current action result while monitoring BehaviorServer liveness.

        A long-running behavior is allowed to run indefinitely as long as status or
        feedback continues to arrive.  This avoids imposing an arbitrary flight-duration
        limit while still detecting a communication failure.

        :raises self.ResultUnknown: if no accepted goal exists
        :raises self.BehaviorCommunicationLost: if status/feedback stops arriving
        :raises self.ResultResponseTimeout: if the behavior becomes IDLE without a result
        :return: whether the action succeeded
        :rtype: bool
        """
        if self.__goal_handle is None:
            raise self.ResultUnknown('No accepted goal')

        result_future = self.__goal_handle.get_result_async()
        idle_since = None

        while not result_future.done():
            now = monotonic()

            if now - self.__last_server_activity > self.STATUS_LIVENESS_TIMEOUT:
                result_future.cancel()
                raise self.BehaviorCommunicationLost(
                    f'{self.__behavior_name} produced no status or feedback for '
                    f'{self.STATUS_LIVENESS_TIMEOUT:.1f} s'
                )

            if self.__status == BehaviorStatus.IDLE:
                if idle_since is None:
                    idle_since = now
                elif now - idle_since > self.RESULT_RESPONSE_TIMEOUT:
                    result_future.cancel()
                    raise self.ResultResponseTimeout(
                        f'{self.__behavior_name} became IDLE but no action result arrived '
                        f'within {self.RESULT_RESPONSE_TIMEOUT:.1f} s'
                    )
            else:
                idle_since = None

            sleep(self.POLL_PERIOD)

        exception = result_future.exception()
        if exception is not None:
            raise exception
        self.__result = result_future.result()

        if self.result_status != GoalStatus.STATUS_SUCCEEDED:
            self._node.get_logger().debug(f'Goal failed with status code: {self.result_status}')
            return False
        self._node.get_logger().debug(f'Result: {self.result}')
        return True

    def __cancel_late_goal(self, send_goal_future) -> None:
        """Cancel a goal that was accepted after the local acknowledgement timeout."""
        try:
            exception = send_goal_future.exception()
            if exception is not None:
                self._node.get_logger().error(
                    f'Late goal response failed for {self.__behavior_name}: {exception}'
                )
                return

            goal_handle = send_goal_future.result()
            if goal_handle is None or not goal_handle.accepted:
                return

            self._node.get_logger().warning(
                f'{self.__behavior_name} accepted a goal after the response timeout; '
                'requesting cancellation'
            )
            goal_handle.cancel_goal_async()

            # Ask for the terminal result as well.  Besides observing the terminal
            # state, this allows rclpy to retire action bookkeeping and feedback state.
            goal_handle.get_result_async()
        except Exception as exception:  # best-effort reconciliation path
            self._node.get_logger().error(
                f'Could not reconcile late goal for {self.__behavior_name}: {exception}'
            )

    def __feedback_callback(self, feedback_msg) -> None:
        """Feedback callback."""
        self.__feedback = feedback_msg.feedback
        self.__last_server_activity = monotonic()
        self._node.get_logger().debug(f'Received feedback: {feedback_msg.feedback}')

    def __status_callback(self, status_msg: BehaviorStatus) -> None:
        """Behavior status callback."""
        self.__status = status_msg.status
        self.__last_server_activity = monotonic()
