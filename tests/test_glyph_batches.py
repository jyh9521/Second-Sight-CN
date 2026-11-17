"""Synthetic checks for offline replay inputs and primitive boundary contracts.

The real EXE and ASI instruction replay is a separate explicit CLI invocation;
no original game machine-code fixture is committed or opened by these tests.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import replay_glyph_batches as replay


class GlyphBatchInputTests(unittest.TestCase):
    def test_reject_unknown_executable(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            replay.validate_executable(b"not a game executable")

    def test_map_resolves_c_symbol(self):
        text = " 0001:00001234 _BeginTextBatchHook 10002234 f localization.obj\n"
        self.assertEqual(replay.map_symbol(text, "BeginTextBatchHook"), 0x10002234)

    def test_map_rejects_missing_or_ambiguous_symbol(self):
        with self.assertRaises(ValueError):
            replay.map_symbol("", "BeginTextBatchHook")
        with self.assertRaises(ValueError):
            replay.map_symbol("0001:00000000 _Hook 10001000 f x.obj\n"
                              "0001:00000001 _Hook 10001001 f x.obj\n", "Hook")

    def test_manifest_identity_bounds_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            def put(glyphs, identity=replay.EXE_SHA256):
                path.write_text(json.dumps(dict(executable_sha256=identity, glyphs=glyphs)), encoding="utf-8")
            put({"A": 0, "B": 6143})
            self.assertEqual(replay.load_glyphs(path), {"A": 0, "B": 6143})
            for glyphs in ({"A": 0, "B": 0}, {"A": -1}, {"A": 6144}, {"AA": 1}, {"A": True}):
                put(glyphs)
                with self.assertRaises(ValueError):
                    replay.load_glyphs(path)
            put({"A": 0}, "wrong")
            with self.assertRaisesRegex(ValueError, "identity"):
                replay.load_glyphs(path)

    def test_cell_and_page_are_independent(self):
        for page in range(6):
            token = replay.Token(str(page), page * 1024 + 1023)
            self.assertEqual(token.texture, replay.PAGE_TEXTURE + page)
            self.assertEqual(token.cell, 1023)
        self.assertEqual(replay.Token("A", 65, latin=True).texture, replay.LATIN_TEXTURE)
        self.assertEqual(replay.Token(" ", space=True).texture, replay.LATIN_TEXTURE)

    def test_feedback_is_separate_from_generic_tool(self):
        path = Path(__file__).parent / "fixtures/glyph_batch_feedback.json"
        feedback = json.loads(path.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(feedback), 6)
        self.assertTrue(all(row["expected"] != row["observed_baseline"] for row in feedback))


def boundary_machine():
    """Build a zero-filled synthetic machine, not an original EXE fixture."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, x86_const
    machine = object.__new__(replay.NativeReplay)
    machine.uc = Uc(UC_ARCH_X86, UC_MODE_32)
    machine.reg = x86_const
    machine.uc.mem_map(0x400000, 0x600000)
    machine.uc.mem_map(replay.STACK_BASE, replay.STACK_SIZE)
    machine.symbols = {}
    machine.executed_hooks = {}
    machine.current_token = replay.Token("synthetic", 0)
    machine.current_index = 0
    machine.queue = []
    machine.submissions = []
    machine.begin_count = machine.end_count = machine.bind_count = 0
    machine.capacity = 0
    machine.uc.hook_add(UC_HOOK_CODE, machine._code)
    return machine


class PrimitiveBoundaryTests(unittest.TestCase):
    def test_partial_capacity_submits_only_actual_vertices(self):
        m = boundary_machine()
        m.write_u32(replay.TEXTURE, replay.PAGE_TEXTURE)
        m.invoke(replay.BEGIN, [0x92, 2, 40, 0xFFFFFFF6])
        m.invoke(replay.EMIT, [0] * 16)
        m.invoke(replay.END, [])
        self.assertEqual(m.submissions[0]["vertices"], 6)
        self.assertEqual(m.submissions[0]["capacity"], 60)
        self.assertEqual(m.read_u32(replay.CURSOR), 0)
        self.assertEqual(m.read_u32(replay.ACTUAL), 6)  # Deliberately stale like native End.
        m.invoke(replay.BEGIN, [0x92, 2, 4, 0xFFFFFFF6])
        self.assertEqual(m.read_u32(replay.ACTUAL), 0)

    def test_begin_rejects_unsubmitted_vertices(self):
        m = boundary_machine()
        m.invoke(replay.BEGIN, [0x92, 2, 8, 0xFFFFFFF6])
        m.invoke(replay.EMIT, [0] * 16)
        with self.assertRaisesRegex(ValueError, "discard"):
            m.invoke(replay.BEGIN, [0x92, 2, 4, 0xFFFFFFF6])

    def test_emit_rejects_capacity_overflow(self):
        m = boundary_machine()
        m.invoke(replay.BEGIN, [0x92, 2, 4, 0xFFFFFFF6])
        m.invoke(replay.EMIT, [0] * 16)
        with self.assertRaisesRegex(ValueError, "capacity"):
            m.invoke(replay.EMIT, [0] * 16)

    def test_recording_end_preserves_record_cursor(self):
        m = boundary_machine()
        m.write_u32(replay.RECORDING, 1)
        m.write_u32(replay.CURSOR, replay.VERTICES)
        m.invoke(replay.BEGIN, [0x92, 2, 4, 0xFFFFFFF6])
        m.invoke(replay.EMIT, [0] * 16)
        cursor = m.read_u32(replay.CURSOR)
        m.invoke(replay.END, [])
        self.assertEqual(m.read_u32(replay.CURSOR), cursor)

    def test_texture_storage_does_not_flush(self):
        m = boundary_machine()
        m.invoke(replay.BEGIN, [0x92, 2, 4, 0xFFFFFFF6])
        m.invoke(replay.EMIT, [0] * 16)
        m.invoke(replay.BIND_STORAGE, [0, replay.PAGE_TEXTURE + 1])
        self.assertEqual(len(m.queue), 1)
        self.assertEqual(m.end_count, 0)
        self.assertEqual(m.read_u32(replay.TEXTURE), replay.PAGE_TEXTURE + 1)

    def test_cdecl_stack_cleanup_is_checked(self):
        m = boundary_machine()
        address = 0x500000
        # Authored synthetic instruction: RET 4, deliberately the wrong ABI.
        m.uc.mem_write(address, bytes.fromhex("C2 04 00"))
        with self.assertRaisesRegex(ValueError, "stack imbalance"):
            m.invoke(address, [123])


if __name__ == "__main__":
    unittest.main()
