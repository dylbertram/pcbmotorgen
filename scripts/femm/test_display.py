"""The presence of an X socket does not prove Wine can open the display."""
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(Path('/tmp/.X11-unix').is_dir() and os.access('/tmp/.X11-unix',os.W_OK),
                     'Display socket tests require a writable existing X11 socket directory')
class DisplayTest(unittest.TestCase):
    def run_display(self, available):
        # Only the socket created by this test is removed. No user's X server
        # is started, contacted or killed; xdpyinfo is an explicit test stub.
        with tempfile.TemporaryDirectory() as directory:
            tools=Path(directory)
            probe=tools/'xdpyinfo';probe.write_text('#!/bin/sh\nexit "$DISPLAY_TEST_EXIT"\n');probe.chmod(0o755)
            display=str(100000+os.getpid())
            path=Path('/tmp/.X11-unix')/('X'+display)
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(path))
                try:
                    env=dict(os.environ,PATH=str(tools)+':'+os.environ['PATH'],DISPLAY_TEST_EXIT='0' if available else '1')
                    script='source "$1"; femm_xvfb "$2" || exit $?; printf "%s" "$DISPLAY"'
                    return subprocess.run(['bash','-c',script,'test',str(Path(__file__).with_name('femm_env.sh')),':'+display],
                                          env=env,capture_output=True,text=True,timeout=10),':'+display
                finally:path.unlink()

    def test_stale_socket_fails_without_unlinking_or_starting_a_server(self):
        result,_=self.run_display(False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('socket but no accessible X server',result.stderr)
        self.assertIn('has not been removed',result.stderr)

    def test_accessible_existing_display_is_exported(self):
        result,display=self.run_display(True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,display)
