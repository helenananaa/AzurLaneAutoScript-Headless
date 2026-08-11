import random
import unittest

from alas_headless.adapter import (
    FlowScope,
    FlowScopeError,
    FlowScopeStack,
    FlowScopeToken,
)


SHA = "a" * 64


def scope(
    identifier,
    *,
    kind="mission",
    parent=None,
    operation="run",
):
    return FlowScope(
        scope_id=identifier,
        kind=kind,
        operation=operation,
        parent_scope_id=parent,
        task_config_sha256=SHA,
        allowed_capabilities=frozenset(),
        deadline_monotonic_ns=1_000_000,
    )


class AdapterScopeTests(unittest.TestCase):
    def test_constructor_rejects_malformed_session_and_parent_pairs(self):
        with self.assertRaises(ValueError):
            FlowScopeStack("bad session")
        for pairs in ((["root", "child"],), (("root",),), (("bad kind", "child"),)):
            with self.subTest(pairs=pairs):
                with self.assertRaises(ValueError):
                    FlowScopeStack(
                        "session-1",
                        allowed_parent_child_pairs=pairs,
                    )

    def test_root_scope_requires_exact_token_and_single_close(self):
        stack = FlowScopeStack("session-1")
        root = scope("mission-1")
        token = stack.open(root)
        self.assertEqual(stack.depth, 1)
        self.assertEqual(stack.active_scopes, (root,))
        self.assertEqual(stack.active_tokens, (token,))
        self.assertEqual(stack.close(token), root)
        self.assertEqual(stack.depth, 0)
        with self.assertRaises(FlowScopeError):
            stack.close(token)
        with self.assertRaises(FlowScopeError):
            stack.open(root)

    def test_nested_scope_requires_allowlisted_exact_parent_and_lifo_close(self):
        stack = FlowScopeStack(
            "session-1",
            allowed_parent_child_pairs={("campaign", "combat")},
        )
        root = scope("campaign-1", kind="campaign")
        child = scope("combat-1", kind="combat", parent=root.scope_id)
        root_token = stack.open(root)
        child_token = stack.open(child)
        self.assertEqual(stack.depth, 2)
        with self.assertRaises(FlowScopeError):
            stack.close(root_token)
        self.assertEqual(stack.close(child_token), child)
        self.assertEqual(stack.close(root_token), root)

        sibling = scope("combat-2", kind="combat", parent="campaign-1")
        with self.assertRaises(FlowScopeError):
            stack.open(sibling)

    def test_rejects_sibling_overlap_unowned_parent_and_foreign_token(self):
        stack = FlowScopeStack("session-1")
        root_token = stack.open(scope("mission-1"))
        with self.assertRaises(FlowScopeError):
            stack.open(scope("mail-1"))
        with self.assertRaises(FlowScopeError):
            stack.open(scope("mail-2", parent="missing"))
        foreign = FlowScopeToken("session-2", root_token.scope_id, root_token.ordinal)
        with self.assertRaises(FlowScopeError):
            stack.close(foreign)
        self.assertEqual(stack.depth, 1)
        stack.close(root_token)

    def test_context_manager_closes_exact_scope_after_success_and_failure(self):
        stack = FlowScopeStack("session-1")
        with stack.activate(scope("mission-1")) as token:
            self.assertEqual(stack.active_tokens, (token,))
        self.assertEqual(stack.depth, 0)

        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with stack.activate(scope("mission-2")):
                raise RuntimeError("test failure")
        self.assertEqual(stack.depth, 0)

    def test_shutdown_rejects_leaks_and_closes_clean_session_permanently(self):
        stack = FlowScopeStack("session-1")
        token = stack.open(scope("mission-1"))
        with self.assertRaises(FlowScopeError):
            stack.shutdown()
        self.assertFalse(stack.trace_fields()["closed"])
        stack.close(token)
        fields = stack.trace_fields()
        with self.assertRaises(TypeError):
            fields["depth"] = 999
        stack.shutdown()
        self.assertTrue(stack.trace_fields()["closed"])
        with self.assertRaises(FlowScopeError):
            stack.shutdown()
        with self.assertRaises(FlowScopeError):
            stack.open(scope("mission-2"))

    def test_seeded_operation_sequences_preserve_stack_invariants(self):
        generator = random.Random(20260812)
        stack = FlowScopeStack(
            "session-fuzz",
            allowed_parent_child_pairs={("root", "child")},
        )
        next_id = 0
        for _ in range(500):
            operation = generator.randrange(4)
            before_scopes = stack.active_scopes
            before_tokens = stack.active_tokens
            try:
                if operation == 0 and stack.depth == 0:
                    next_id += 1
                    stack.open(scope("root-{0}".format(next_id), kind="root"))
                elif operation == 1 and stack.depth == 1:
                    next_id += 1
                    parent = stack.active_scopes[-1]
                    stack.open(
                        scope(
                            "child-{0}".format(next_id),
                            kind="child",
                            parent=parent.scope_id,
                        )
                    )
                elif operation == 2 and stack.depth:
                    stack.close(stack.active_tokens[-1])
                else:
                    stack.close(FlowScopeToken("foreign", "fake", 999))
            except FlowScopeError:
                self.assertEqual(stack.active_scopes, before_scopes)
                self.assertEqual(stack.active_tokens, before_tokens)
            self.assertEqual(stack.depth, len(stack.active_scopes))
            self.assertEqual(stack.depth, len(stack.active_tokens))
            self.assertEqual(
                tuple(item.scope_id for item in stack.active_scopes),
                tuple(item.scope_id for item in stack.active_tokens),
            )
        while stack.depth:
            stack.close(stack.active_tokens[-1])
        stack.shutdown()


if __name__ == "__main__":
    unittest.main()
