"""Test compaction and pruning functionality."""
import pytest
from session.compaction import (
    ConversationCompaction,
    ConversationManager,
    MessagePart,
    PartType,
    ToolCallState,
    is_contextual_message,
    truncate_middle,
    truncate_middle_chars,
)


class TestIsContextualMessage:
    """Test is_contextual_message detection."""

    def test_model_switch_detection(self):
        assert is_contextual_message("<model_switch>gpt-4</model_switch>") is True

    def test_permissions_detection(self):
        assert is_contextual_message("<permissions>sudo access</permissions>") is True

    def test_model_reject_detection(self):
        assert is_contextual_message("<model拒绝>API rate limit</model拒绝>") is True

    def test_system_instructions_detection(self):
        assert is_contextual_message("<system-instructions>Follow rules</system-instructions>") is True

    def test_system_reminder_detection(self):
        assert is_contextual_message("<system-reminder>Remember this</system-reminder>") is True

    def test_pipe_format_detection(self):
        assert is_contextual_message("<|model|gpt-4|>") is True
        assert is_contextual_message("<|system|instructions|>") is True

    def test_normal_text_not_detected(self):
        assert is_contextual_message("Hello, how can I help you?") is False
        assert is_contextual_message("Please write a function") is False
        assert is_contextual_message("What's the weather?") is False


class TestPruneContextualMessages:
    """Test prune_contextual_messages functionality."""

    def test_prune_removes_contextual_messages(self):
        """Test that contextual messages are removed."""
        compaction = ConversationCompaction()
        compaction.add_message("user", "<model_switch>gpt-4</model_switch>")
        compaction.add_message("assistant", "OK, switched to gpt-4.")
        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi there!")

        result = compaction.prune_contextual_messages(protect_recent=2)

        assert result["messages_modified"] == 1
        assert result["tokens_saved"] > 0
        assert "[Contextual message removed]" in compaction.messages[0].content

    def test_prune_preserves_recent_messages(self):
        """Test that recent messages are not pruned."""
        compaction = ConversationCompaction()
        compaction.add_message("user", "<model_switch>old</model_switch>")
        compaction.add_message("assistant", "OK")
        compaction.add_message("user", "<permissions>new</permissions>")
        compaction.add_message("assistant", "OK")

        result = compaction.prune_contextual_messages(protect_recent=2)

        # First message should be pruned, second should be protected
        assert compaction.messages[0].content == "[Contextual message removed]"
        assert "<permissions>" in compaction.messages[2].content


class TestPruneToUserBoundary:
    """Test prune_to_user_boundary functionality."""

    def test_prune_preserves_recent_turns(self):
        """Test that recent turns are preserved."""
        compaction = ConversationCompaction()

        # Add 10 turns
        for i in range(10):
            compaction.add_message("user", f"User message {i+1}")
            compaction.add_message("assistant", f"Assistant reply {i+1}")

        pruned = compaction.prune_to_user_boundary(protect_turns=3, max_turns=None)

        # Should delete 7 pairs (14 messages), keep 3 pairs (6 messages)
        assert pruned == 14
        assert len(compaction.messages) == 6
        # First message should be from turn 8 (the 3rd protected turn)
        assert "User message 8" in compaction.messages[0].content

    def test_prune_respects_max_turns(self):
        """Test max_turns limit."""
        compaction = ConversationCompaction()

        # Add 10 turns
        for i in range(10):
            compaction.add_message("user", f"User {i+1}")
            compaction.add_message("assistant", f"Assistant {i+1}")

        pruned = compaction.prune_to_user_boundary(protect_turns=2, max_turns=5)

        # Should keep 5 turns (10 messages)
        assert len(compaction.messages) == 10
        # Should start from turn 6
        assert "User 6" in compaction.messages[0].content


