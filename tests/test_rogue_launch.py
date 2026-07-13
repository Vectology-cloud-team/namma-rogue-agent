import os
import select
import signal
import subprocess
import time
import unittest


STATUS_TOKENS = (b"Level:", b"Gold:", b"Hp:", b"Str:", b"Arm:", b"Exp:")


class RogueLaunchTest(unittest.TestCase):
    def _require_posix_binary(self):
        if os.name != "posix":
            self.skipTest("PTY launch test requires POSIX")

        binary = os.environ.get("ROGUE_BINARY")
        if not binary:
            self.skipTest("set ROGUE_BINARY to run the Rogue launch test")
        return os.path.abspath(binary)

    def _start_rogue(self, binary):
        import pty

        cwd = os.path.dirname(binary)
        env = os.environ.copy()
        env.setdefault("TERM", "xterm")
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            [binary],
            cwd=cwd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            preexec_fn=os.setpgrp,
            close_fds=True,
        )
        os.close(slave_fd)
        return process, master_fd, bytearray()

    def _signal_child_group(self, pid, sig):
        try:
            os.killpg(os.getpgid(pid), sig)
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                pass

    def _read_available(self, fd, output, timeout=0.1):
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            chunk = b""
        output.extend(chunk)

    def _tail(self, output):
        return bytes(output[-1200:])

    def _fail(self, stage, output, **state):
        details = " ".join(f"{key}={value!r}" for key, value in state.items())
        self.fail(f"stage={stage} {details} tail={self._tail(output)!r}")

    def _mark_process_exit(self, process, status):
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            process.returncode = os.waitstatus_to_exitcode(status)

    def _cleanup_child(self, process, fd):
        pid = process.pid
        self._signal_child_group(pid, signal.SIGCONT)

        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done == pid:
                    self._mark_process_exit(process, status)
                    break
            except ChildProcessError:
                break
            self._signal_child_group(pid, sig)
            time.sleep(0.1)

        try:
            _, status = os.waitpid(pid, 0)
            self._mark_process_exit(process, status)
        except ChildProcessError:
            pass
        except OSError:
            pass

        try:
            os.close(fd)
        except OSError:
            pass

    def _wait_for_status(self, process, fd, output, deadline):
        while time.time() < deadline:
            self._read_available(fd, output)
            if all(token in output for token in STATUS_TOKENS):
                return
            done, status = os.waitpid(process.pid, os.WNOHANG)
            if done == process.pid:
                self._mark_process_exit(process, status)
                self._fail("wait_for_status", output, status=status)
        self._fail("wait_for_status_timeout", output)

    def _wait_for_text(self, process, fd, output, needle, deadline, stage):
        needle = needle.lower()
        while time.time() < deadline:
            self._read_available(fd, output)
            if needle in bytes(output).lower():
                return
            done, status = os.waitpid(process.pid, os.WNOHANG)
            if done == process.pid:
                self._mark_process_exit(process, status)
                self._fail(stage, output, status=status)
        self._fail(f"{stage}_timeout", output, needle=needle)

    def _quit_and_wait(self, process, fd, output, deadline):
        sent_quit = False
        sent_confirm = False
        sent_return = False
        status = None
        while time.time() < deadline:
            self._read_available(fd, output)
            lower = bytes(output).lower()

            if not sent_quit:
                os.write(fd, b"Q")
                sent_quit = True
            elif not sent_confirm and b"really quit?" in lower:
                os.write(fd, b"y")
                sent_confirm = True
            elif sent_confirm and not sent_return and b"press return" in lower:
                os.write(fd, b"\r")
                sent_return = True

            done, status = os.waitpid(process.pid, os.WNOHANG)
            if done == process.pid:
                self._mark_process_exit(process, status)
                return status

        self._fail(
            "quit_timeout",
            output,
            sent_quit=sent_quit,
            sent_confirm=sent_confirm,
            sent_return=sent_return,
        )

    def _assert_clean_exit(self, status, output):
        self.assertIsNotNone(status)
        self.assertTrue(os.WIFEXITED(status), self._tail(output))
        self.assertEqual(os.WEXITSTATUS(status), 0, self._tail(output))

    def test_launch_new_game_and_quit(self):
        binary = self._require_posix_binary()
        process, fd, output = self._start_rogue(binary)
        try:
            self._wait_for_status(process, fd, output, time.time() + 12.0)
            status = self._quit_and_wait(process, fd, output, time.time() + 12.0)
        except BaseException:
            self._cleanup_child(process, fd)
            raise
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

        text = bytes(output)
        self._assert_clean_exit(status, output)
        for token in STATUS_TOKENS:
            self.assertIn(token, text)
        self.assertIn(b"@", text)
        self.assertIn(b"really quit?", text.lower())
        self.assertIn(b"You quit with", text)

    def test_suspend_resume_accepts_input_and_quits(self):
        binary = self._require_posix_binary()
        process, fd, output = self._start_rogue(binary)
        stage = "start"
        try:
            stage = "wait_for_initial_status"
            self._wait_for_status(process, fd, output, time.time() + 12.0)

            stage = "send_sigtstp"
            os.kill(process.pid, signal.SIGTSTP)

            stage = "wait_for_stopped_state"
            stopped = False
            deadline = time.time() + 5.0
            while time.time() < deadline:
                self._read_available(fd, output)
                done, status = os.waitpid(
                    process.pid,
                    os.WUNTRACED | os.WNOHANG,
                )
                if done == process.pid:
                    if os.WIFSTOPPED(status):
                        stopped = True
                        break
                    self._mark_process_exit(process, status)
                    self._fail(stage, output, status=status)
                time.sleep(0.05)
            if not stopped:
                self._fail(stage, output, stopped=stopped)

            stage = "send_sigcont"
            os.kill(process.pid, signal.SIGCONT)
            time.sleep(0.2)
            self._read_available(fd, output)
            done, status = os.waitpid(process.pid, os.WNOHANG)
            if done == process.pid:
                self._mark_process_exit(process, status)
                self._fail(stage, output, status=status)

            stage = "post_resume_input"
            os.write(fd, b"X")
            self._wait_for_text(
                process,
                fd,
                output,
                b"illegal command",
                time.time() + 5.0,
                stage,
            )

            stage = "quit_after_resume"
            status = self._quit_and_wait(process, fd, output, time.time() + 12.0)
        except BaseException:
            self._cleanup_child(process, fd)
            raise
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

        text = bytes(output)
        self._assert_clean_exit(status, output)
        for token in STATUS_TOKENS:
            self.assertIn(token, text)
        self.assertIn(b"illegal command", text.lower())
        self.assertIn(b"really quit?", text.lower())
        self.assertIn(b"You quit with", text)


if __name__ == "__main__":
    unittest.main()
