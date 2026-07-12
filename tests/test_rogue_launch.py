import os
import select
import signal
import time
import unittest


class RogueLaunchTest(unittest.TestCase):
    def test_launch_new_game_and_quit(self):
        if os.name != "posix":
            self.skipTest("PTY launch test requires POSIX")

        binary = os.environ.get("ROGUE_BINARY")
        if not binary:
            self.skipTest("set ROGUE_BINARY to run the Rogue launch test")

        import pty

        binary = os.path.abspath(binary)
        cwd = os.path.dirname(binary)
        argv0 = os.path.basename(binary)
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(cwd)
            os.environ.setdefault("TERM", "xterm")
            os.execl(binary, argv0)

        output = bytearray()
        deadline = time.time() + 12.0
        sent_quit = False
        sent_confirm = False
        sent_return = False
        status = None
        try:
            while time.time() < deadline:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(fd, 4096)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        break
                    output.extend(chunk)

                if not sent_quit and b"Level:" in output and b"Gold:" in output:
                    os.write(fd, b"Q")
                    sent_quit = True
                elif sent_quit and not sent_confirm and b"really quit?" in output.lower():
                    os.write(fd, b"y")
                    sent_confirm = True
                elif sent_confirm and not sent_return and b"press return" in output.lower():
                    os.write(fd, b"\r")
                    sent_return = True

                try:
                    done_pid, status = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if done_pid == pid:
                    break
            else:
                os.kill(pid, signal.SIGKILL)
                tail = bytes(output[-1200:])
                self.fail(
                    "Rogue did not exit after Q/y/Return input; "
                    f"sent_quit={sent_quit} sent_confirm={sent_confirm} "
                    f"sent_return={sent_return} "
                    f"tail={tail!r}"
                )
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass

        text = bytes(output)
        self.assertIsNotNone(status)
        self.assertTrue(os.WIFEXITED(status), text[-1000:])
        self.assertEqual(os.WEXITSTATUS(status), 0, text[-1000:])
        for token in (b"Level:", b"Gold:", b"Hp:", b"Str:", b"Arm:", b"Exp:"):
            self.assertIn(token, text)
        self.assertIn(b"@", text)
        self.assertIn(b"really quit?", text.lower())
        self.assertIn(b"You quit with", text)


if __name__ == "__main__":
    unittest.main()