class TestSmartPrune:
    """Test smart_prune分层裁剪策略."""

    def test_smart_prune_level_0_contextual(self):
        """Test Level 0 contextual pruning."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "<model_switch>old</model_switch>")
        compaction.add_message("assistant", "OK")
        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi")

        result = compaction.smart_prune()

        # Should have Level 0 action for contextual
        assert any(a["level"] == 0 and a["action"] == "prune_contextual" for a in result["actions"])

    def test_smart_prune_level_1_tool_results(self):
        """Test Level 1 tool result pruning via ConversationManager."""
        manager = ConversationManager()

        # Add many turns with large content to exceed 20000 tokens
        for i in range(100):
            manager.add_user_message(f"User {i+1}: " + "x" * 400)  # ~100 tokens
            tool_part = MessagePart(
                part_type=PartType.TOOL.value,
                content=f"Tool output {i}: " + "x" * 400,  # ~100 tokens
                tool_name="test_tool",
                tool_call_id=f"call_{i}",
                tool_call_state=ToolCallState.COMPLETED,
                token_count=0
            )
            manager.add_assistant_message(f"Reply {i+1}: " + "x" * 400, parts=[tool_part])

        # Verify we have enough tokens
        assert manager.compaction.total_tokens > 20000

        result = manager.smart_prune()

        # Should have Level 1 action for tool pruning
        assert any(a["level"] == 1 and a["action"] == "prune_tool_results" for a in result["actions"])


class TestPrune:
    """Test basic prune functionality."""

    def test_prune_clears_old_tool_results(self):
        """Test that prune clears old tool results."""
        compaction = ConversationCompaction()

        # Add many turns to exceed PRUNE_MINIMUM (20000 tokens)
        # Add first half with tool calls (to be pruned later)
        for i in range(30):
            compaction.add_message("user", f"User message {i+1}: " + "x" * 800)  # ~200 tokens
            tool_part = MessagePart(
                part_type=PartType.TOOL.value,
                content="Tool output that should be pruned: " + "x" * 500,
                tool_name="test_tool",
                tool_call_id=f"call_{i}",
                tool_call_state=ToolCallState.COMPLETED,
                token_count=0
            )
            compaction.add_message("assistant", f"Reply {i+1}", parts=[tool_part])

        # Add second half without tool calls (protected recent turns)
        for i in range(30, 60):
            compaction.add_message("user", f"User message {i+1}: " + "x" * 800)
            compaction.add_message("assistant", f"Assistant reply {i+1}: " + "x" * 800)

        # Verify we have enough tokens
        assert compaction.total_tokens > 20000, f"Need > 20000 tokens, got {compaction.total_tokens}"

        pruned = compaction.prune()

        assert pruned > 0, "Should prune some tokens from old tool calls"

    def test_prune_protects_skill_tool(self):
        """Test that skill tool is protected from pruning."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Use a skill")
        skill_part = MessagePart(
            part_type=PartType.TOOL.value,
            content="Skill result",
            tool_name="skill",
            tool_call_id="call_1",
            tool_call_state=ToolCallState.COMPLETED,
            token_count=50
        )
        compaction.add_message("assistant", "OK", parts=[skill_part])
        compaction.add_message("user", "Another task")
        compaction.add_message("assistant", "OK")

        pruned = compaction.prune()

        # Skill tool should NOT be pruned
        assert compaction.messages[1].parts[0].compacted is False
        assert compaction.messages[1].parts[0].content == "Skill result"


