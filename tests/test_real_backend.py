"""Tests for the Phase 9A ctypes native ABI bootstrap stub."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from runtime.actions import RequestedAction
from runtime.determinism import DeterminismContext
from runtime.provider import DecisionRequest, DecisionResponse, DecisionStatus
from runtime.rogue import (
    CtypesRogueNativeBackend,
    RogueAbiVersionError,
    RogueCloseError,
    RogueDomainAdapter,
    RogueLibraryLoadError,
    RogueSymbolMissingError,
)
from runtime.orchestrator import RuntimeOrchestrator
from runtime.state import EpisodeOutcome, RuntimeState


REPO_ROOT = Path(__file__).resolve().parents[1]
NATIVE_SOURCE = REPO_ROOT / "native" / "rogue_native_bootstrap.c"
NATIVE_INCLUDE = REPO_ROOT / "adapter" / "native" / "include"
STUB_IDENTITY_SCOPE = "phase9_native_abi_stub"
STUB_UPSTREAM_IDENTITY = "NaMMA Rogue Native ABI Bootstrap Stub"
STUB_BUILD_IDENTITY = "phase9-native-abi-stub"


def compiler() -> str | None:
    return shutil.which("gcc") or shutil.which("cc")


def shared_library_path(directory: Path, name: str) -> Path:
    suffix = ".dll" if os.name == "nt" else ".so"
    return directory / f"{name}{suffix}"


def compile_shared_library(source: Path, output: Path) -> None:
    cc = compiler()
    if cc is None:
        raise unittest.SkipTest("C compiler is not available")
    command = [
        cc,
        "-shared",
        "-Wall",
        "-Wextra",
        "-Werror",
        f"-I{NATIVE_INCLUDE}",
        str(source),
        "-o",
        str(output),
    ]
    if os.name != "nt":
        command.insert(2, "-fPIC")
    subprocess.run(command, check=True, cwd=REPO_ROOT)


def make_context() -> DeterminismContext:
    return DeterminismContext.from_config(
        world_seed=9001,
        episode_seed=42,
        source_identity=STUB_UPSTREAM_IDENTITY,
        build_identity=STUB_BUILD_IDENTITY,
        compatibility_patch_identity="not-applicable",
        config={
            "profile": "phase9-native-abi-stub-test",
            "identity_scope": STUB_IDENTITY_SCOPE,
        },
    )


class SequenceProvider:
    def __init__(self, actions: list[RequestedAction]) -> None:
        self._actions = list(actions)
        self.requests: list[DecisionRequest] = []

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        self.requests.append(request)
        if not self._actions:
            return DecisionResponse(
                request_id=request.request_id,
                status=DecisionStatus.NO_ACTION,
            )
        return DecisionResponse(
            request_id=request.request_id,
            status=DecisionStatus.OK,
            requested_action=self._actions.pop(0),
        )


@unittest.skipIf(compiler() is None, "C compiler is not available")
class CtypesRogueNativeBackendTests(unittest.TestCase):
    def build_backend(
        self,
        temp_dir: Path,
        name: str = "namma_rogue_bootstrap",
    ) -> CtypesRogueNativeBackend:
        library = shared_library_path(temp_dir, name)
        compile_shared_library(NATIVE_SOURCE, library)
        return CtypesRogueNativeBackend(library)

    def test_create_reset_observe_identity_terminal_wait_quit(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            backend = self.build_backend(Path(temp))
            backend.create(backend.config)

            reset = backend.reset(make_context())
            observation = backend.observe()
            identity = backend.source_identity()
            terminal = backend.terminal_status()

            self.assertEqual("OK", reset.status)
            self.assertEqual("Rogue native bootstrap reset.", observation.recent_message)
            self.assertEqual(0, observation.turn)
            self.assertFalse(observation.terminal)
            self.assertFalse(terminal.terminal)
            self.assertEqual(STUB_IDENTITY_SCOPE, identity.identity_scope)
            self.assertEqual(STUB_UPSTREAM_IDENTITY, identity.upstream_identity)
            self.assertNotIn("Rogueforge Rogue 5.4.4", identity.upstream_identity)
            self.assertEqual("", identity.upstream_archive_sha256)
            self.assertEqual("not-applicable", identity.compatibility_patch_identity)
            self.assertEqual("native/rogue_native_bootstrap.c", identity.source_commit)
            self.assertEqual(STUB_BUILD_IDENTITY, identity.build_identity)

            wait = backend.validate_action(RequestedAction("WAIT"))
            self.assertTrue(wait.accepted)
            wait_result = backend.apply_action(wait, turn=0)
            self.assertFalse(wait_result.terminal)
            self.assertEqual("wait", wait_result.domain_events[0])
            self.assertEqual(1, backend.observe().turn)

            move = backend.validate_action(
                RequestedAction("MOVE", {"direction": "S"})
            )
            self.assertFalse(move.accepted)

            quit_action = backend.validate_action(RequestedAction("QUIT"))
            quit_result = backend.apply_action(quit_action, turn=1)
            terminal = backend.terminal_status()

            self.assertTrue(quit_result.terminal)
            self.assertTrue(terminal.terminal)
            self.assertEqual(EpisodeOutcome.USER_ABORT, terminal.outcome)
            backend.close()
            backend.close()

    def test_runtime_runs_quit_episode_through_native_abi_stub(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            backend = self.build_backend(Path(temp))
            adapter = RogueDomainAdapter(backend)
            provider = SequenceProvider([RequestedAction("QUIT")])
            runtime = RuntimeOrchestrator(
                domain=adapter,
                decision_provider=provider,
                context=make_context(),
                max_runtime_turns=3,
            )

            result = runtime.run_episode("phase9-native-abi-stub")

            self.assertEqual(RuntimeState.TERMINATED, result.runtime_state)
            self.assertEqual(EpisodeOutcome.USER_ABORT, result.outcome)
            self.assertEqual(1, len(result.replay_episode.events))
            event = result.replay_episode.events[0]
            self.assertEqual(STUB_UPSTREAM_IDENTITY, event.source_identity)
            self.assertEqual(STUB_BUILD_IDENTITY, event.build_identity)
            self.assertEqual("not-applicable", event.compatibility_patch_identity)
            self.assertEqual(["WAIT", "QUIT"], provider.requests[0].allowed_action_schema["action_types"])

    def test_stub_diagnostic_checksum_is_deterministic_only(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            first = self.build_backend(Path(temp))
            first.create(first.config)
            first.reset(make_context())
            first_checksum = first.privileged_debug_state().payload[
                "replay_verification_state"
            ]["native_checksum"]
            same_checksum = first.privileged_debug_state().payload[
                "replay_verification_state"
            ]["native_checksum"]
            self.assertEqual(first_checksum, same_checksum)

            wait = first.validate_action(RequestedAction("WAIT"))
            first.apply_action(wait, turn=0)
            changed_by_turn = first.privileged_debug_state().payload[
                "replay_verification_state"
            ]["native_checksum"]
            self.assertNotEqual(first_checksum, changed_by_turn)
            first.close()

            second = self.build_backend(Path(temp), "namma_rogue_bootstrap_seed")
            second.create(second.config)
            altered_context = DeterminismContext.from_config(
                world_seed=make_context().world_seed + 1,
                episode_seed=make_context().episode_seed,
                source_identity=STUB_UPSTREAM_IDENTITY,
                build_identity=STUB_BUILD_IDENTITY,
                compatibility_patch_identity="not-applicable",
                config={"profile": "phase9-native-abi-stub-test"},
            )
            second.reset(altered_context)
            changed_by_seed = second.privileged_debug_state().payload[
                "replay_verification_state"
            ]["native_checksum"]
            self.assertNotEqual(first_checksum, changed_by_seed)
            second.close()

    def test_backend_error_classes_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            temp_path = Path(temp)
            missing = temp_path / "missing-native-library.so"

            with self.assertRaises(RogueLibraryLoadError):
                CtypesRogueNativeBackend(missing)

            wrong_abi_source = temp_path / "wrong_abi.c"
            wrong_abi_source.write_text(
                "#include <stdint.h>\n"
                "#if defined(_WIN32)\n"
                "#define EXPORT __declspec(dllexport)\n"
                "#else\n"
                "#define EXPORT __attribute__((visibility(\"default\")))\n"
                "#endif\n"
                "EXPORT uint32_t namma_rogue_abi_version(void) {\n"
                "    return 99u << 16u;\n"
                "}\n",
                encoding="utf-8",
                newline="\n",
            )
            wrong_abi_library = shared_library_path(temp_path, "wrong_abi")
            compile_shared_library(wrong_abi_source, wrong_abi_library)
            with self.assertRaises(RogueAbiVersionError):
                CtypesRogueNativeBackend(wrong_abi_library)

            missing_symbol_source = temp_path / "missing_symbol.c"
            missing_symbol_source.write_text(
                "#include <stdint.h>\n"
                "#if defined(_WIN32)\n"
                "#define EXPORT __declspec(dllexport)\n"
                "#else\n"
                "#define EXPORT __attribute__((visibility(\"default\")))\n"
                "#endif\n"
                "EXPORT uint32_t namma_rogue_abi_version(void) {\n"
                "    return (0u << 16u) | 2u;\n"
                "}\n",
                encoding="utf-8",
                newline="\n",
            )
            missing_symbol_library = shared_library_path(temp_path, "missing_symbol")
            compile_shared_library(missing_symbol_source, missing_symbol_library)
            with self.assertRaises(RogueSymbolMissingError):
                CtypesRogueNativeBackend(missing_symbol_library)

    def test_close_failure_is_distinct(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            backend = self.build_backend(Path(temp))
            backend.create(backend.config)

            def failing_destroy(_handle):
                raise RuntimeError("destroy failed")

            backend._namma_rogue_destroy = failing_destroy

            with self.assertRaises(RogueCloseError):
                backend.close()


if __name__ == "__main__":
    unittest.main()
