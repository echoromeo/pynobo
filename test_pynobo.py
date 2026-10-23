import asyncio
import errno
import pathlib
import unittest
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

from pynobo import (
    PynoboConnectionError,
    PynoboError,
    PynoboHandshakeError,
    PynoboValidationError,
    nobo,
)

class TestValidation(unittest.TestCase):

    def test_is_valid_datetime(self):
        self.assertTrue(nobo.API.is_valid_datetime("202404041800"))
        self.assertFalse(nobo.API.is_valid_datetime("2024040418001"))
        self.assertFalse(nobo.API.is_valid_datetime("20240404180"))
        self.assertFalse(nobo.API.is_valid_datetime("invalid"))

    def test_time_is_quarter(self):
        self.assertTrue(nobo.API.time_is_quarter("00"))
        self.assertTrue(nobo.API.time_is_quarter("15"))
        self.assertTrue(nobo.API.time_is_quarter("30"))
        self.assertTrue(nobo.API.time_is_quarter("45"))
        self.assertFalse(nobo.API.time_is_quarter("01"))
        self.assertFalse(nobo.API.time_is_quarter("59"))

    def test_validate_temperature(self):
        nobo.API.validate_temperature("20")
        nobo.API.validate_temperature(20)
        nobo.API.validate_temperature(7)
        nobo.API.validate_temperature(30)
        with self.assertRaises(TypeError):
            nobo.API.validate_temperature(0.0)
        with self.assertRaisesRegex(ValueError, "must be digits"):
            nobo.API.validate_temperature("foo")
        with self.assertRaisesRegex(ValueError, "Min temperature is 7"):
            nobo.API.validate_temperature(6)
        with self.assertRaisesRegex(ValueError, "Max temperature is 30"):
            nobo.API.validate_temperature(31)

    def test_validate_week_profile(self):
        nobo.API.validate_week_profile(['00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000','00000','12001','16000'])
        nobo.API.validate_week_profile(['00000','00000','00000','00000','00000','00000','00000'])
        nobo.API.validate_week_profile(['00000','00001','00002','00004','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "must contain exactly 7 entries for midnight"):
            nobo.API.validate_week_profile(['00000','00000','00000','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "must contain exactly 7 entries for midnight"):
            nobo.API.validate_week_profile(['00000','00000','00000','00000','00000','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "invalid state"):
            nobo.API.validate_week_profile(['00003','00000','00000','00000','00000','00000','00000'])
        with self.assertRaisesRegex(ValueError, "not in whole quarters"):
            nobo.API.validate_week_profile(['00000','01231','00000','00000','00000','00000','00000','00000'])


class TestExceptionHierarchy(unittest.TestCase):

    def test_validation_error_raised_and_inherits_value_error(self):
        with self.assertRaises(PynoboValidationError):
            nobo.API.validate_temperature(6)
        # back-compat: callers catching ValueError still work
        with self.assertRaises(ValueError):
            nobo.API.validate_temperature(6)

    def test_validation_error_raised_for_type_check(self):
        with self.assertRaises(PynoboValidationError):
            nobo.API.validate_temperature(0.0)
        # back-compat: callers catching TypeError still work
        with self.assertRaises(TypeError):
            nobo.API.validate_temperature(0.0)

    def test_all_errors_inherit_base(self):
        self.assertTrue(issubclass(PynoboConnectionError, PynoboError))
        self.assertTrue(issubclass(PynoboHandshakeError, PynoboError))
        self.assertTrue(issubclass(PynoboValidationError, PynoboError))
        self.assertTrue(issubclass(PynoboValidationError, ValueError))
        self.assertTrue(issubclass(PynoboValidationError, TypeError))


class TestPyTypedMarker(unittest.TestCase):

    def test_py_typed_file_is_present_in_source(self):
        marker = pathlib.Path(__file__).parent / "pynobo" / "py.typed"
        self.assertTrue(marker.is_file(), f"{marker} is missing")


class TestConnectionStateAPI(unittest.TestCase):

    def _make_hub(self):
        return nobo('123', discover=False, synchronous=False)

    def test_initial_state_is_disconnected(self):
        hub = self._make_hub()
        events = []
        hub.register_connection_callback(lambda h, s: events.append(s))
        self.assertFalse(hub.connected)
        self.assertEqual(events, [])

    def test_transition_fires_callback_once(self):
        hub = self._make_hub()
        events = []
        hub.register_connection_callback(lambda h, s: events.append((h is hub, s)))
        hub._set_connected(True)
        self.assertTrue(hub.connected)
        self.assertEqual(events, [(True, True)])

    def test_transitions_are_idempotent(self):
        hub = self._make_hub()
        events = []
        hub.register_connection_callback(lambda h, s: events.append(s))
        hub._set_connected(True)
        hub._set_connected(True)
        hub._set_connected(False)
        hub._set_connected(False)
        self.assertEqual(events, [True, False])

    def test_deregister_stops_callback(self):
        hub = self._make_hub()
        events = []
        cb = lambda h, s: events.append(s)
        hub.register_connection_callback(cb)
        hub._set_connected(True)
        hub.deregister_connection_callback(cb)
        hub._set_connected(False)
        self.assertEqual(events, [True])

    def test_callback_exception_does_not_break_dispatch(self):
        hub = self._make_hub()
        events = []
        def boom(h, s):
            raise RuntimeError("boom")
        hub.register_connection_callback(boom)
        hub.register_connection_callback(lambda h, s: events.append(s))
        hub._set_connected(True)
        self.assertEqual(events, [True])
        self.assertTrue(hub.connected)


class TestSocketReceiveReconnect(unittest.IsolatedAsyncioTestCase):

    def _make_hub(self):
        return nobo('123', discover=False, synchronous=False)

    def _install_fake_transport(self, hub, errors_to_raise):
        """Wire fake reader/writer + spies for reconnect_hub / stop.

        The reader raises each exception in `errors_to_raise` on successive
        readuntil() calls, then hangs so the task stays alive until cancelled.
        Returns (reconnect_calls, stop_calls, reconnect_done_event).
        """
        errors = iter(errors_to_raise)
        hang = asyncio.Event()  # never set

        reader = MagicMock(spec=asyncio.StreamReader)

        async def readuntil(_sep):
            try:
                raise next(errors)
            except StopIteration:
                await hang.wait()
                return b'\r'  # unreachable

        reader.readuntil = readuntil

        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        hub._reader = reader
        hub._writer = writer

        reconnect_calls = []
        reconnect_done = asyncio.Event()

        async def fake_reconnect():
            reconnect_calls.append(True)
            hub._set_connected(True)
            reconnect_done.set()

        hub.reconnect_hub = fake_reconnect

        stop_calls = []

        async def fake_stop():
            stop_calls.append(True)

        hub.stop = fake_stop

        return reconnect_calls, stop_calls, reconnect_done

    async def _run_socket_receive_until_reconnect(self, hub, reconnect_done):
        task = asyncio.create_task(hub.socket_receive())
        try:
            await asyncio.wait_for(reconnect_done.wait(), timeout=1)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def test_reconnect_on_econnreset(self):
        """ConnectionResetError from readuntil must route through reconnect_hub, not stop()."""
        hub = self._make_hub()
        err = ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")
        reconnect_calls, stop_calls, reconnect_done = self._install_fake_transport(hub, [err])

        await self._run_socket_receive_until_reconnect(hub, reconnect_done)

        self.assertEqual(len(reconnect_calls), 1)
        self.assertEqual(stop_calls, [])

    async def test_reconnect_on_oserror_with_reconnect_errno(self):
        """Plain OSError with an errno in RECONNECT_ERRORS must also trigger reconnect."""
        hub = self._make_hub()
        err = OSError(errno.ETIMEDOUT, "Timed out")
        reconnect_calls, stop_calls, reconnect_done = self._install_fake_transport(hub, [err])

        await self._run_socket_receive_until_reconnect(hub, reconnect_done)

        self.assertEqual(len(reconnect_calls), 1)
        self.assertEqual(stop_calls, [])

    async def test_connection_callback_transitions_on_disconnect_reconnect(self):
        """Callback must see True → False → True across a drop and successful reconnect."""
        hub = self._make_hub()
        events = []
        hub.register_connection_callback(lambda _h, state: events.append(state))
        hub._set_connected(True)  # initial connected state

        err = ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")
        _reconnect_calls, _stop_calls, reconnect_done = self._install_fake_transport(hub, [err])

        await self._run_socket_receive_until_reconnect(hub, reconnect_done)

        self.assertEqual(events, [True, False, True])

    async def test_socket_receive_stops_cleanly_on_handshake_error(self):
        """Terminal handshake rejection during reconnect routes to outer arm → stop().

        Complements test_reconnect_hub_propagates_handshake_error: that one verifies
        reconnect_hub lets the exception escape; this one verifies socket_receive's
        outer arm actually catches it, logs cleanly, and exits via stop() instead of
        the misleading "Unhandled exception" catch-all.
        """
        hub = self._make_hub()
        err = ConnectionResetError(errno.ECONNRESET, "Connection reset by peer")
        self._install_fake_transport(hub, [err])
        # Override fake reconnect: this time reconnect itself fails terminally.
        hub.reconnect_hub = AsyncMock(side_effect=PynoboHandshakeError("rejected"))

        stop_calls = []

        async def fake_stop():
            stop_calls.append(True)

        hub.stop = fake_stop

        # socket_receive should exit on its own — no external cancel needed.
        await asyncio.wait_for(hub.socket_receive(), timeout=1)

        self.assertEqual(stop_calls, [True])

    async def test_reconnect_hub_propagates_handshake_error(self):
        """Handshake rejection must escape the retry loop so it surfaces to the outer handler.

        PynoboHandshakeError means the hub is refusing us (bad serial, version mismatch) —
        no amount of retrying will fix that. It should propagate out for socket_receive's
        outer arm to log cleanly and stop.
        """
        hub = self._make_hub()
        call_count = {'n': 0}

        async def fake_connect(_ip, _serial):
            call_count['n'] += 1
            raise PynoboHandshakeError("hub rejected handshake")

        hub.async_connect_hub = fake_connect

        with patch('pynobo.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaises(PynoboHandshakeError):
                await hub.reconnect_hub()

        self.assertEqual(call_count['n'], 1)
        self.assertFalse(hub.connected)

    async def test_reconnect_hub_retries_on_transient_failure(self):
        """reconnect_hub must keep retrying when async_connect_hub raises PynoboConnectionError.

        The pre-fix code caught only OSError, but async_connect_hub wraps OSError from
        open_connection into PynoboConnectionError — so the first failed attempt escaped,
        bounced out of socket_receive as Unhandled exception, and called stop().
        """
        hub = self._make_hub()
        events = []
        hub.register_connection_callback(lambda _h, state: events.append(state))

        call_count = {'n': 0}

        async def fake_connect(_ip, _serial):
            call_count['n'] += 1
            if call_count['n'] < 3:
                raise PynoboConnectionError("transient network failure")
            # Mirror real async_connect_hub: fire the connection callback on
            # success before returning, so reconnect_hub doesn't have to.
            hub._set_connected(True)
            return True

        hub.async_connect_hub = fake_connect

        # Patch sleep so the test doesn't wait through the real backoff (10 + 20 s).
        with patch('pynobo.asyncio.sleep', new_callable=AsyncMock):
            await hub.reconnect_hub()

        self.assertEqual(call_count['n'], 3)
        # Only one transition fires: the final True on success. No intermediate False —
        # reconnect_hub doesn't touch state until it has a good connection.
        self.assertEqual(events, [True])
        self.assertTrue(hub.connected)

    async def test_liveness_deadline_triggers_reconnect_on_silent_drop(self):
        """If no frame arrives within 2× the keep-alive interval, force a reconnect.

        Models the silent-network-drop case: readuntil hangs (packets go nowhere,
        nothing comes back). keep_alive's liveness check should close the writer,
        which unblocks readuntil with EOF → IncompleteReadError → reconnect_hub.
        """
        hub = self._make_hub()
        events = []
        hub.register_connection_callback(lambda _h, state: events.append(state))
        hub._set_connected(True)

        reader = MagicMock(spec=asyncio.StreamReader)
        hang = asyncio.Event()  # released by close() to surface EOF

        async def readuntil(_sep):
            await hang.wait()
            raise asyncio.IncompleteReadError(partial=b'', expected=1)

        reader.readuntil = readuntil

        writer = MagicMock(spec=asyncio.StreamWriter)

        def close_writer():
            # After close, any subsequent readuntil (post-reconnect) must hang
            # forever so the test loop doesn't spin.
            async def hang_forever(_sep):
                await asyncio.Event().wait()
            reader.readuntil = hang_forever
            hang.set()  # wakes the already-pending readuntil, which raises EOF

        writer.close = MagicMock(side_effect=close_writer)
        writer.wait_closed = AsyncMock()
        hub._reader = reader
        hub._writer = writer

        reconnect_done = asyncio.Event()
        reconnect_calls = []

        async def fake_reconnect():
            reconnect_calls.append(True)
            hub._set_connected(True)
            reconnect_done.set()

        hub.reconnect_hub = fake_reconnect
        hub.stop = AsyncMock()

        recv_task = asyncio.create_task(hub.socket_receive())
        keep_task = asyncio.create_task(hub.keep_alive(interval=0.1))
        try:
            await asyncio.wait_for(reconnect_done.wait(), timeout=2)
        finally:
            recv_task.cancel()
            keep_task.cancel()
            with suppress(asyncio.CancelledError):
                await recv_task
            with suppress(asyncio.CancelledError):
                await keep_task

        self.assertEqual(len(reconnect_calls), 1)
        self.assertEqual(events, [True, False, True])

    async def test_connect_fires_connection_callback_before_data_callback(self):
        """async_connect_hub fires the connection callback before the data callback.

        Consumers (notably HA's nobo_hub integration) gate availability on the
        connection callback. Reordering them would re-introduce the race where
        a data callback fires while the consumer still thinks the hub is
        disconnected.
        """
        hub = nobo('123456789012', ip='192.168.1.1', discover=False, synchronous=False)
        order = []
        hub.register_callback(lambda _h: order.append('data'))
        hub.register_connection_callback(lambda _h, _s: order.append('connection'))

        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        # Successful handshake responses, then nothing (handshake-only path).
        responses = iter([
            ['HELLO', nobo.API.VERSION, '123456789012', '20260101000000'],
            ['HANDSHAKE'],
        ])

        async def fake_get_response():
            return next(responses)

        hub.get_response = fake_get_response
        hub.async_send_command = AsyncMock()
        hub._get_initial_data = AsyncMock()

        with patch('pynobo.asyncio.open_connection',
                   new=AsyncMock(return_value=(reader, writer))):
            result = await hub.async_connect_hub('192.168.1.1', '123456789012')

        self.assertTrue(result)
        self.assertEqual(order, ['connection', 'data'])


class TestDiscovery(unittest.IsolatedAsyncioTestCase):

    async def test_repeated_discover_without_reuse_port(self):
        # Windows has no SO_REUSEPORT, so the discovery socket must be closed
        # before async_discover_hubs returns, or the next call fails to bind (#42).
        with patch.object(nobo, '_reuse_port', return_value=False):
            await nobo.async_discover_hubs(autodiscover_wait=0)
            await nobo.async_discover_hubs(autodiscover_wait=0)


if __name__ == '__main__':
    unittest.main()