class TestPruneReasoningOnly:
    """Test prune_reasoning_only functionality."""

    def test_prune_removes_reasoning(self):
        """Test that reasoning content is removed."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi", reasoning="This is my thinking process")

        pruned = compaction.prune_reasoning_only()

        assert pruned > 0
        assert compaction.messages[1].reasoning is None
        assert compaction.reasoning_tokens == 0


class TestTruncateMiddle:
    """Test truncate_middle functions."""

    def test_truncate_middle_short_text(self):
        """Test that short text is not truncated."""
        text = "Hello, world!"
        result, original = truncate_middle(text, 100)
        assert result == text
        assert original is None

    def test_truncate_middle_long_text(self):
        """Test that long text is truncated with marker."""
        text = "A" * 1000
        result, original = truncate_middle(text, 100)
        assert "truncated" in result
        assert original is not None
        assert result.startswith("AAAA")
        assert result.endswith("AAAA")

    def test_truncate_middle_chars(self):
        """Test truncate by character count."""
        text = "A" * 1000
        result = truncate_middle_chars(text, 50)
        assert "truncated" in result
        assert result.startswith("AAAA")
        assert result.endswith("AAAA")

    def test_truncate_middle_empty(self):
        """Test empty text handling."""
        result, _ = truncate_middle("", 100)
        assert result == ""


class TestRollback:
    """Test rollback functionality."""

    def test_rollback_one_turn(self):
        """Test rolling back one turn."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi there!")
        compaction.add_message("user", "How are you?")
        compaction.add_message("assistant", "I'm good!")

        before_count = len(compaction.messages)
        result = compaction.rollback(1)

        assert result["rolled_back"] == 1
        assert result["messages_removed"] == 2
        assert len(compaction.messages) == before_count - 2

    def test_rollback_multiple_turns(self):
        """Test rolling back multiple turns."""
        compaction = ConversationCompaction()

        # Add 5 turns
        for i in range(5):
            compaction.add_message("user", f"User message {i+1}")
            compaction.add_message("assistant", f"Assistant reply {i+1}")

        before_count = len(compaction.messages)
        result = compaction.rollback(2)

        assert result["rolled_back"] == 2
        assert result["messages_removed"] == 4
        assert len(compaction.messages) == before_count - 4

    def test_rollback_preserves_early_messages(self):
        """Test that early messages are preserved."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "First")
        compaction.add_message("assistant", "First reply")
        compaction.add_message("user", "Second")
        compaction.add_message("assistant", "Second reply")
        compaction.add_message("user", "Third")
        compaction.add_message("assistant", "Third reply")

        compaction.rollback(1)

        # First turn should still be there
        assert "First" in compaction.messages[0].content
        assert "First reply" in compaction.messages[1].content

    def test_rollback_more_than_available(self):
        """Test rollback when requesting more turns than available."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi")

        result = compaction.rollback(10)

        # Should rollback all available
        assert result["rolled_back"] == 1
        assert len(compaction.messages) == 0

    def test_rollback_zero_turns(self):
        """Test rollback with 0 turns is no-op."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi")

        result = compaction.rollback(0)

        assert result["rolled_back"] == 0
        assert len(compaction.messages) == 2


class TestRemoveOldestMessages:
    """Test remove_oldest_messages FIFO deletion."""

    def test_remove_oldest_single_message(self):
        """Test removing one oldest message."""
        compaction = ConversationCompaction()

        compaction.add_message("assistant", "Hello! How can I help?")
        compaction.add_message("user", "Hi")
        compaction.add_message("assistant", "Hi there!")

        result = compaction.remove_oldest_messages(1)

        assert result["removed"] == 1
        assert len(compaction.messages) == 2
        assert compaction.messages[0].content == "Hi"

    def test_remove_oldest_multiple_messages(self):
        """Test removing multiple oldest messages."""
        compaction = ConversationCompaction()

        compaction.add_message("assistant", "First reply")
        compaction.add_message("user", "First question")
        compaction.add_message("assistant", "Second reply")
        compaction.add_message("user", "Second question")

        result = compaction.remove_oldest_messages(2)

        assert result["removed"] == 2
        assert len(compaction.messages) == 2
        assert compaction.messages[0].content == "Second reply"

    def test_remove_oldest_preserves_summary(self):
        """Test that summary message is protected."""
        compaction = ConversationCompaction()

        compaction.add_message("assistant", "Welcome!")
        compaction.messages[0].is_summary = True
        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi there!")

        result = compaction.remove_oldest_messages(1)

        # Should remove only 1 message, not the summary
        assert result["removed"] == 1
        assert len(compaction.messages) == 2
        assert compaction.messages[0].is_summary is True

    def test_remove_oldest_more_than_available(self):
        """Test removing more messages than available."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi")

        result = compaction.remove_oldest_messages(10)

        # Should remove what it can (1 user message, not the greeting summary if exists)
        assert result["removed"] >= 0
        assert result["remaining_messages"] >= 0

    def test_remove_oldest_zero(self):
        """Test removing 0 messages is no-op."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")
        compaction.add_message("assistant", "Hi")

        result = compaction.remove_oldest_messages(0)

        assert result["removed"] == 0
        assert len(compaction.messages) == 2


class TestDeleteTurn:
    """Test delete_turn method."""

    def test_delete_turn_user_with_assistant(self):
        """Test deleting a user message and its following assistant reply."""
        compaction = ConversationCompaction()

        compaction.add_message("assistant", "Hello!")
        compaction.add_message("user", "Hi")
        compaction.add_message("assistant", "Hi there!")
        compaction.add_message("user", "How are you?")
        compaction.add_message("assistant", "I'm good!")

        # Delete at index 1 (user message "Hi" with its assistant reply)
        result = compaction.delete_turn(1)

        assert result["removed"] == 2
        assert len(compaction.messages) == 3
        # Should keep: Hello!, "How are you?", "I'm good!"
        assert compaction.messages[0].content == "Hello!"
        assert compaction.messages[1].content == "How are you?"
        assert compaction.messages[2].content == "I'm good!"

    def test_delete_turn_last_user_only(self):
        """Test deleting last user message without following assistant."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "First")
        compaction.add_message("assistant", "Reply 1")
        compaction.add_message("user", "Second")

        result = compaction.delete_turn(2)

        assert result["removed"] == 1
        assert len(compaction.messages) == 2
        assert compaction.messages[0].content == "First"
        assert compaction.messages[1].content == "Reply 1"

    def test_delete_turn_assistant_message(self):
        """Test deleting an assistant message."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hi")
        compaction.add_message("assistant", "Hello!")
        compaction.add_message("user", "How are you?")
        compaction.add_message("assistant", "I'm fine!")

        # Delete at index 1 (assistant "Hello!")
        result = compaction.delete_turn(1)

        assert result["removed"] == 2  # deletes assistant + next user
        assert len(compaction.messages) == 2

    def test_delete_turn_invalid_index(self):
        """Test deleting with invalid index."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")

        result = compaction.delete_turn(99)

        assert result["removed"] == 0
        assert len(compaction.messages) == 1

    def test_delete_turn_single_message(self):
        """Test deleting the only message."""
        compaction = ConversationCompaction()

        compaction.add_message("user", "Hello")

        result = compaction.delete_turn(0)

        assert result["removed"] == 1
        assert len(compaction.messages) == 0
